"""
AI-QROS — Behaviour Extraction Engine
Phase 5: Market Behaviour Detection

Detects institutional behaviours, market structure patterns, and regime
classifications from computed features (Phase 4) and raw market data.

Detection Categories:
 1. REGIME     — Market regime classification (trending, ranging, volatile)
 2. STRUCTURE  — ICT/SMC patterns: CHoCH, BOS, FVG, Order Blocks
 3. LIQUIDITY  — Liquidity sweeps, stop hunts, equal highs/lows
 4. OPTIONS    — OI buildup, IV crush, gamma squeeze, expiry pinning
 5. VOLUME     — Volume anomalies, absorption, exhaustion
 6. INSTITUTIONAL — FII/DII flow patterns, smart money divergence

Each detector returns a list of detected behaviour dicts.
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
from app.models.market_data import OHLCVCandle, OptionSettlement
from app.models.feature_store import ComputedFeatureStore
from app.models.behaviour import DetectedBehaviour, MarketRegime, BehaviourExtractionLog

logger = structlog.get_logger("aiqros.services.behaviour_engine")

TARGET_SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]
SYMBOL_MAP = {"NIFTY": "26000", "BANKNIFTY": "26009", "SENSEX": "1"}


def _safe(val):
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return round(float(val), 6)
    if isinstance(val, (np.bool_,)):
        return bool(val)
    return val


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

async def _load_features(db: AsyncSession, symbol: str, trade_date: date) -> Optional[dict]:
    """Load computed features for a symbol/date from Phase 4 feature store."""
    result = await db.execute(
        select(ComputedFeatureStore.features)
        .where(and_(
            ComputedFeatureStore.symbol == symbol,
            ComputedFeatureStore.trade_date == trade_date,
        ))
        .order_by(ComputedFeatureStore.computation_version.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row if row else None


async def _load_ohlcv_series(db: AsyncSession, symbol: str, trade_date: date, days: int = 60) -> pd.DataFrame:
    """Load recent OHLCV candle data for pattern detection."""
    token = SYMBOL_MAP.get(symbol, symbol)
    start = trade_date - timedelta(days=days * 2)

    result = await db.execute(
        select(OHLCVCandle)
        .where(and_(
            OHLCVCandle.symbol_token == token,
            OHLCVCandle.interval == "1day",
            OHLCVCandle.timestamp >= datetime.combine(start, datetime.min.time()),
            OHLCVCandle.timestamp <= datetime.combine(trade_date, datetime.max.time()),
        ))
        .order_by(OHLCVCandle.timestamp.asc())
    )
    rows = result.scalars().all()
    if not rows:
        return pd.DataFrame()

    return pd.DataFrame([{
        "timestamp": r.timestamp, "open": r.open, "high": r.high,
        "low": r.low, "close": r.close, "volume": r.volume or 0,
    } for r in rows]).astype({"open": "float32", "high": "float32",
                              "low": "float32", "close": "float32", "volume": "float32"})


async def _load_options_data(db: AsyncSession, symbol: str, trade_date: date) -> pd.DataFrame:
    """Load option settlements for behaviour analysis."""
    result = await db.execute(
        select(OptionSettlement)
        .where(and_(
            OptionSettlement.underlying == symbol,
            OptionSettlement.trade_date == trade_date,
        ))
    )
    rows = result.scalars().all()
    if not rows:
        return pd.DataFrame()

    return pd.DataFrame([{
        "strike": r.strike, "option_type": r.option_type,
        "expiry_date": r.expiry_date, "open": r.open, "high": r.high,
        "low": r.low, "close": r.close, "oi": r.oi or 0,
        "change_oi": r.change_oi or 0, "contracts": r.contracts or 0,
    } for r in rows])


# ═══════════════════════════════════════════════════════════════
# 1. REGIME DETECTION
# ═══════════════════════════════════════════════════════════════

def detect_regime(features: dict, df: pd.DataFrame) -> tuple[dict, list[dict]]:
    """
    Classify market regime from computed features.
    Returns (regime_dict, list_of_behaviour_events).
    """
    behaviours = []

    adx = features.get("adx_14")
    rsi = features.get("rsi_14")
    bb_bw = features.get("bb_20_bandwidth")
    vol_ratio = features.get("vol_ratio_5_20")
    sma_cross = features.get("sma_50_200_cross")
    macd_cross = features.get("macd_cross")
    close = features.get("price_close")
    sma_200 = features.get("sma_200")

    # Trend direction
    trend_up = (sma_cross == 1) if sma_cross else None
    price_above_200 = (close > sma_200) if close and sma_200 else None

    # Regime classification
    if adx and adx > 25:
        if trend_up or price_above_200:
            regime = "trending_up"
            sub = "strong_trend" if adx > 40 else "weak_trend"
        else:
            regime = "trending_down"
            sub = "strong_trend" if adx > 40 else "weak_trend"
    elif bb_bw and bb_bw < 0.03:
        regime = "low_vol_squeeze"
        sub = "expansion_pending"
    elif vol_ratio and vol_ratio > 1.5:
        regime = "volatile"
        sub = "expansion"
    else:
        regime = "ranging"
        sub = "mean_revert"

    # Volatility state
    hv_20 = features.get("hist_vol_20d")
    if hv_20:
        if hv_20 > 25:
            vol_state = "extreme"
        elif hv_20 > 18:
            vol_state = "high"
        elif hv_20 > 10:
            vol_state = "normal"
        else:
            vol_state = "low"
    else:
        vol_state = None

    # Options regime
    iv_proxy = features.get("atm_iv_proxy")
    pcr = features.get("pcr_oi")
    if iv_proxy and iv_proxy > 1.5:
        options_regime = "iv_expansion"
    elif iv_proxy and iv_proxy < 0.8:
        options_regime = "iv_contraction"
    elif pcr and pcr > 1.3:
        options_regime = "put_heavy"
    elif pcr and pcr < 0.7:
        options_regime = "call_heavy"
    else:
        options_regime = "neutral"

    confidence = min(1.0, (adx or 15) / 50 + 0.3)

    regime_data = {
        "regime": regime,
        "sub_regime": sub,
        "trend_strength": _safe(adx),
        "volatility_state": vol_state,
        "options_regime": options_regime,
        "confidence": round(confidence, 2),
        "details": {
            "adx": _safe(adx), "rsi": _safe(rsi),
            "bb_bandwidth": _safe(bb_bw), "vol_ratio": _safe(vol_ratio),
            "sma_cross": _safe(sma_cross), "macd_cross": _safe(macd_cross),
            "hv_20d": _safe(hv_20), "iv_proxy": _safe(iv_proxy),
        },
    }

    behaviours.append({
        "behaviour_type": "MARKET_REGIME",
        "category": "REGIME",
        "confidence": confidence,
        "direction": "bullish" if regime == "trending_up" else "bearish" if regime == "trending_down" else "neutral",
        "description": f"Market regime: {regime} ({sub}). Volatility: {vol_state}. Options: {options_regime}.",
        "details": regime_data["details"],
    })

    return regime_data, behaviours


# ═══════════════════════════════════════════════════════════════
# 2. MARKET STRUCTURE DETECTION (ICT/SMC)
# ═══════════════════════════════════════════════════════════════

def detect_structure_patterns(df: pd.DataFrame) -> list[dict]:
    """Detect CHoCH, BOS, FVG, Order Blocks from OHLCV data."""
    behaviours = []
    if len(df) < 10:
        return behaviours

    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    open_ = df["open"].values

    # --- Break of Structure (BOS) ---
    # Bullish BOS: current high breaks above previous swing high
    # Find swing highs (higher than both neighbors)
    for i in range(2, len(df) - 1):
        if high[i - 1] > high[i - 2] and high[i - 1] > high[i]:
            # Swing high at i-1
            if high[-1] > high[i - 1]:
                behaviours.append({
                    "behaviour_type": "BOS",
                    "category": "STRUCTURE",
                    "confidence": 0.7,
                    "direction": "bullish",
                    "description": f"Break of Structure: price broke above swing high {high[i-1]:.2f}",
                    "details": {"swing_high": _safe(high[i - 1]), "break_price": _safe(high[-1])},
                })
                break  # Only report most recent

    for i in range(2, len(df) - 1):
        if low[i - 1] < low[i - 2] and low[i - 1] < low[i]:
            if low[-1] < low[i - 1]:
                behaviours.append({
                    "behaviour_type": "BOS",
                    "category": "STRUCTURE",
                    "confidence": 0.7,
                    "direction": "bearish",
                    "description": f"Break of Structure: price broke below swing low {low[i-1]:.2f}",
                    "details": {"swing_low": _safe(low[i - 1]), "break_price": _safe(low[-1])},
                })
                break

    # --- Change of Character (CHoCH) ---
    # Detect trend reversal: series of HH/HL breaks into LL/LH or vice versa
    if len(df) >= 5:
        recent_highs = high[-5:]
        recent_lows = low[-5:]
        hh_count = sum(1 for i in range(1, len(recent_highs)) if recent_highs[i] > recent_highs[i - 1])
        ll_count = sum(1 for i in range(1, len(recent_lows)) if recent_lows[i] < recent_lows[i - 1])

        if hh_count >= 3 and close[-1] < low[-2]:
            behaviours.append({
                "behaviour_type": "CHOCH",
                "category": "STRUCTURE",
                "confidence": 0.75,
                "direction": "bearish",
                "description": "Change of Character: uptrend broken — close below prior low after higher highs",
                "details": {"hh_count": hh_count, "break_level": _safe(low[-2])},
            })
        elif ll_count >= 3 and close[-1] > high[-2]:
            behaviours.append({
                "behaviour_type": "CHOCH",
                "category": "STRUCTURE",
                "confidence": 0.75,
                "direction": "bullish",
                "description": "Change of Character: downtrend broken — close above prior high after lower lows",
                "details": {"ll_count": ll_count, "break_level": _safe(high[-2])},
            })

    # --- Fair Value Gap (FVG) Detection ---
    # Bullish FVG: candle[i-2].high < candle[i].low (gap up)
    # Bearish FVG: candle[i-2].low > candle[i].high (gap down)
    if len(df) >= 3:
        i = len(df) - 1
        if low[i] > high[i - 2]:
            gap_size = low[i] - high[i - 2]
            behaviours.append({
                "behaviour_type": "FVG_DETECTION",
                "category": "STRUCTURE",
                "confidence": 0.65,
                "direction": "bullish",
                "description": f"Bullish Fair Value Gap detected: {high[i-2]:.2f} to {low[i]:.2f}",
                "details": {"fvg_top": _safe(low[i]), "fvg_bottom": _safe(high[i - 2]),
                            "gap_size": _safe(gap_size)},
            })
        elif high[i] < low[i - 2]:
            gap_size = low[i - 2] - high[i]
            behaviours.append({
                "behaviour_type": "FVG_DETECTION",
                "category": "STRUCTURE",
                "confidence": 0.65,
                "direction": "bearish",
                "description": f"Bearish Fair Value Gap detected: {high[i]:.2f} to {low[i-2]:.2f}",
                "details": {"fvg_top": _safe(low[i - 2]), "fvg_bottom": _safe(high[i]),
                            "gap_size": _safe(gap_size)},
            })

    # --- Order Block Detection ---
    # Bullish OB: last bearish candle before a strong bullish move
    if len(df) >= 4:
        for j in range(len(df) - 2, max(len(df) - 6, 0), -1):
            is_bearish = close[j] < open_[j]
            bullish_follow = close[j + 1] > high[j]
            if is_bearish and bullish_follow:
                behaviours.append({
                    "behaviour_type": "ORDER_BLOCK",
                    "category": "STRUCTURE",
                    "confidence": 0.6,
                    "direction": "bullish",
                    "description": f"Bullish Order Block at {low[j]:.2f}-{high[j]:.2f}",
                    "details": {"ob_high": _safe(high[j]), "ob_low": _safe(low[j])},
                })
                break

        for j in range(len(df) - 2, max(len(df) - 6, 0), -1):
            is_bullish = close[j] > open_[j]
            bearish_follow = close[j + 1] < low[j]
            if is_bullish and bearish_follow:
                behaviours.append({
                    "behaviour_type": "ORDER_BLOCK",
                    "category": "STRUCTURE",
                    "confidence": 0.6,
                    "direction": "bearish",
                    "description": f"Bearish Order Block at {low[j]:.2f}-{high[j]:.2f}",
                    "details": {"ob_high": _safe(high[j]), "ob_low": _safe(low[j])},
                })
                break

    return behaviours


# ═══════════════════════════════════════════════════════════════
# 3. LIQUIDITY PATTERN DETECTION
# ═══════════════════════════════════════════════════════════════

def detect_liquidity_patterns(df: pd.DataFrame, features: dict) -> list[dict]:
    """Detect liquidity sweeps, stop hunts, equal highs/lows."""
    behaviours = []
    if len(df) < 10:
        return behaviours

    high = df["high"].values
    low = df["low"].values
    close = df["close"].values

    # --- Equal Highs (EQH) Detection ---
    # Two or more recent highs within 0.1% of each other
    tolerance = 0.001
    for i in range(len(df) - 5, len(df) - 1):
        for j in range(i + 1, len(df)):
            if abs(high[i] - high[j]) / high[i] < tolerance and i != j:
                behaviours.append({
                    "behaviour_type": "LIQUIDITY_SWEEP",
                    "category": "LIQUIDITY",
                    "confidence": 0.6,
                    "direction": "neutral",
                    "description": f"Equal Highs detected at ~{high[i]:.2f} — liquidity pool above",
                    "details": {"eqh_level": _safe(high[i]),
                                "is_swept": _safe(high[-1] > high[i] * 1.001)},
                })
                break
        else:
            continue
        break

    # --- Equal Lows (EQL) Detection ---
    for i in range(len(df) - 5, len(df) - 1):
        for j in range(i + 1, len(df)):
            if abs(low[i] - low[j]) / low[i] < tolerance and i != j:
                behaviours.append({
                    "behaviour_type": "LIQUIDITY_SWEEP",
                    "category": "LIQUIDITY",
                    "confidence": 0.6,
                    "direction": "neutral",
                    "description": f"Equal Lows detected at ~{low[i]:.2f} — liquidity pool below",
                    "details": {"eql_level": _safe(low[i]),
                                "is_swept": _safe(low[-1] < low[i] * 0.999)},
                })
                break
        else:
            continue
        break

    # --- Stop Hunt Detection ---
    # Price exceeds prior day high/low but closes back inside range
    if len(df) >= 2:
        prev_high = high[-2]
        prev_low = low[-2]
        curr_high = high[-1]
        curr_low = low[-1]
        curr_close = close[-1]

        if curr_high > prev_high and curr_close < prev_high:
            behaviours.append({
                "behaviour_type": "STOP_HUNT",
                "category": "LIQUIDITY",
                "confidence": 0.7,
                "direction": "bearish",
                "description": f"Stop hunt above {prev_high:.2f} — swept highs then closed below",
                "details": {"swept_level": _safe(prev_high), "sweep_high": _safe(curr_high),
                            "close": _safe(curr_close)},
            })

        if curr_low < prev_low and curr_close > prev_low:
            behaviours.append({
                "behaviour_type": "STOP_HUNT",
                "category": "LIQUIDITY",
                "confidence": 0.7,
                "direction": "bullish",
                "description": f"Stop hunt below {prev_low:.2f} — swept lows then closed above",
                "details": {"swept_level": _safe(prev_low), "sweep_low": _safe(curr_low),
                            "close": _safe(curr_close)},
            })

    return behaviours


# ═══════════════════════════════════════════════════════════════
# 4. OPTIONS BEHAVIOUR DETECTION
# ═══════════════════════════════════════════════════════════════

def detect_options_behaviours(features: dict, df_options: pd.DataFrame) -> list[dict]:
    """Detect OI buildup, IV crush, gamma squeeze, expiry pinning signals."""
    behaviours = []

    # --- OI Buildup ---
    ce_oi_change = features.get("ce_oi_change")
    pe_oi_change = features.get("pe_oi_change")
    daily_return = features.get("price_daily_return")

    if ce_oi_change is not None and pe_oi_change is not None:
        if ce_oi_change > 0 and daily_return and daily_return > 0:
            behaviours.append({
                "behaviour_type": "OI_BUILDUP",
                "category": "OPTIONS",
                "confidence": 0.7,
                "direction": "bullish",
                "description": f"Long buildup: CE OI +{ce_oi_change}, price up {daily_return:.2f}%",
                "details": {"ce_oi_change": _safe(ce_oi_change), "pe_oi_change": _safe(pe_oi_change),
                            "return": _safe(daily_return)},
            })
        elif pe_oi_change > 0 and daily_return and daily_return < 0:
            behaviours.append({
                "behaviour_type": "OI_BUILDUP",
                "category": "OPTIONS",
                "confidence": 0.7,
                "direction": "bearish",
                "description": f"Short buildup: PE OI +{pe_oi_change}, price down {daily_return:.2f}%",
                "details": {"ce_oi_change": _safe(ce_oi_change), "pe_oi_change": _safe(pe_oi_change),
                            "return": _safe(daily_return)},
            })

    # --- Short Covering ---
    if ce_oi_change and ce_oi_change < 0 and daily_return and daily_return > 0.5:
        behaviours.append({
            "behaviour_type": "SHORT_COVERING",
            "category": "OPTIONS",
            "confidence": 0.65,
            "direction": "bullish",
            "description": f"Short covering rally: CE OI decreased {ce_oi_change}, price up {daily_return:.2f}%",
            "details": {"ce_oi_change": _safe(ce_oi_change), "return": _safe(daily_return)},
        })

    # --- Long Unwinding ---
    if pe_oi_change and pe_oi_change < 0 and daily_return and daily_return < -0.5:
        behaviours.append({
            "behaviour_type": "LONG_UNWINDING",
            "category": "OPTIONS",
            "confidence": 0.65,
            "direction": "bearish",
            "description": f"Long unwinding: PE OI decreased {pe_oi_change}, price down {daily_return:.2f}%",
            "details": {"pe_oi_change": _safe(pe_oi_change), "return": _safe(daily_return)},
        })

    # --- IV Crush Detection ---
    iv_proxy = features.get("atm_iv_proxy")
    dte = features.get("days_to_expiry")
    straddle_pct = features.get("straddle_pct_of_spot")
    if iv_proxy and iv_proxy < 0.6 and dte is not None and dte <= 1:
        behaviours.append({
            "behaviour_type": "IV_CRUSH",
            "category": "OPTIONS",
            "confidence": 0.8,
            "direction": "neutral",
            "description": f"IV crush detected: IV proxy {iv_proxy:.2f}, {dte} DTE, straddle {straddle_pct:.2f}% of spot",
            "details": {"iv_proxy": _safe(iv_proxy), "dte": _safe(dte),
                        "straddle_pct": _safe(straddle_pct)},
        })

    # --- Gamma Squeeze ---
    pcr = features.get("pcr_oi")
    oi_concentration = features.get("oi_concentration_ratio")
    if pcr and pcr < 0.5 and oi_concentration and oi_concentration > 0.4:
        behaviours.append({
            "behaviour_type": "GAMMA_SQUEEZE",
            "category": "OPTIONS",
            "confidence": 0.6,
            "direction": "bullish",
            "description": f"Potential gamma squeeze: PCR {pcr:.2f}, OI concentrated {oi_concentration:.2f}",
            "details": {"pcr": _safe(pcr), "oi_concentration": _safe(oi_concentration)},
        })

    # --- Expiry Pinning ---
    max_pain = features.get("max_pain")
    price_close = features.get("price_close")
    if max_pain and price_close and dte is not None and dte <= 1:
        pin_dist = abs(price_close - max_pain) / price_close * 100
        if pin_dist < 0.5:
            behaviours.append({
                "behaviour_type": "EXPIRY_PINNING",
                "category": "OPTIONS",
                "confidence": 0.75,
                "direction": "neutral",
                "description": f"Expiry pinning: price {price_close:.2f} near max pain {max_pain:.2f} ({pin_dist:.2f}% away)",
                "details": {"max_pain": _safe(max_pain), "price": _safe(price_close),
                            "distance_pct": _safe(pin_dist)},
            })

    return behaviours


# ═══════════════════════════════════════════════════════════════
# 5. VOLUME BEHAVIOUR DETECTION
# ═══════════════════════════════════════════════════════════════

def detect_volume_behaviours(features: dict, df: pd.DataFrame) -> list[dict]:
    """Detect volume anomalies, absorption, exhaustion."""
    behaviours = []

    rel_vol = features.get("relative_volume")
    daily_return = features.get("price_daily_return")

    # --- Volume Spike ---
    if rel_vol and rel_vol > 2.0:
        behaviours.append({
            "behaviour_type": "VOLUME_ANOMALY",
            "category": "VOLUME",
            "confidence": 0.7,
            "direction": "bullish" if daily_return and daily_return > 0 else "bearish" if daily_return and daily_return < 0 else "neutral",
            "description": f"Volume spike: {rel_vol:.1f}x average, return {daily_return:.2f}%" if daily_return else f"Volume spike: {rel_vol:.1f}x average",
            "details": {"relative_volume": _safe(rel_vol), "return": _safe(daily_return)},
        })

    # --- Volume Exhaustion ---
    # High volume but small price range = absorption/exhaustion
    range_pct = features.get("price_range_pct")
    if rel_vol and rel_vol > 1.5 and range_pct and range_pct < 0.5:
        behaviours.append({
            "behaviour_type": "VOLUME_ANOMALY",
            "category": "VOLUME",
            "confidence": 0.65,
            "direction": "neutral",
            "description": f"Volume absorption: {rel_vol:.1f}x volume but only {range_pct:.2f}% range — institutional defense",
            "details": {"relative_volume": _safe(rel_vol), "range_pct": _safe(range_pct)},
        })

    # --- Volume Divergence ---
    # Price making new highs but volume declining
    if len(df) >= 5:
        price_trending_up = df["close"].iloc[-1] > df["close"].iloc[-5]
        vol_declining = df["volume"].iloc[-1] < df["volume"].iloc[-5]
        if price_trending_up and vol_declining:
            behaviours.append({
                "behaviour_type": "VOLUME_ANOMALY",
                "category": "VOLUME",
                "confidence": 0.55,
                "direction": "bearish",
                "description": "Volume divergence: price rising but volume declining — weakening momentum",
                "details": {"price_5d_change": _safe(float(df["close"].iloc[-1] - df["close"].iloc[-5])),
                            "vol_5d_change": _safe(float(df["volume"].iloc[-1] - df["volume"].iloc[-5]))},
            })

    return behaviours


# ═══════════════════════════════════════════════════════════════
# 6. INSTITUTIONAL BEHAVIOUR DETECTION
# ═══════════════════════════════════════════════════════════════

def detect_institutional_behaviours(features: dict) -> list[dict]:
    """Detect institutional flow patterns from computed features."""
    behaviours = []

    smart_flow = features.get("smart_money_flow")
    smart_flow_5d = features.get("smart_money_flow_5d")
    acc_dist = features.get("acc_dist_ratio")
    sentiment = features.get("institutional_sentiment")

    # --- Smart Money Accumulation ---
    if smart_flow_5d and smart_flow_5d > 3:
        behaviours.append({
            "behaviour_type": "INSTITUTIONAL_FLOW",
            "category": "INSTITUTIONAL",
            "confidence": 0.7,
            "direction": "bullish",
            "description": f"Smart money accumulation detected: 5-day flow score {smart_flow_5d:.2f}",
            "details": {"smart_flow_5d": _safe(smart_flow_5d), "acc_dist_ratio": _safe(acc_dist)},
        })

    # --- Smart Money Distribution ---
    if smart_flow_5d and smart_flow_5d < -3:
        behaviours.append({
            "behaviour_type": "INSTITUTIONAL_FLOW",
            "category": "INSTITUTIONAL",
            "confidence": 0.7,
            "direction": "bearish",
            "description": f"Smart money distribution detected: 5-day flow score {smart_flow_5d:.2f}",
            "details": {"smart_flow_5d": _safe(smart_flow_5d), "acc_dist_ratio": _safe(acc_dist)},
        })

    # --- Delivery-based signal ---
    delivery = features.get("delivery_pct_proxy")
    if delivery and delivery > 0.8:
        behaviours.append({
            "behaviour_type": "INSTITUTIONAL_FLOW",
            "category": "INSTITUTIONAL",
            "confidence": 0.6,
            "direction": "bullish",
            "description": f"High delivery proxy {delivery:.2f} — institutional buying pressure",
            "details": {"delivery_proxy": _safe(delivery)},
        })
    elif delivery and delivery < 0.2:
        behaviours.append({
            "behaviour_type": "INSTITUTIONAL_FLOW",
            "category": "INSTITUTIONAL",
            "confidence": 0.6,
            "direction": "bearish",
            "description": f"Low delivery proxy {delivery:.2f} — institutional selling pressure",
            "details": {"delivery_proxy": _safe(delivery)},
        })

    return behaviours


# ═══════════════════════════════════════════════════════════════
# GAP BEHAVIOUR DETECTION
# ═══════════════════════════════════════════════════════════════

def detect_gap_behaviours(features: dict) -> list[dict]:
    """Detect gap-related behaviours."""
    behaviours = []

    gap_pct = features.get("gap_pct")
    gap_filled = features.get("gap_filled")
    gap_dir = features.get("gap_direction")

    if gap_pct and abs(gap_pct) > 0.5:
        behaviours.append({
            "behaviour_type": "GAP_BEHAVIOUR",
            "category": "STRUCTURE",
            "confidence": 0.65,
            "direction": "bullish" if gap_pct > 0 else "bearish",
            "description": f"Significant gap {gap_dir}: {gap_pct:.2f}%, {'filled' if gap_filled else 'unfilled'}",
            "details": {"gap_pct": _safe(gap_pct), "gap_filled": _safe(gap_filled),
                        "gap_direction": gap_dir},
        })

    # Gap and go (unfilled gap with momentum)
    if gap_pct and abs(gap_pct) > 0.3 and not gap_filled:
        daily_return = features.get("price_daily_return")
        if daily_return and np.sign(gap_pct) == np.sign(daily_return):
            behaviours.append({
                "behaviour_type": "GAP_BEHAVIOUR",
                "category": "STRUCTURE",
                "confidence": 0.6,
                "direction": "bullish" if gap_pct > 0 else "bearish",
                "description": f"Gap and Go: unfilled {gap_pct:.2f}% gap with continuation {daily_return:.2f}%",
                "details": {"gap_pct": _safe(gap_pct), "return": _safe(daily_return)},
            })

    return behaviours


# ═══════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

async def extract_behaviours_for_date(
    symbol: str,
    trade_date: date,
    triggered_by: str = "scheduler",
) -> dict:
    """
    Run ALL behaviour detectors for a single symbol on a single trade_date.
    Stores DetectedBehaviour rows and MarketRegime.
    Returns summary dict.
    """
    start_time = time.time()

    async with AsyncSessionLocal() as db:
        log = BehaviourExtractionLog(
            symbol=symbol, trade_date=trade_date,
            status="running", triggered_by=triggered_by,
        )
        db.add(log)
        await db.flush()

        try:
            # Load data
            features = await _load_features(db, symbol, trade_date)
            df = await _load_ohlcv_series(db, symbol, trade_date)
            df_options = await _load_options_data(db, symbol, trade_date)

            if not features:
                log.status = "failed"
                log.error_message = "No computed features found. Run Phase 4 first."
                log.completed_at = datetime.utcnow()
                log.duration_seconds = round(time.time() - start_time, 2)
                await db.commit()
                return {"status": "failed", "symbol": symbol, "error": "No features available"}

            all_behaviours = []
            category_counts = {}

            # 1. Regime detection
            regime_data, regime_behaviours = detect_regime(features, df)
            all_behaviours.extend(regime_behaviours)

            # Store regime
            stmt = pg_insert(MarketRegime).values(
                trade_date=trade_date, symbol=symbol,
                regime=regime_data["regime"], sub_regime=regime_data["sub_regime"],
                trend_strength=regime_data["trend_strength"],
                volatility_state=regime_data["volatility_state"],
                options_regime=regime_data["options_regime"],
                confidence=regime_data["confidence"],
                details=regime_data["details"],
                classified_at=datetime.utcnow(),
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_market_regime",
                set_={
                    "regime": regime_data["regime"],
                    "sub_regime": regime_data["sub_regime"],
                    "trend_strength": regime_data["trend_strength"],
                    "volatility_state": regime_data["volatility_state"],
                    "options_regime": regime_data["options_regime"],
                    "confidence": regime_data["confidence"],
                    "details": regime_data["details"],
                    "classified_at": datetime.utcnow(),
                },
            )
            await db.execute(stmt)

            # 2. Structure patterns
            if not df.empty:
                structure_b = detect_structure_patterns(df)
                all_behaviours.extend(structure_b)

            # 3. Liquidity patterns
            if not df.empty:
                liquidity_b = detect_liquidity_patterns(df, features)
                all_behaviours.extend(liquidity_b)

            # 4. Options behaviours
            options_b = detect_options_behaviours(features, df_options)
            all_behaviours.extend(options_b)

            # 5. Volume behaviours
            if not df.empty:
                volume_b = detect_volume_behaviours(features, df)
                all_behaviours.extend(volume_b)

            # 6. Institutional behaviours
            institutional_b = detect_institutional_behaviours(features)
            all_behaviours.extend(institutional_b)

            # 7. Gap behaviours
            gap_b = detect_gap_behaviours(features)
            all_behaviours.extend(gap_b)

            # Count by category
            for b in all_behaviours:
                cat = b["category"]
                category_counts[cat] = category_counts.get(cat, 0) + 1

            # Store all detected behaviours
            for b in all_behaviours:
                db.add(DetectedBehaviour(
                    trade_date=trade_date,
                    symbol=symbol,
                    behaviour_type=b["behaviour_type"],
                    category=b["category"],
                    confidence=b["confidence"],
                    direction=b.get("direction"),
                    description=b["description"],
                    details=b.get("details"),
                ))

            duration = round(time.time() - start_time, 2)

            log.status = "success"
            log.behaviours_detected = len(all_behaviours)
            log.categories_detected = category_counts
            log.completed_at = datetime.utcnow()
            log.duration_seconds = duration

            await db.commit()

            logger.info(
                "behaviours_extracted", symbol=symbol,
                trade_date=str(trade_date), total=len(all_behaviours),
                categories=category_counts, duration_s=duration,
            )

            return {
                "status": "success",
                "symbol": symbol,
                "trade_date": str(trade_date),
                "behaviours_detected": len(all_behaviours),
                "category_counts": category_counts,
                "regime": regime_data["regime"],
                "duration_seconds": duration,
            }

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)[:500]
            log.completed_at = datetime.utcnow()
            log.duration_seconds = round(time.time() - start_time, 2)
            await db.commit()

            logger.error("behaviour_extraction_failed", symbol=symbol, error=str(e))
            return {"status": "failed", "symbol": symbol, "error": str(e)[:200]}


async def extract_daily_behaviours(
    trade_date: Optional[date] = None,
    triggered_by: str = "scheduler",
) -> dict:
    """Extract behaviours for ALL target symbols for a given date."""
    if trade_date is None:
        trade_date = date.today()

    results = {}
    for symbol in TARGET_SYMBOLS:
        results[symbol] = await extract_behaviours_for_date(symbol, trade_date, triggered_by)

    success = sum(1 for r in results.values() if r.get("status") == "success")
    total_behaviours = sum(r.get("behaviours_detected", 0) for r in results.values())

    return {
        "status": "complete",
        "trade_date": str(trade_date),
        "symbols_processed": len(TARGET_SYMBOLS),
        "symbols_succeeded": success,
        "total_behaviours_detected": total_behaviours,
        "results": results,
    }


async def get_behaviours(
    symbol: Optional[str] = None,
    trade_date: Optional[date] = None,
    category: Optional[str] = None,
    behaviour_type: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Query detected behaviours with filters."""
    async with AsyncSessionLocal() as db:
        query = select(DetectedBehaviour)
        if symbol:
            query = query.where(DetectedBehaviour.symbol == symbol)
        if trade_date:
            query = query.where(DetectedBehaviour.trade_date == trade_date)
        if category:
            query = query.where(DetectedBehaviour.category == category)
        if behaviour_type:
            query = query.where(DetectedBehaviour.behaviour_type == behaviour_type)

        query = query.order_by(DetectedBehaviour.detected_at.desc()).limit(limit)
        result = await db.execute(query)
        rows = result.scalars().all()

        return [{
            "id": r.id, "trade_date": str(r.trade_date), "symbol": r.symbol,
            "behaviour_type": r.behaviour_type, "category": r.category,
            "confidence": r.confidence, "direction": r.direction,
            "description": r.description, "details": r.details,
        } for r in rows]


async def get_regime(symbol: str, trade_date: date) -> Optional[dict]:
    """Get market regime classification for a symbol/date."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MarketRegime).where(and_(
                MarketRegime.symbol == symbol,
                MarketRegime.trade_date == trade_date,
            ))
        )
        r = result.scalar_one_or_none()
        if r:
            return {
                "symbol": r.symbol, "trade_date": str(r.trade_date),
                "regime": r.regime, "sub_regime": r.sub_regime,
                "trend_strength": r.trend_strength,
                "volatility_state": r.volatility_state,
                "options_regime": r.options_regime,
                "confidence": r.confidence, "details": r.details,
            }
        return None
