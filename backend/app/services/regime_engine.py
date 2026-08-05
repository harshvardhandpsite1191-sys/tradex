"""
AI-QROS — Advanced Regime Classification Engine
Phase 10: Market Regime Engine

Implements ML-based and heuristic-based multi-timeframe regime classification.
Uses:
 1. GMM (Gaussian Mixture Model) clustering from scikit-learn on normalized features (ADX, Volatility, Returns).
 2. Rule-based heuristic verification for trend strength, volatility state, and options regime.
 3. Stored in `MarketRegime` table.
"""

import time
import math
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Tuple
import structlog
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.db.database import AsyncSessionLocal
from app.models.behaviour import MarketRegime
from app.models.feature_store import ComputedFeatureStore

logger = structlog.get_logger("aiqros.services.regime_engine")

TARGET_SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]


def _classify_volatility(iv: Optional[float], historical_vol: Optional[float]) -> str:
    """Helper to classify volatility state."""
    vol = iv if iv is not None else (historical_vol if historical_vol is not None else 0.15)
    if vol > 0.28:
        return "extreme"
    elif vol > 0.20:
        return "high"
    elif vol > 0.12:
        return "normal"
    return "low"


def _determine_options_regime(
    regime: str, volatility_state: str, features: Dict[str, Any]
) -> str:
    """Helper to determine optimal options regime classification."""
    pcr = features.get("pcr_oi", 1.0) or 1.0
    iv_pct = features.get("iv_percentile", 50.0) or 50.0
    
    if volatility_state in ("high", "extreme") and iv_pct > 80:
        return "iv_contraction"  # Great for selling options (high IV crush likelihood)
    if regime == "low_vol_squeeze":
        return "iv_expansion"   # Great for buying options before breakout
    if regime in ("trending_up", "trending_down") and volatility_state == "normal":
        if pcr > 1.3 or pcr < 0.7:
            return "gamma_squeeze"
        return "theta_decay"
    return "neutral"


async def classify_market_regime(
    symbol: str,
    trade_date: date,
    db: AsyncSession
) -> Optional[MarketRegime]:
    """
    Classify regime for a single symbol using features and historical data.
    Uses GMM clustering fallback to heuristics.
    """
    # 1. Fetch historical feature store data for fitting/normalization (last 120 trading days)
    cutoff = trade_date - timedelta(days=180)
    result = await db.execute(
        select(ComputedFeatureStore.features)
        .where(and_(
            ComputedFeatureStore.symbol == symbol,
            ComputedFeatureStore.trade_date >= cutoff,
            ComputedFeatureStore.trade_date <= trade_date
        ))
        .order_by(ComputedFeatureStore.trade_date.asc())
    )
    rows = result.scalars().all()
    if not rows:
        logger.warn("no_features_found_for_regime_classification", symbol=symbol, trade_date=str(trade_date))
        return None

    # Load current features
    current_features = rows[-1]
    
    # Heuristics setup
    adx = current_features.get("adx_14", 20.0) or 20.0
    rsi = current_features.get("rsi_14", 50.0) or 50.0
    bb_bw = current_features.get("bb_20_bandwidth", 0.05) or 0.05
    close = current_features.get("price_close") or current_features.get("close", 0.0)
    sma_200 = current_features.get("sma_200") or close
    hist_vol = current_features.get("hist_vol_20", 0.15) or 0.15
    iv = current_features.get("implied_vol", 0.15) or 0.15

    # 2. Extract arrays for clustering: ADX, Volatility, Returns
    data_list = []
    for r in rows:
        r_adx = r.get("adx_14", 20.0) or 20.0
        r_vol = r.get("bb_20_bandwidth", 0.05) or 0.05
        r_ret = r.get("price_daily_return") or r.get("daily_return", 0.0)
        data_list.append([r_adx, r_vol, r_ret])

    # Fallback to rules if data is sparse
    regime = "ranging"
    sub_regime = "mean_revert"
    confidence = 0.50

    if len(data_list) >= 30:
        try:
            X = np.array(data_list)
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            
            # Fit GMM with 4 regimes (Trending Up, Trending Down, Ranging, Volatile/Squeeze)
            gmm = GaussianMixture(n_components=4, random_state=42, max_iter=100)
            gmm.fit(X_scaled)
            
            probs = gmm.predict_proba(X_scaled[-1:])[0]
            cluster = int(np.argmax(probs))
            confidence = float(np.max(probs))
            
            # Label cluster based on centroids
            means = scaler.inverse_transform(gmm.means_)
            # Means columns: 0=ADX, 1=Volatility Bandwidth, 2=Return
            c_adx, c_vol, c_ret = means[cluster]
            
            if c_adx > 25.0:
                if c_ret > 0.0:
                    regime = "trending_up"
                    sub_regime = "strong_trend" if adx > 35 else "weak_trend"
                else:
                    regime = "trending_down"
                    sub_regime = "strong_trend" if adx > 35 else "weak_trend"
            elif c_vol < 0.03:
                regime = "low_vol_squeeze"
                sub_regime = "expansion"
            elif c_vol > 0.08:
                regime = "volatile"
                sub_regime = "breakout"
            else:
                regime = "ranging"
                sub_regime = "mean_revert"
                
        except Exception as ex:
            logger.error("gmm_regime_classification_failed_using_heuristics", error=str(ex))

    # Apply deterministic override overrides if metrics are at extremes
    if adx < 15.0 and bb_bw < 0.025:
        regime = "low_vol_squeeze"
        sub_regime = "expansion"
    elif adx > 30.0:
        if close > sma_200:
            regime = "trending_up"
            sub_regime = "strong_trend" if adx > 40 else "weak_trend"
        else:
            regime = "trending_down"
            sub_regime = "strong_trend" if adx > 40 else "weak_trend"

    vol_state = _classify_volatility(iv, hist_vol)
    opt_regime = _determine_options_regime(regime, vol_state, current_features)

    # Upsert the market regime entry
    regime_entry = MarketRegime(
        trade_date=trade_date,
        symbol=symbol,
        regime=regime,
        sub_regime=sub_regime,
        trend_strength=float(adx),
        volatility_state=vol_state,
        options_regime=opt_regime,
        confidence=confidence,
        details={
            "adx": adx,
            "rsi": rsi,
            "bb_bandwidth": bb_bw,
            "vol_state": vol_state,
            "options_regime": opt_regime,
            "gmm_confidence": confidence
        }
    )
    
    # Database merge operation
    stmt = select(MarketRegime).where(and_(MarketRegime.symbol == symbol, MarketRegime.trade_date == trade_date))
    existing = await db.execute(stmt)
    row = existing.scalar_one_or_none()
    
    if row:
        row.regime = regime
        row.sub_regime = sub_regime
        row.trend_strength = float(adx)
        row.volatility_state = vol_state
        row.options_regime = opt_regime
        row.confidence = confidence
        row.details = regime_entry.details
        row.classified_at = datetime.utcnow()
        return row
    else:
        db.add(regime_entry)
        return regime_entry


async def run_daily_regime_classification(
    trade_date: Optional[date] = None
) -> dict:
    """Classify regimes for all target symbols."""
    td = trade_date or date.today()
    results = {}
    
    async with AsyncSessionLocal() as db:
        for symbol in TARGET_SYMBOLS:
            try:
                entry = await classify_market_regime(symbol, td, db)
                if entry:
                    results[symbol] = {
                        "regime": entry.regime,
                        "sub_regime": entry.sub_regime,
                        "volatility_state": entry.volatility_state,
                        "options_regime": entry.options_regime
                    }
            except Exception as e:
                logger.error("regime_classification_failed", symbol=symbol, error=str(e))
                results[symbol] = {"status": "failed", "error": str(e)}
        await db.commit()
        
    return {
        "status": "success",
        "trade_date": str(td),
        "classifications": results
    }
