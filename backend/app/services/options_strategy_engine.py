"""
AI-QROS — Options Strategy Engine
Phase 17: Options Strategy Engine

Selects the optimal options trading strategy based on daily consolidated signals, 
prediction confidence, implied volatility percentile (IV Rank), and days to expiry (DTE).
"""

import time
from datetime import datetime, date
from typing import Optional, List, Dict
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.signal import TradeSignal
from app.models.feature_store import ComputedFeatureStore

logger = structlog.get_logger("aiqros.services.options_strategy_engine")


def select_options_strategy(
    symbol: str,
    signal_type: str,
    direction: str,
    confidence: float,
    iv_percentile: float,
    dte: float
) -> Dict:
    """
    Core strategy selection matrix.
    """
    strategy_name = "NO_TRADE"
    legs = []
    description = "No suitable strategy found for the current market state."
    
    # ── Bullish Signals ──
    if direction == "bullish":
        if iv_percentile < 40.0:
            strategy_name = "LONG_CALL"
            legs = [{"action": "BUY", "option_type": "CE", "strike": "ATM", "qty_ratio": 1}]
            description = "Buy ATM Call options to capitalize on low implied volatility and expected upside."
        else:
            strategy_name = "BULL_CALL_SPREAD"
            legs = [
                {"action": "BUY", "option_type": "CE", "strike": "ATM", "qty_ratio": 1},
                {"action": "SELL", "option_type": "CE", "strike": "OTM_1", "qty_ratio": 1}
            ]
            description = "Buy ATM Call, Sell OTM Call to offset high implied volatility and theta decay."
            
    # ── Bearish Signals ──
    elif direction == "bearish":
        if iv_percentile < 40.0:
            strategy_name = "LONG_PUT"
            legs = [{"action": "BUY", "option_type": "PE", "strike": "ATM", "qty_ratio": 1}]
            description = "Buy ATM Put options to capitalize on low implied volatility and expected downside."
        else:
            strategy_name = "BEAR_PUT_SPREAD"
            legs = [
                {"action": "BUY", "option_type": "PE", "strike": "ATM", "qty_ratio": 1},
                {"action": "SELL", "option_type": "PE", "strike": "OTM_1", "qty_ratio": 1}
            ]
            description = "Buy ATM Put, Sell OTM Put to hedge against high implied volatility and theta decay."
            
    # ── Neutral / Premium Collection Signals ──
    elif direction == "neutral":
        if signal_type == "SHORT_STRADDLE":
            if iv_percentile > 70.0:
                strategy_name = "SHORT_STRADDLE"
                legs = [
                    {"action": "SELL", "option_type": "CE", "strike": "ATM", "qty_ratio": 1},
                    {"action": "SELL", "option_type": "PE", "strike": "ATM", "qty_ratio": 1}
                ]
                description = "Sell ATM Call and Put to collect maximum premium during high IV contraction."
            else:
                strategy_name = "IRON_CONDOR"
                legs = [
                    {"action": "SELL", "option_type": "CE", "strike": "OTM_1", "qty_ratio": 1},
                    {"action": "SELL", "option_type": "PE", "strike": "OTM_1", "qty_ratio": 1},
                    {"action": "BUY", "option_type": "CE", "strike": "OTM_2", "qty_ratio": 1},
                    {"action": "BUY", "option_type": "PE", "strike": "OTM_2", "qty_ratio": 1}
                ]
                description = "Sell OTM Spread to collect premium with capped risk in ranging low-volatility state."

    return {
        "symbol": symbol,
        "strategy": strategy_name,
        "legs": legs,
        "description": description,
        "iv_percentile": iv_percentile,
        "dte": dte
    }


async def generate_options_strategy_recommendation(
    symbol: str,
    trade_date: date,
    db: AsyncSession
) -> Dict:
    """
    Query the daily signal and features, apply the selection matrix,
    and return the chosen strategy configuration.
    """
    # Load daily signal
    sig_q = select(TradeSignal).where(
        and_(TradeSignal.symbol == symbol, TradeSignal.trade_date == trade_date)
    )
    sig_res = await db.execute(sig_q)
    sig = sig_res.scalar_one_or_none()
    if not sig:
        return select_options_strategy(symbol, "NO_TRADE", "neutral", 0.50, 50.0, 5.0)

    # Load features (IV percentile, DTE)
    feat_q = select(ComputedFeatureStore.features).where(
        and_(ComputedFeatureStore.symbol == symbol, ComputedFeatureStore.trade_date == trade_date)
    ).order_by(ComputedFeatureStore.computation_version.desc()).limit(1)
    feat_res = await db.execute(feat_q)
    features = feat_res.scalar_one_or_none() or {}

    iv_percentile = features.get("iv_percentile", 50.0) or 50.0
    dte = features.get("days_to_expiry", 5.0) or 5.0

    strategy = select_options_strategy(
        symbol=symbol,
        signal_type=sig.signal_type,
        direction=sig.direction,
        confidence=sig.confidence_score,
        iv_percentile=iv_percentile,
        dte=dte
    )
    
    logger.info("options_strategy_selected", symbol=symbol, strategy=strategy["strategy"])
    return strategy
