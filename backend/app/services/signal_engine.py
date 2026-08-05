"""
AI-QROS — Signal Generation Engine
Phase 15: Signal Generation

Synthesises regime classification, opening bias, expiry pain thresholds, 
active scenario triggers, and historical similarity profiles into a single daily directional signal.
"""

import time
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.db.database import AsyncSessionLocal
from app.models.signal import TradeSignal
from app.models.behaviour import MarketRegime
from app.models.opening import OpeningIntelligence
from app.models.expiry import ExpiryIntelligence
from app.models.scenario import MarketScenario
from app.services.similarity_engine import find_similar_dates

logger = structlog.get_logger("aiqros.services.signal_engine")

TARGET_SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]


async def generate_daily_signal_for_symbol(
    symbol: str,
    trade_date: date,
    db: AsyncSession
) -> Optional[TradeSignal]:
    """
    Consolidate metrics from Phase 9-14 and yield a single TradeSignal.
    """
    # 1. Fetch Regime (Phase 10)
    reg_q = select(MarketRegime).where(
        and_(MarketRegime.symbol == symbol, MarketRegime.trade_date == trade_date)
    )
    reg_res = await db.execute(reg_q)
    reg_row = reg_res.scalar_one_or_none()
    regime = reg_row.regime if reg_row else "ranging"
    options_regime = reg_row.options_regime if reg_row else "neutral"

    # 2. Fetch Opening Bias (Phase 11)
    open_q = select(OpeningIntelligence).where(
        and_(OpeningIntelligence.symbol == symbol, OpeningIntelligence.trade_date == trade_date)
    )
    open_res = await db.execute(open_q)
    open_row = open_res.scalar_one_or_none()
    open_bias = open_row.opening_bias if open_row else "neutral"
    expected_gap = open_row.expected_gap_pct if open_row else 0.0

    # 3. Fetch Expiry Pinning & Max Pain (Phase 12)
    exp_q = select(ExpiryIntelligence).where(
        and_(ExpiryIntelligence.symbol == symbol, ExpiryIntelligence.trade_date == trade_date)
    ).order_by(desc(ExpiryIntelligence.created_at)).limit(1)
    exp_res = await db.execute(exp_q)
    exp_row = exp_res.scalar_one_or_none()
    pin_prob = exp_row.pinning_probability if exp_row else 0.0
    max_pain_val = exp_row.max_pain if exp_row else 0.0

    # 4. Fetch Historical Similarity subsequent returns (Phase 14)
    similar_days = await find_similar_dates(symbol, trade_date, db, top_n=3)
    avg_sim_return = sum(d["subsequent_return"] for d in similar_days) / len(similar_days) if similar_days else 0.0

    # 5. Determine Signal Direction & Type
    direction = "neutral"
    signal_type = "NO_TRADE"
    confidence_score = 0.50

    # Score vectors
    bullish_indicators = 0
    bearish_indicators = 0
    neutral_indicators = 0

    if regime == "trending_up":
        bullish_indicators += 2
    elif regime == "trending_down":
        bearish_indicators += 2
    else:
        neutral_indicators += 2

    if open_bias == "bullish":
        bullish_indicators += 1.5
    elif open_bias == "bearish":
        bearish_indicators += 1.5
    else:
        neutral_indicators += 1.0

    if avg_sim_return > 0.001:
        bullish_indicators += 1
    elif avg_sim_return < -0.001:
        bearish_indicators += 1
    else:
        neutral_indicators += 1

    total_indicators = bullish_indicators + bearish_indicators + neutral_indicators

    # Decision Matrix
    if bullish_indicators > bearish_indicators and bullish_indicators > neutral_indicators:
        direction = "bullish"
        signal_type = "BUY_CALL"
        confidence_score = bullish_indicators / total_indicators
    elif bearish_indicators > bullish_indicators and bearish_indicators > neutral_indicators:
        direction = "bearish"
        signal_type = "BUY_PUT"
        confidence_score = bearish_indicators / total_indicators
    else:
        direction = "neutral"
        # If neutral and options regime favors selling, select premium collection strategies
        if options_regime == "iv_contraction" or pin_prob > 0.3:
            signal_type = "SHORT_STRADDLE"
        else:
            signal_type = "NO_TRADE"
        confidence_score = max(0.50, neutral_indicators / total_indicators)

    # 6. Save TradeSignal
    signal_entry = TradeSignal(
        trade_date=trade_date,
        symbol=symbol,
        signal_type=signal_type,
        direction=direction,
        confidence_score=round(float(confidence_score), 4),
        contributing_factors={
            "regime": regime,
            "options_regime": options_regime,
            "opening_bias": open_bias,
            "expected_gap_pct": expected_gap,
            "avg_similarity_return": avg_sim_return,
            "pinning_probability": pin_prob,
            "max_pain": max_pain_val
        }
    )

    stmt = select(TradeSignal).where(
        and_(
            TradeSignal.symbol == symbol,
            TradeSignal.trade_date == trade_date
        )
    )
    existing = await db.execute(stmt)
    row = existing.scalar_one_or_none()

    if row:
        row.signal_type = signal_type
        row.direction = direction
        row.confidence_score = signal_entry.confidence_score
        row.contributing_factors = signal_entry.contributing_factors
        return row
    else:
        db.add(signal_entry)
        return signal_entry


async def run_daily_signal_generation(trade_date: Optional[date] = None) -> dict:
    """Run daily signal generation job for all targets."""
    td = trade_date or date.today()
    results = {}
    async with AsyncSessionLocal() as db:
        for symbol in TARGET_SYMBOLS:
            try:
                entry = await generate_daily_signal_for_symbol(symbol, td, db)
                if entry:
                    results[symbol] = {
                        "signal": entry.signal_type,
                        "direction": entry.direction,
                        "confidence": entry.confidence_score
                    }
            except Exception as e:
                logger.error("signal_generation_failed", symbol=symbol, error=str(e))
                results[symbol] = {"status": "failed", "error": str(e)}
        await db.commit()
    return {"status": "success", "trade_date": str(td), "signals": results}
