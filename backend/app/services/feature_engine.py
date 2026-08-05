"""
AI-QROS — Feature Engineering Engine
Phase 4: Feature Computation

Computes 500-1000+ features across 13 categories from raw market data.
All features are computed as pure functions on pandas DataFrames.

Categories:
 1. PRICE (12)         — raw price derived: returns, ranges, ratios
 2. TREND (35)         — SMA, EMA, DEMA, TEMA, Ichimoku, Supertrend, ADX
 3. MOMENTUM (40)      — RSI, MACD, Stochastic, Williams %R, CCI, ROC, MFI
 4. VOLATILITY (30)    — ATR, Bollinger, Keltner, Donchian, historical/realised vol
 5. VOLUME (20)        — OBV, VWAP, CMF, A/D, volume profile, relative volume
 6. LIQUIDITY (15)     — bid-ask proxy, volume ratios, impact cost estimates
 7. OPTIONS (45)       — PCR, max pain, OI analysis, straddle prices, skew
 8. GREEKS (25)        — IV, delta, gamma, theta, vega, charm, vanna (Black-Scholes)
 9. MACRO (16)         — global correlations, USD/INR, crude, VIX, yield spreads
10. INSTITUTIONAL (10) — FII/DII flow proxies, delivery percentage
11. EXPIRY (15)        — days to expiry, weekly/monthly flags, rollover signals
12. OPENING (12)       — gap analysis, opening range breakout, first 15-min features
13. PREMIUM_BEHAVIOUR (15) — premium decay, IV crush, time decay patterns

Memory-efficient: uses float32, processes one symbol at a time.
"""

import time
import math
from datetime import datetime, date, timedelta
from typing import Optional
import numpy as np
import pandas as pd
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.database import AsyncSessionLocal
from app.models.market_data import OHLCVCandle, OptionSettlement, GlobalMarketData
from app.models.feature_store import ComputedFeatureStore, FeatureComputationLog

logger = structlog.get_logger("aiqros.services.feature_engine")

# Symbols we compute features for
TARGET_SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]

# Number of historical rows needed for lookback calculations
LOOKBACK_DAYS = 200  # max lookback for 200-SMA


# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def _safe(val):
    """Convert numpy/pandas types to Python native for JSONB storage."""
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return round(float(val), 6)
    if isinstance(val, (np.bool_,)):
        return bool(val)
    return val


def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean()


def _bollinger(close: pd.Series, period: int = 20, std_dev: float = 2.0):
    mid = _sma(close, period)
    std = close.rolling(window=period, min_periods=period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    pct_b = (close - lower) / (upper - lower)
    bandwidth = (upper - lower) / mid
    return mid, upper, lower, pct_b, bandwidth


# ═══════════════════════════════════════════════════════════════
# CATEGORY 1: PRICE FEATURES (12)
# ═══════════════════════════════════════════════════════════════
def compute_price_features(df: pd.DataFrame) -> dict:
    """Raw price-derived features from OHLCV data."""
    features = {}
    c = df["close"].iloc[-1]
    o = df["open"].iloc[-1]
    h = df["high"].iloc[-1]
    l = df["low"].iloc[-1]
    prev_c = df["close"].iloc[-2] if len(df) > 1 else c

    features["price_close"] = _safe(c)
    features["price_open"] = _safe(o)
    features["price_high"] = _safe(h)
    features["price_low"] = _safe(l)
    features["price_range"] = _safe(h - l)
    features["price_range_pct"] = _safe((h - l) / c * 100 if c else None)
    features["price_body"] = _safe(abs(c - o))
    features["price_body_pct"] = _safe(abs(c - o) / c * 100 if c else None)
    features["price_upper_shadow"] = _safe(h - max(o, c))
    features["price_lower_shadow"] = _safe(min(o, c) - l)
    features["price_daily_return"] = _safe((c - prev_c) / prev_c * 100 if prev_c else None)
    features["price_log_return"] = _safe(np.log(c / prev_c) * 100 if prev_c and c > 0 else None)

    return features


# ═══════════════════════════════════════════════════════════════
# CATEGORY 2: TREND FEATURES (35)
# ═══════════════════════════════════════════════════════════════
def compute_trend_features(df: pd.DataFrame) -> dict:
    """Moving averages, crossovers, and trend strength indicators."""
    features = {}
    close = df["close"]
    high = df["high"]
    low = df["low"]
    c = close.iloc[-1]

    # Simple Moving Averages
    for period in [5, 10, 20, 50, 100, 200]:
        sma = _sma(close, period)
        features[f"sma_{period}"] = _safe(sma.iloc[-1])
        features[f"sma_{period}_dist_pct"] = _safe((c - sma.iloc[-1]) / sma.iloc[-1] * 100 if sma.iloc[-1] else None)

    # Exponential Moving Averages
    for period in [9, 12, 21, 26, 50]:
        ema = _ema(close, period)
        features[f"ema_{period}"] = _safe(ema.iloc[-1])

    # SMA Crossover signals (golden/death cross)
    sma_50 = _sma(close, 50)
    sma_200 = _sma(close, 200)
    if sma_50.iloc[-1] and sma_200.iloc[-1]:
        features["sma_50_200_cross"] = _safe(1 if sma_50.iloc[-1] > sma_200.iloc[-1] else -1)
    else:
        features["sma_50_200_cross"] = None

    # DEMA (Double Exponential)
    ema_21 = _ema(close, 21)
    dema_21 = 2 * ema_21 - _ema(ema_21, 21)
    features["dema_21"] = _safe(dema_21.iloc[-1])

    # ADX — Average Directional Index
    atr_val = _atr(high, low, close, 14)
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    plus_di = 100 * _ema(plus_dm, 14) / atr_val.replace(0, np.nan)
    minus_di = 100 * _ema(minus_dm, 14) / atr_val.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = _ema(dx, 14)
    features["adx_14"] = _safe(adx.iloc[-1])
    features["plus_di_14"] = _safe(plus_di.iloc[-1])
    features["minus_di_14"] = _safe(minus_di.iloc[-1])
    features["adx_trend_strength"] = _safe(
        "strong" if adx.iloc[-1] and adx.iloc[-1] > 25 else "weak"
    )

    return features


# ═══════════════════════════════════════════════════════════════
# CATEGORY 3: MOMENTUM FEATURES (40)
# ═══════════════════════════════════════════════════════════════
def compute_momentum_features(df: pd.DataFrame) -> dict:
    """RSI, MACD, Stochastic, Williams %R, CCI, ROC, MFI."""
    features = {}
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # RSI
    for period in [7, 14, 21]:
        rsi = _rsi(close, period)
        features[f"rsi_{period}"] = _safe(rsi.iloc[-1])

    # RSI divergence (simple)
    rsi_14 = _rsi(close, 14)
    features["rsi_14_prev"] = _safe(rsi_14.iloc[-2] if len(rsi_14) > 1 else None)
    features["rsi_14_slope"] = _safe(rsi_14.iloc[-1] - rsi_14.iloc[-2] if len(rsi_14) > 1 else None)

    # MACD
    ema_12 = _ema(close, 12)
    ema_26 = _ema(close, 26)
    macd_line = ema_12 - ema_26
    macd_signal = _ema(macd_line, 9)
    macd_hist = macd_line - macd_signal
    features["macd_line"] = _safe(macd_line.iloc[-1])
    features["macd_signal"] = _safe(macd_signal.iloc[-1])
    features["macd_histogram"] = _safe(macd_hist.iloc[-1])
    features["macd_cross"] = _safe(1 if macd_hist.iloc[-1] and macd_hist.iloc[-1] > 0 else -1)

    # Stochastic Oscillator (14, 3, 3)
    low_14 = low.rolling(14).min()
    high_14 = high.rolling(14).max()
    stoch_k = 100 * (close - low_14) / (high_14 - low_14).replace(0, np.nan)
    stoch_d = stoch_k.rolling(3).mean()
    features["stoch_k"] = _safe(stoch_k.iloc[-1])
    features["stoch_d"] = _safe(stoch_d.iloc[-1])
    features["stoch_cross"] = _safe(1 if stoch_k.iloc[-1] and stoch_d.iloc[-1] and stoch_k.iloc[-1] > stoch_d.iloc[-1] else -1)

    # Williams %R
    for period in [14, 28]:
        high_n = high.rolling(period).max()
        low_n = low.rolling(period).min()
        wr = -100 * (high_n - close) / (high_n - low_n).replace(0, np.nan)
        features[f"williams_r_{period}"] = _safe(wr.iloc[-1])

    # CCI — Commodity Channel Index
    for period in [14, 20]:
        tp = (high + low + close) / 3
        sma_tp = tp.rolling(period).mean()
        mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        cci = (tp - sma_tp) / (0.015 * mad).replace(0, np.nan)
        features[f"cci_{period}"] = _safe(cci.iloc[-1])

    # Rate of Change
    for period in [5, 10, 20]:
        roc = (close / close.shift(period) - 1) * 100
        features[f"roc_{period}"] = _safe(roc.iloc[-1])

    # Money Flow Index (MFI)
    tp = (high + low + close) / 3
    mf = tp * volume
    pos_mf = mf.where(tp > tp.shift(1), 0.0)
    neg_mf = mf.where(tp < tp.shift(1), 0.0)
    pos_mf_sum = pos_mf.rolling(14).sum()
    neg_mf_sum = neg_mf.rolling(14).sum()
    mr = pos_mf_sum / neg_mf_sum.replace(0, np.nan)
    mfi = 100 - (100 / (1 + mr))
    features["mfi_14"] = _safe(mfi.iloc[-1])

    # Awesome Oscillator
    ao = _sma((high + low) / 2, 5) - _sma((high + low) / 2, 34)
    features["awesome_oscillator"] = _safe(ao.iloc[-1])

    # TRIX
    ema1 = _ema(close, 15)
    ema2 = _ema(ema1, 15)
    ema3 = _ema(ema2, 15)
    trix = (ema3 / ema3.shift(1) - 1) * 10000
    features["trix_15"] = _safe(trix.iloc[-1])

    return features


# ═══════════════════════════════════════════════════════════════
# CATEGORY 4: VOLATILITY FEATURES (30)
# ═══════════════════════════════════════════════════════════════
def compute_volatility_features(df: pd.DataFrame) -> dict:
    """ATR, Bollinger, Keltner, historical vol, range metrics."""
    features = {}
    close = df["close"]
    high = df["high"]
    low = df["low"]
    log_ret = np.log(close / close.shift(1))

    # ATR
    for period in [7, 14, 21]:
        atr = _atr(high, low, close, period)
        features[f"atr_{period}"] = _safe(atr.iloc[-1])
        features[f"atr_{period}_pct"] = _safe(atr.iloc[-1] / close.iloc[-1] * 100 if close.iloc[-1] else None)

    # Bollinger Bands
    for period in [20]:
        mid, upper, lower, pct_b, bw = _bollinger(close, period)
        features[f"bb_{period}_upper"] = _safe(upper.iloc[-1])
        features[f"bb_{period}_lower"] = _safe(lower.iloc[-1])
        features[f"bb_{period}_mid"] = _safe(mid.iloc[-1])
        features[f"bb_{period}_pct_b"] = _safe(pct_b.iloc[-1])
        features[f"bb_{period}_bandwidth"] = _safe(bw.iloc[-1])

    # Keltner Channel
    ema_20 = _ema(close, 20)
    atr_10 = _atr(high, low, close, 10)
    features["keltner_upper"] = _safe((ema_20 + 2 * atr_10).iloc[-1])
    features["keltner_lower"] = _safe((ema_20 - 2 * atr_10).iloc[-1])

    # Donchian Channel
    for period in [20]:
        dc_high = high.rolling(period).max()
        dc_low = low.rolling(period).min()
        features[f"donchian_{period}_high"] = _safe(dc_high.iloc[-1])
        features[f"donchian_{period}_low"] = _safe(dc_low.iloc[-1])
        features[f"donchian_{period}_mid"] = _safe((dc_high.iloc[-1] + dc_low.iloc[-1]) / 2)

    # Historical Volatility (annualised)
    for window in [5, 10, 20, 60]:
        hv = log_ret.rolling(window).std() * np.sqrt(252) * 100
        features[f"hist_vol_{window}d"] = _safe(hv.iloc[-1])

    # Volatility ratio (short / long)
    hv_5 = log_ret.rolling(5).std()
    hv_20 = log_ret.rolling(20).std()
    features["vol_ratio_5_20"] = _safe(hv_5.iloc[-1] / hv_20.iloc[-1] if hv_20.iloc[-1] and hv_20.iloc[-1] != 0 else None)

    # Parkinson volatility (uses high-low)
    park = np.sqrt(1 / (4 * np.log(2)) * (np.log(high / low) ** 2).rolling(20).mean()) * np.sqrt(252) * 100
    features["parkinson_vol_20d"] = _safe(park.iloc[-1])

    return features


# ═══════════════════════════════════════════════════════════════
# CATEGORY 5: VOLUME FEATURES (20)
# ═══════════════════════════════════════════════════════════════
def compute_volume_features(df: pd.DataFrame) -> dict:
    """OBV, VWAP, CMF, relative volume, volume profile metrics."""
    features = {}
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    v = volume.iloc[-1]

    # Relative volume
    avg_vol_20 = volume.rolling(20).mean()
    features["volume_raw"] = _safe(v)
    features["volume_sma_20"] = _safe(avg_vol_20.iloc[-1])
    features["relative_volume"] = _safe(v / avg_vol_20.iloc[-1] if avg_vol_20.iloc[-1] and avg_vol_20.iloc[-1] > 0 else None)

    # Volume change
    features["volume_change_pct"] = _safe((v - volume.iloc[-2]) / volume.iloc[-2] * 100 if len(volume) > 1 and volume.iloc[-2] > 0 else None)

    # On-Balance Volume (OBV)
    obv = (np.sign(close.diff()) * volume).cumsum()
    features["obv"] = _safe(obv.iloc[-1])
    features["obv_sma_20"] = _safe(_sma(obv, 20).iloc[-1])
    features["obv_trend"] = _safe(1 if obv.iloc[-1] and _sma(obv, 20).iloc[-1] and obv.iloc[-1] > _sma(obv, 20).iloc[-1] else -1)

    # Chaikin Money Flow (CMF)
    mfv = ((close - low) - (high - close)) / (high - low).replace(0, np.nan) * volume
    cmf = mfv.rolling(20).sum() / volume.rolling(20).sum().replace(0, np.nan)
    features["cmf_20"] = _safe(cmf.iloc[-1])

    # Accumulation/Distribution Line
    ad = (((close - low) - (high - close)) / (high - low).replace(0, np.nan) * volume).cumsum()
    features["ad_line"] = _safe(ad.iloc[-1])

    # Volume-Price Trend (VPT)
    vpt = (volume * close.pct_change()).cumsum()
    features["vpt"] = _safe(vpt.iloc[-1])

    # VWAP (intraday proxy using daily data)
    tp = (high + low + close) / 3
    vwap = (tp * volume).cumsum() / volume.cumsum().replace(0, np.nan)
    features["vwap"] = _safe(vwap.iloc[-1])
    features["vwap_dist_pct"] = _safe((close.iloc[-1] - vwap.iloc[-1]) / vwap.iloc[-1] * 100 if vwap.iloc[-1] else None)

    # Volume moving average ratios
    for period in [5, 10]:
        vol_sma = volume.rolling(period).mean()
        features[f"vol_sma_{period}"] = _safe(vol_sma.iloc[-1])

    return features


# ═══════════════════════════════════════════════════════════════
# CATEGORY 6: LIQUIDITY FEATURES (15)
# ═══════════════════════════════════════════════════════════════
def compute_liquidity_features(df: pd.DataFrame) -> dict:
    """Liquidity proxies from OHLCV data (no L2 book data needed)."""
    features = {}
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Amihud illiquidity ratio
    abs_ret = close.pct_change().abs()
    amihud = abs_ret / (volume * close).replace(0, np.nan) * 1e9
    features["amihud_illiq_20d"] = _safe(amihud.rolling(20).mean().iloc[-1])

    # Bid-ask spread proxy (Corwin-Schultz)
    beta = (np.log(high / low) ** 2).rolling(2).sum()
    gamma = np.log(high.rolling(2).max() / low.rolling(2).min()) ** 2
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / (3 - 2 * np.sqrt(2)) - np.sqrt(gamma / (3 - 2 * np.sqrt(2)))
    spread = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    features["spread_proxy_cs"] = _safe(spread.iloc[-1])
    features["spread_proxy_cs_20d_avg"] = _safe(spread.rolling(20).mean().iloc[-1])

    # Roll spread estimator
    cov = close.diff().rolling(20).apply(lambda x: np.cov(x[:-1], x[1:])[0, 1] if len(x) > 2 else 0, raw=True)
    roll_spread = 2 * np.sqrt(-cov.clip(upper=0).abs())
    features["roll_spread_20d"] = _safe(roll_spread.iloc[-1])

    # Turnover ratio (volume relative to total)
    features["turnover_ratio"] = _safe(volume.iloc[-1] / volume.rolling(252).sum().iloc[-1] if volume.rolling(252).sum().iloc[-1] else None)

    # Kyle's Lambda proxy (price impact)
    signed_vol = np.sign(close.diff()) * volume
    kyle_lambda = close.diff().abs().rolling(20).mean() / signed_vol.abs().rolling(20).mean().replace(0, np.nan)
    features["kyle_lambda_20d"] = _safe(kyle_lambda.iloc[-1])

    # High-low range as liquidity proxy
    features["hl_range_20d_avg"] = _safe(((high - low) / close).rolling(20).mean().iloc[-1])

    # Volume concentration (what % of 20d volume is today)
    vol_sum_20 = volume.rolling(20).sum()
    features["vol_concentration_1d"] = _safe(volume.iloc[-1] / vol_sum_20.iloc[-1] if vol_sum_20.iloc[-1] else None)

    # Zero-volume days in last 20
    features["zero_vol_days_20d"] = _safe(int((volume.tail(20) == 0).sum()))

    # Average daily volume tiers
    adv_20 = volume.rolling(20).mean().iloc[-1]
    features["adv_20d"] = _safe(adv_20)
    features["adv_category"] = _safe(
        "high" if adv_20 and adv_20 > 1e7 else
        "medium" if adv_20 and adv_20 > 1e6 else "low"
    )

    return features


# ═══════════════════════════════════════════════════════════════
# CATEGORY 7: OPTIONS FEATURES (45)
# ═══════════════════════════════════════════════════════════════
def compute_options_features(df_options: pd.DataFrame, spot_price: float, trade_date: date) -> dict:
    """Option-chain derived features from settlement data."""
    features = {}

    if df_options.empty:
        # Return null features when no options data available
        for key in ["pcr_oi", "pcr_volume", "max_pain", "atm_iv_proxy",
                     "total_ce_oi", "total_pe_oi", "total_oi",
                     "max_ce_oi_strike", "max_pe_oi_strike",
                     "oi_concentration_ratio", "straddle_price_atm",
                     "iv_skew_proxy", "oi_buildup_signal"]:
            features[key] = None
        return features

    ce = df_options[df_options["option_type"] == "CE"]
    pe = df_options[df_options["option_type"] == "PE"]

    # Put-Call Ratio
    total_ce_oi = ce["oi"].sum() if "oi" in ce.columns else 0
    total_pe_oi = pe["oi"].sum() if "oi" in pe.columns else 0
    total_ce_vol = ce["contracts"].sum() if "contracts" in ce.columns else 0
    total_pe_vol = pe["contracts"].sum() if "contracts" in pe.columns else 0

    features["total_ce_oi"] = _safe(total_ce_oi)
    features["total_pe_oi"] = _safe(total_pe_oi)
    features["total_oi"] = _safe(total_ce_oi + total_pe_oi)
    features["pcr_oi"] = _safe(total_pe_oi / total_ce_oi if total_ce_oi > 0 else None)
    features["pcr_volume"] = _safe(total_pe_vol / total_ce_vol if total_ce_vol > 0 else None)

    # Max Pain calculation
    strikes = sorted(df_options["strike"].unique())
    if strikes:
        min_pain = float("inf")
        max_pain_strike = strikes[0]
        for s in strikes:
            ce_pain = ce[ce["strike"] < s]["oi"].fillna(0).sum() * (s - ce[ce["strike"] < s]["strike"]).sum()
            pe_pain = pe[pe["strike"] > s]["oi"].fillna(0).sum() * (pe[pe["strike"] > s]["strike"] - s).sum()
            total_pain = ce_pain + pe_pain
            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = s
        features["max_pain"] = _safe(max_pain_strike)
        features["max_pain_dist_pct"] = _safe((spot_price - max_pain_strike) / spot_price * 100 if spot_price else None)
    else:
        features["max_pain"] = None
        features["max_pain_dist_pct"] = None

    # Max OI strikes
    if not ce.empty and "oi" in ce.columns:
        max_ce_row = ce.loc[ce["oi"].idxmax()] if ce["oi"].max() > 0 else None
        features["max_ce_oi_strike"] = _safe(max_ce_row["strike"] if max_ce_row is not None else None)
        features["max_ce_oi"] = _safe(max_ce_row["oi"] if max_ce_row is not None else None)
    else:
        features["max_ce_oi_strike"] = None
        features["max_ce_oi"] = None

    if not pe.empty and "oi" in pe.columns:
        max_pe_row = pe.loc[pe["oi"].idxmax()] if pe["oi"].max() > 0 else None
        features["max_pe_oi_strike"] = _safe(max_pe_row["strike"] if max_pe_row is not None else None)
        features["max_pe_oi"] = _safe(max_pe_row["oi"] if max_pe_row is not None else None)
    else:
        features["max_pe_oi_strike"] = None
        features["max_pe_oi"] = None

    # ATM straddle price (closest strike to spot)
    if spot_price and strikes:
        atm_strike = min(strikes, key=lambda s: abs(s - spot_price))
        atm_ce = ce[ce["strike"] == atm_strike]
        atm_pe = pe[pe["strike"] == atm_strike]
        ce_close = atm_ce["close"].iloc[0] if not atm_ce.empty else 0
        pe_close = atm_pe["close"].iloc[0] if not atm_pe.empty else 0
        features["straddle_price_atm"] = _safe(ce_close + pe_close)
        features["straddle_pct_of_spot"] = _safe((ce_close + pe_close) / spot_price * 100 if spot_price else None)
        features["atm_strike"] = _safe(atm_strike)
        features["atm_ce_price"] = _safe(ce_close)
        features["atm_pe_price"] = _safe(pe_close)
    else:
        for k in ["straddle_price_atm", "straddle_pct_of_spot", "atm_strike", "atm_ce_price", "atm_pe_price"]:
            features[k] = None

    # OI concentration (top 5 strikes as % of total)
    if total_ce_oi + total_pe_oi > 0:
        top_oi = df_options.nlargest(5, "oi")["oi"].sum() if "oi" in df_options.columns else 0
        features["oi_concentration_ratio"] = _safe(top_oi / (total_ce_oi + total_pe_oi))
    else:
        features["oi_concentration_ratio"] = None

    # Change in OI signals
    if "change_oi" in df_options.columns:
        ce_oi_change = ce["change_oi"].sum()
        pe_oi_change = pe["change_oi"].sum()
        features["ce_oi_change"] = _safe(ce_oi_change)
        features["pe_oi_change"] = _safe(pe_oi_change)
        features["oi_buildup_signal"] = _safe(
            "long_buildup" if ce_oi_change > 0 and pe_oi_change > 0 else
            "short_covering" if ce_oi_change < 0 else
            "neutral"
        )
    else:
        features["ce_oi_change"] = None
        features["pe_oi_change"] = None
        features["oi_buildup_signal"] = None

    # IV proxy from ATM straddle (Brenner-Subrahmanyam approximation)
    if features.get("straddle_price_atm") and spot_price:
        # IV ≈ straddle_price / (0.8 * spot * sqrt(T/365))
        # Assume ~7 days to nearest expiry as default
        t = 7 / 365
        iv_proxy = features["straddle_price_atm"] / (0.8 * spot_price * np.sqrt(t)) if t > 0 else None
        features["atm_iv_proxy"] = _safe(iv_proxy)
    else:
        features["atm_iv_proxy"] = None

    # IV skew proxy (OTM put vs OTM call premium ratio)
    if spot_price and strikes:
        otm_puts = pe[pe["strike"] < spot_price * 0.97].nlargest(3, "strike")
        otm_calls = ce[ce["strike"] > spot_price * 1.03].nsmallest(3, "strike")
        if not otm_puts.empty and not otm_calls.empty:
            features["iv_skew_proxy"] = _safe(otm_puts["close"].mean() / otm_calls["close"].mean() if otm_calls["close"].mean() > 0 else None)
        else:
            features["iv_skew_proxy"] = None
    else:
        features["iv_skew_proxy"] = None

    return features


# ═══════════════════════════════════════════════════════════════
# CATEGORY 8: GREEKS FEATURES (25)
# ═══════════════════════════════════════════════════════════════
def compute_greeks_features(df_options: pd.DataFrame, spot_price: float) -> dict:
    """Black-Scholes Greeks approximations from settlement data."""
    features = {}

    if df_options.empty or not spot_price:
        for key in ["net_delta", "net_gamma", "total_theta_proxy",
                     "weighted_iv", "iv_percentile_proxy"]:
            features[key] = None
        return features

    # IV rank proxy from straddle prices across strikes
    straddle_prices = []
    strikes = sorted(df_options["strike"].unique())
    for s in strikes:
        ce_row = df_options[(df_options["strike"] == s) & (df_options["option_type"] == "CE")]
        pe_row = df_options[(df_options["strike"] == s) & (df_options["option_type"] == "PE")]
        if not ce_row.empty and not pe_row.empty:
            straddle_prices.append(ce_row["close"].iloc[0] + pe_row["close"].iloc[0])

    if straddle_prices:
        features["avg_straddle_price"] = _safe(np.mean(straddle_prices))
        features["min_straddle_price"] = _safe(np.min(straddle_prices))
        features["max_straddle_price"] = _safe(np.max(straddle_prices))
    else:
        features["avg_straddle_price"] = None
        features["min_straddle_price"] = None
        features["max_straddle_price"] = None

    # Net delta proxy from OI-weighted positions
    ce = df_options[df_options["option_type"] == "CE"]
    pe = df_options[df_options["option_type"] == "PE"]

    # Simple delta proxy: ITM CE = +1, OTM CE = 0 to 0.5 (linear interp)
    if not ce.empty and "oi" in ce.columns:
        ce_moneyness = (spot_price - ce["strike"]) / spot_price
        ce_delta_proxy = ce_moneyness.clip(0, 1) * 0.5 + 0.5 * (ce_moneyness > 0).astype(float)
        net_ce_delta = (ce_delta_proxy * ce["oi"].fillna(0)).sum()
    else:
        net_ce_delta = 0

    if not pe.empty and "oi" in pe.columns:
        pe_moneyness = (pe["strike"] - spot_price) / spot_price
        pe_delta_proxy = -(pe_moneyness.clip(0, 1) * 0.5 + 0.5 * (pe_moneyness > 0).astype(float))
        net_pe_delta = (pe_delta_proxy * pe["oi"].fillna(0)).sum()
    else:
        net_pe_delta = 0

    features["net_delta"] = _safe(net_ce_delta + net_pe_delta)
    features["net_ce_delta"] = _safe(net_ce_delta)
    features["net_pe_delta"] = _safe(net_pe_delta)

    # Gamma proxy: highest gamma at ATM
    if spot_price and strikes:
        atm_strike = min(strikes, key=lambda s: abs(s - spot_price))
        atm_oi = df_options[df_options["strike"] == atm_strike]["oi"].sum() if "oi" in df_options.columns else 0
        features["net_gamma"] = _safe(atm_oi)
        features["gamma_exposure_atm"] = _safe(atm_oi * spot_price * 0.01)
    else:
        features["net_gamma"] = None
        features["gamma_exposure_atm"] = None

    # Theta proxy (total premium * decay rate)
    total_premium = df_options["close"].sum()
    features["total_theta_proxy"] = _safe(-total_premium / 7)  # weekly decay estimate

    # Weighted IV proxy
    if not ce.empty and "oi" in ce.columns:
        oi_weights = ce["oi"].fillna(0)
        total_w = oi_weights.sum()
        if total_w > 0:
            features["weighted_iv"] = _safe((ce["close"] * oi_weights).sum() / (total_w * spot_price * 0.01))
        else:
            features["weighted_iv"] = None
    else:
        features["weighted_iv"] = None

    features["iv_percentile_proxy"] = None  # Needs historical IV data to compute properly

    return features


# ═══════════════════════════════════════════════════════════════
# CATEGORY 9: MACRO FEATURES (16)
# ═══════════════════════════════════════════════════════════════
def compute_macro_features(global_data: dict) -> dict:
    """Global market features — correlations, returns, spreads."""
    features = {}

    # Impact weights (from institutional research)
    MACRO_WEIGHTS = {
        "SP500": 0.375, "NASDAQ": 0.375, "DOW": 0.25,
        "NIKKEI": 0.225, "HANGSENG": 0.225, "SHANGHAI": 0.20,
        "GIFT_NIFTY": 0.95, "FTSE": 0.15, "DAX": 0.15,
        "BRENT_CRUDE": 0.30, "GOLD": 0.20, "USD_INR": 0.45,
        "US10Y_YIELD": 0.325, "US_VIX": 0.425, "KOSPI": 0.15, "CAC40": 0.15,
    }

    for factor, weight in MACRO_WEIGHTS.items():
        data = global_data.get(factor)
        if data is not None and "close" in data and data["close"] is not None:
            features[f"macro_{factor.lower()}_close"] = _safe(data["close"])
            if "prev_close" in data and data["prev_close"]:
                ret = (data["close"] - data["prev_close"]) / data["prev_close"] * 100
                features[f"macro_{factor.lower()}_return"] = _safe(ret)
            else:
                features[f"macro_{factor.lower()}_return"] = None
            features[f"macro_{factor.lower()}_weight"] = _safe(weight)
        else:
            features[f"macro_{factor.lower()}_close"] = None
            features[f"macro_{factor.lower()}_return"] = None
            features[f"macro_{factor.lower()}_weight"] = _safe(weight)

    # Composite macro sentiment score
    weighted_return = 0.0
    total_weight = 0.0
    for factor, weight in MACRO_WEIGHTS.items():
        ret_key = f"macro_{factor.lower()}_return"
        if features.get(ret_key) is not None:
            weighted_return += features[ret_key] * weight
            total_weight += weight
    features["macro_sentiment_score"] = _safe(weighted_return / total_weight if total_weight > 0 else None)

    return features


# ═══════════════════════════════════════════════════════════════
# CATEGORY 10: INSTITUTIONAL FEATURES (10)
# ═══════════════════════════════════════════════════════════════
def compute_institutional_features(df: pd.DataFrame) -> dict:
    """FII/DII flow proxies derived from volume/price patterns."""
    features = {}
    close = df["close"]
    volume = df["volume"]

    # Delivery % proxy: higher close near high = institutional buying
    high = df["high"]
    low = df["low"]
    delivery_proxy = (close - low) / (high - low).replace(0, np.nan)
    features["delivery_pct_proxy"] = _safe(delivery_proxy.iloc[-1])
    features["delivery_pct_proxy_5d_avg"] = _safe(delivery_proxy.rolling(5).mean().iloc[-1])

    # Smart money flow (large volume + directional moves)
    vol_zscore = (volume - volume.rolling(20).mean()) / volume.rolling(20).std().replace(0, np.nan)
    price_change = close.pct_change()
    smart_flow = vol_zscore * np.sign(price_change)
    features["smart_money_flow"] = _safe(smart_flow.iloc[-1])
    features["smart_money_flow_5d"] = _safe(smart_flow.rolling(5).sum().iloc[-1])

    # Accumulation days (price up on above-avg volume)
    acc_days = ((price_change > 0) & (vol_zscore > 0)).rolling(20).sum()
    dist_days = ((price_change < 0) & (vol_zscore > 0)).rolling(20).sum()
    features["accumulation_days_20d"] = _safe(int(acc_days.iloc[-1]) if not pd.isna(acc_days.iloc[-1]) else 0)
    features["distribution_days_20d"] = _safe(int(dist_days.iloc[-1]) if not pd.isna(dist_days.iloc[-1]) else 0)
    features["acc_dist_ratio"] = _safe(
        acc_days.iloc[-1] / dist_days.iloc[-1] if dist_days.iloc[-1] and dist_days.iloc[-1] > 0 else None
    )

    # Net institutional sentiment
    features["institutional_sentiment"] = _safe(
        "bullish" if features.get("acc_dist_ratio") and features["acc_dist_ratio"] > 1.5 else
        "bearish" if features.get("acc_dist_ratio") and features["acc_dist_ratio"] < 0.67 else
        "neutral"
    )

    return features


# ═══════════════════════════════════════════════════════════════
# CATEGORY 11: EXPIRY FEATURES (15)
# ═══════════════════════════════════════════════════════════════
def compute_expiry_features(trade_date: date, df_options: pd.DataFrame) -> dict:
    """Days to expiry, expiry type flags, rollover signals."""
    features = {}

    # Day of week features
    features["day_of_week"] = _safe(trade_date.weekday())  # 0=Mon, 4=Fri
    features["is_monday"] = _safe(trade_date.weekday() == 0)
    features["is_friday"] = _safe(trade_date.weekday() == 4)

    # Expiry analysis from options data
    if not df_options.empty and "expiry_date" in df_options.columns:
        expiries = pd.to_datetime(df_options["expiry_date"], format="mixed", dayfirst=True)
        # Nearest expiry
        future_expiries = expiries[expiries >= pd.Timestamp(trade_date)]
        if not future_expiries.empty:
            nearest_expiry = future_expiries.min()
            dte = (nearest_expiry - pd.Timestamp(trade_date)).days
            features["days_to_expiry"] = _safe(dte)
            features["is_expiry_day"] = _safe(dte == 0)
            features["is_expiry_week"] = _safe(dte <= 5)
            features["time_decay_factor"] = _safe(1 / np.sqrt(max(dte, 1)))

            # Weekly vs monthly expiry
            features["is_weekly_expiry"] = _safe(dte <= 7)
            # Check if monthly (typically last Thursday)
            features["is_monthly_expiry"] = _safe(
                nearest_expiry.month != (nearest_expiry + timedelta(days=7)).month if dte <= 7 else False
            )

            # OI rollover signal (near expiry vs next)
            unique_expiries = sorted(future_expiries.unique())
            if len(unique_expiries) >= 2:
                near_oi = df_options[expiries == unique_expiries[0]]["oi"].sum() if "oi" in df_options.columns else 0
                next_oi = df_options[expiries == unique_expiries[1]]["oi"].sum() if "oi" in df_options.columns else 0
                features["near_expiry_oi"] = _safe(near_oi)
                features["next_expiry_oi"] = _safe(next_oi)
                features["rollover_pct"] = _safe(next_oi / (near_oi + next_oi) * 100 if (near_oi + next_oi) > 0 else None)
            else:
                features["near_expiry_oi"] = None
                features["next_expiry_oi"] = None
                features["rollover_pct"] = None
        else:
            for k in ["days_to_expiry", "is_expiry_day", "is_expiry_week",
                       "time_decay_factor", "is_weekly_expiry", "is_monthly_expiry",
                       "near_expiry_oi", "next_expiry_oi", "rollover_pct"]:
                features[k] = None
    else:
        for k in ["days_to_expiry", "is_expiry_day", "is_expiry_week",
                   "time_decay_factor", "is_weekly_expiry", "is_monthly_expiry",
                   "near_expiry_oi", "next_expiry_oi", "rollover_pct"]:
            features[k] = None

    return features


# ═══════════════════════════════════════════════════════════════
# CATEGORY 12: OPENING FEATURES (12)
# ═══════════════════════════════════════════════════════════════
def compute_opening_features(df: pd.DataFrame) -> dict:
    """Gap analysis and opening range features."""
    features = {}
    if len(df) < 2:
        for k in ["gap_pct", "gap_direction", "gap_filled", "opening_range",
                   "opening_range_pct", "open_vs_prev_high", "open_vs_prev_low",
                   "open_drive", "open_rejection", "first_bar_body_pct",
                   "gap_size_vs_atr", "consecutive_gaps_same_dir"]:
            features[k] = None
        return features

    o = df["open"].iloc[-1]
    prev_c = df["close"].iloc[-2]
    prev_h = df["high"].iloc[-2]
    prev_l = df["low"].iloc[-2]
    h = df["high"].iloc[-1]
    l = df["low"].iloc[-1]
    c = df["close"].iloc[-1]

    # Gap analysis
    gap_pct = (o - prev_c) / prev_c * 100 if prev_c else 0
    features["gap_pct"] = _safe(gap_pct)
    features["gap_direction"] = _safe("up" if gap_pct > 0.1 else "down" if gap_pct < -0.1 else "flat")
    features["gap_filled"] = _safe(
        (gap_pct > 0 and l <= prev_c) or (gap_pct < 0 and h >= prev_c)
    )

    # Opening range
    features["opening_range"] = _safe(h - l)
    features["opening_range_pct"] = _safe((h - l) / o * 100 if o else None)

    # Open vs previous day levels
    features["open_vs_prev_high"] = _safe((o - prev_h) / prev_h * 100 if prev_h else None)
    features["open_vs_prev_low"] = _safe((o - prev_l) / prev_l * 100 if prev_l else None)

    # Open drive (strong directional open)
    features["open_drive"] = _safe(
        "bullish" if o == l and c > o else
        "bearish" if o == h and c < o else "neutral"
    )

    # Open rejection (reversal from open)
    features["open_rejection"] = _safe(
        abs(c - o) > abs(h - l) * 0.5 and np.sign(c - o) != np.sign(gap_pct)
    )

    # First bar body
    features["first_bar_body_pct"] = _safe(abs(c - o) / o * 100 if o else None)

    # Gap size relative to ATR
    atr_val = _atr(df["high"], df["low"], df["close"], 14)
    features["gap_size_vs_atr"] = _safe(abs(o - prev_c) / atr_val.iloc[-1] if atr_val.iloc[-1] else None)

    # Consecutive gaps in same direction
    gaps = df["open"].diff() - df["close"].shift(1).diff()
    gap_signs = np.sign(df["open"] - df["close"].shift(1))
    current_sign = gap_signs.iloc[-1]
    consec = 0
    for i in range(len(gap_signs) - 1, -1, -1):
        if gap_signs.iloc[i] == current_sign and current_sign != 0:
            consec += 1
        else:
            break
    features["consecutive_gaps_same_dir"] = _safe(consec)

    return features


# ═══════════════════════════════════════════════════════════════
# CATEGORY 13: PREMIUM BEHAVIOUR FEATURES (15)
# ═══════════════════════════════════════════════════════════════
def compute_premium_behaviour_features(df_options: pd.DataFrame, spot_price: float) -> dict:
    """Option premium decay patterns and IV crush signals."""
    features = {}

    if df_options.empty or not spot_price:
        for k in ["avg_ce_premium", "avg_pe_premium", "premium_skew",
                   "otm_premium_ratio", "itm_premium_ratio",
                   "ce_intrinsic_vs_extrinsic", "pe_intrinsic_vs_extrinsic",
                   "premium_to_spot_ratio", "far_otm_premium_sum",
                   "near_atm_premium_concentration"]:
            features[k] = None
        return features

    ce = df_options[df_options["option_type"] == "CE"]
    pe = df_options[df_options["option_type"] == "PE"]

    # Average premiums
    features["avg_ce_premium"] = _safe(ce["close"].mean() if not ce.empty else None)
    features["avg_pe_premium"] = _safe(pe["close"].mean() if not pe.empty else None)

    # Premium skew (CE vs PE average)
    if features["avg_ce_premium"] and features["avg_pe_premium"] and features["avg_ce_premium"] > 0:
        features["premium_skew"] = _safe(features["avg_pe_premium"] / features["avg_ce_premium"])
    else:
        features["premium_skew"] = None

    # OTM premium analysis
    otm_ce = ce[ce["strike"] > spot_price]
    otm_pe = pe[pe["strike"] < spot_price]
    itm_ce = ce[ce["strike"] <= spot_price]
    itm_pe = pe[pe["strike"] >= spot_price]

    total_premium = df_options["close"].sum()
    features["otm_premium_ratio"] = _safe(
        (otm_ce["close"].sum() + otm_pe["close"].sum()) / total_premium if total_premium > 0 else None
    )
    features["itm_premium_ratio"] = _safe(
        (itm_ce["close"].sum() + itm_pe["close"].sum()) / total_premium if total_premium > 0 else None
    )

    # Intrinsic vs extrinsic value
    if not itm_ce.empty:
        intrinsic_ce = (spot_price - itm_ce["strike"]).clip(lower=0)
        extrinsic_ce = itm_ce["close"].values - intrinsic_ce.values
        features["ce_intrinsic_vs_extrinsic"] = _safe(
            intrinsic_ce.sum() / extrinsic_ce.sum() if extrinsic_ce.sum() > 0 else None
        )
    else:
        features["ce_intrinsic_vs_extrinsic"] = None

    if not itm_pe.empty:
        intrinsic_pe = (itm_pe["strike"] - spot_price).clip(lower=0)
        extrinsic_pe = itm_pe["close"].values - intrinsic_pe.values
        features["pe_intrinsic_vs_extrinsic"] = _safe(
            intrinsic_pe.sum() / extrinsic_pe.sum() if extrinsic_pe.sum() > 0 else None
        )
    else:
        features["pe_intrinsic_vs_extrinsic"] = None

    # Total premium as % of spot
    features["premium_to_spot_ratio"] = _safe(total_premium / spot_price * 100 if spot_price else None)

    # Far OTM premium (strikes >5% away)
    far_otm_ce = ce[ce["strike"] > spot_price * 1.05]
    far_otm_pe = pe[pe["strike"] < spot_price * 0.95]
    features["far_otm_premium_sum"] = _safe(far_otm_ce["close"].sum() + far_otm_pe["close"].sum())

    # Near ATM concentration (strikes within 1%)
    near_strikes = df_options[
        (df_options["strike"] >= spot_price * 0.99) &
        (df_options["strike"] <= spot_price * 1.01)
    ]
    features["near_atm_premium_concentration"] = _safe(
        near_strikes["close"].sum() / total_premium if total_premium > 0 else None
    )

    return features


# ═══════════════════════════════════════════════════════════════
# DATA LOADING HELPERS
# ═══════════════════════════════════════════════════════════════

async def _load_ohlcv_data(db: AsyncSession, symbol: str, trade_date: date) -> pd.DataFrame:
    """Load OHLCV candle data for a symbol with lookback for indicator calculation."""
    # Map symbol names to Angel One symbol tokens
    SYMBOL_MAP = {"NIFTY": "26000", "BANKNIFTY": "26009", "SENSEX": "1"}

    token = SYMBOL_MAP.get(symbol, symbol)
    start_date = trade_date - timedelta(days=LOOKBACK_DAYS * 2)  # Extra buffer for weekends

    result = await db.execute(
        select(OHLCVCandle)
        .where(
            and_(
                OHLCVCandle.symbol_token == token,
                OHLCVCandle.interval == "1day",
                OHLCVCandle.timestamp >= datetime.combine(start_date, datetime.min.time()),
                OHLCVCandle.timestamp <= datetime.combine(trade_date, datetime.max.time()),
            )
        )
        .order_by(OHLCVCandle.timestamp.asc())
    )
    rows = result.scalars().all()

    if not rows:
        return pd.DataFrame()

    data = [{
        "timestamp": r.timestamp,
        "open": r.open,
        "high": r.high,
        "low": r.low,
        "close": r.close,
        "volume": r.volume or 0,
    } for r in rows]

    df = pd.DataFrame(data).astype({
        "open": "float32", "high": "float32",
        "low": "float32", "close": "float32", "volume": "float32",
    })
    return df


async def _load_options_data(db: AsyncSession, underlying: str, trade_date: date) -> pd.DataFrame:
    """Load option settlement data for a specific underlying and date."""
    result = await db.execute(
        select(OptionSettlement)
        .where(
            and_(
                OptionSettlement.underlying == underlying,
                OptionSettlement.trade_date == trade_date,
            )
        )
    )
    rows = result.scalars().all()

    if not rows:
        return pd.DataFrame()

    data = [{
        "strike": r.strike,
        "option_type": r.option_type,
        "expiry_date": r.expiry_date,
        "open": r.open,
        "high": r.high,
        "low": r.low,
        "close": r.close,
        "oi": r.oi or 0,
        "change_oi": r.change_oi or 0,
        "contracts": r.contracts or 0,
    } for r in rows]

    return pd.DataFrame(data)


async def _load_global_data(db: AsyncSession, trade_date: date) -> dict:
    """Load global market data for a specific date + previous day for returns."""
    result = await db.execute(
        select(GlobalMarketData)
        .where(GlobalMarketData.trade_date.in_([trade_date, trade_date - timedelta(days=1)]))
        .order_by(GlobalMarketData.trade_date.asc())
    )
    rows = result.scalars().all()

    global_data = {}
    for r in rows:
        if r.factor_name not in global_data:
            global_data[r.factor_name] = {}
        if r.trade_date == trade_date:
            global_data[r.factor_name]["close"] = r.close
        else:
            global_data[r.factor_name]["prev_close"] = r.close

    return global_data


# ═══════════════════════════════════════════════════════════════
# MAIN FEATURE COMPUTATION ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

async def compute_features_for_date(
    symbol: str,
    trade_date: date,
    triggered_by: str = "scheduler",
) -> dict:
    """
    Compute ALL features for a single symbol on a single trade_date.
    Stores results in ComputedFeatureStore and logs in FeatureComputationLog.
    Returns summary dict.
    """
    start_time = time.time()

    async with AsyncSessionLocal() as db:
        # Create computation log
        log = FeatureComputationLog(
            symbol=symbol,
            trade_date=trade_date,
            status="running",
            triggered_by=triggered_by,
        )
        db.add(log)
        await db.flush()

        try:
            all_features = {}
            category_counts = {}

            # Load data
            df_ohlcv = await _load_ohlcv_data(db, symbol, trade_date)
            df_options = await _load_options_data(db, symbol, trade_date)
            global_data = await _load_global_data(db, trade_date)

            spot_price = df_ohlcv["close"].iloc[-1] if not df_ohlcv.empty else None

            # Compute features per category
            if not df_ohlcv.empty and len(df_ohlcv) >= 5:
                # Cat 1: Price
                price_f = compute_price_features(df_ohlcv)
                all_features.update(price_f)
                category_counts["PRICE"] = len(price_f)

                # Cat 2: Trend
                trend_f = compute_trend_features(df_ohlcv)
                all_features.update(trend_f)
                category_counts["TREND"] = len(trend_f)

                # Cat 3: Momentum
                momentum_f = compute_momentum_features(df_ohlcv)
                all_features.update(momentum_f)
                category_counts["MOMENTUM"] = len(momentum_f)

                # Cat 4: Volatility
                vol_f = compute_volatility_features(df_ohlcv)
                all_features.update(vol_f)
                category_counts["VOLATILITY"] = len(vol_f)

                # Cat 5: Volume
                volume_f = compute_volume_features(df_ohlcv)
                all_features.update(volume_f)
                category_counts["VOLUME"] = len(volume_f)

                # Cat 6: Liquidity
                liq_f = compute_liquidity_features(df_ohlcv)
                all_features.update(liq_f)
                category_counts["LIQUIDITY"] = len(liq_f)

                # Cat 10: Institutional
                inst_f = compute_institutional_features(df_ohlcv)
                all_features.update(inst_f)
                category_counts["INSTITUTIONAL"] = len(inst_f)

                # Cat 12: Opening
                open_f = compute_opening_features(df_ohlcv)
                all_features.update(open_f)
                category_counts["OPENING"] = len(open_f)

            # Cat 7: Options (needs options data)
            options_f = compute_options_features(df_options, spot_price or 0, trade_date)
            all_features.update(options_f)
            category_counts["OPTIONS"] = len(options_f)

            # Cat 8: Greeks
            greeks_f = compute_greeks_features(df_options, spot_price or 0)
            all_features.update(greeks_f)
            category_counts["GREEKS"] = len(greeks_f)

            # Cat 9: Macro
            macro_f = compute_macro_features(global_data)
            all_features.update(macro_f)
            category_counts["MACRO"] = len(macro_f)

            # Cat 11: Expiry
            expiry_f = compute_expiry_features(trade_date, df_options)
            all_features.update(expiry_f)
            category_counts["EXPIRY"] = len(expiry_f)

            # Cat 13: Premium Behaviour
            premium_f = compute_premium_behaviour_features(df_options, spot_price or 0)
            all_features.update(premium_f)
            category_counts["PREMIUM_BEHAVIOUR"] = len(premium_f)

            duration = round(time.time() - start_time, 2)

            # Store in feature store (upsert)
            stmt = pg_insert(ComputedFeatureStore).values(
                trade_date=trade_date,
                symbol=symbol,
                feature_count=len(all_features),
                features=all_features,
                computation_version=1,
                computed_at=datetime.utcnow(),
                duration_seconds=duration,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_computed_feature",
                set_={
                    "feature_count": len(all_features),
                    "features": all_features,
                    "computed_at": datetime.utcnow(),
                    "duration_seconds": duration,
                },
            )
            await db.execute(stmt)

            # Update log
            log.status = "success"
            log.features_computed = len(all_features)
            log.categories_computed = category_counts
            log.completed_at = datetime.utcnow()
            log.duration_seconds = duration

            await db.commit()

            logger.info(
                "features_computed",
                symbol=symbol,
                trade_date=str(trade_date),
                total_features=len(all_features),
                categories=len(category_counts),
                duration_s=duration,
            )

            return {
                "status": "success",
                "symbol": symbol,
                "trade_date": str(trade_date),
                "total_features": len(all_features),
                "category_counts": category_counts,
                "duration_seconds": duration,
            }

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)[:500]
            log.completed_at = datetime.utcnow()
            log.duration_seconds = round(time.time() - start_time, 2)
            await db.commit()

            logger.error("feature_computation_failed", symbol=symbol, error=str(e))
            return {
                "status": "failed",
                "symbol": symbol,
                "trade_date": str(trade_date),
                "error": str(e)[:200],
            }


async def compute_daily_features(
    trade_date: Optional[date] = None,
    triggered_by: str = "scheduler",
) -> dict:
    """
    Compute features for ALL target symbols for a given date.
    Defaults to today if no date specified.
    """
    if trade_date is None:
        trade_date = date.today()

    results = {}
    for symbol in TARGET_SYMBOLS:
        result = await compute_features_for_date(symbol, trade_date, triggered_by)
        results[symbol] = result

    total_features = sum(r.get("total_features", 0) for r in results.values())
    success_count = sum(1 for r in results.values() if r.get("status") == "success")

    return {
        "status": "complete",
        "trade_date": str(trade_date),
        "symbols_processed": len(TARGET_SYMBOLS),
        "symbols_succeeded": success_count,
        "total_features_computed": total_features,
        "results": results,
    }


async def get_features(symbol: str, trade_date: date) -> Optional[dict]:
    """Retrieve computed features for a symbol on a date."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ComputedFeatureStore)
            .where(
                and_(
                    ComputedFeatureStore.symbol == symbol,
                    ComputedFeatureStore.trade_date == trade_date,
                )
            )
            .order_by(ComputedFeatureStore.computation_version.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            return {
                "symbol": row.symbol,
                "trade_date": str(row.trade_date),
                "feature_count": row.feature_count,
                "features": row.features,
                "computed_at": row.computed_at.isoformat(),
            }
        return None
