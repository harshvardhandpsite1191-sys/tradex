"""
AI-QROS — Trade Recommendation Engine
Phase 19: Trade Recommendation

Generates exact strike selections, premium entry targets, stop loss parameters,
and risk allocation sizes for recommended options strategy legs.
"""

import time
import math
from datetime import datetime, date
from typing import Optional, List, Dict
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.db.database import AsyncSessionLocal
from app.models.recommendation import TradeRecommendation
from app.models.expiry import ExpiryIntelligence
from app.models.market_data import OHLCVCandle
from app.services.options_strategy_engine import generate_options_strategy_recommendation
from app.services.trade_filter import evaluate_trade_restrictions

logger = structlog.get_logger("aiqros.services.recommendation_engine")

STRIKE_INTERVALS = {
    "NIFTY": 50,
    "BANKNIFTY": 100,
    "SENSEX": 100
}


def round_to_strike(spot: float, symbol: str) -> int:
    """Round index spot price to the nearest standard option strike strike."""
    interval = STRIKE_INTERVALS.get(symbol.upper(), 100)
    return int(round(spot / interval) * interval)


async def get_current_spot(symbol: str, trade_date: date, db: AsyncSession) -> float:
    """Fetch the latest available close/spot price for the index."""
    token_map = {"NIFTY": "26000", "BANKNIFTY": "26009", "SENSEX": "1"}
    token = token_map.get(symbol.upper(), symbol)
    spot_q = select(OHLCVCandle).where(
        and_(
            OHLCVCandle.symbol_token == token,
            OHLCVCandle.interval == "1day",
            OHLCVCandle.timestamp <= datetime.combine(trade_date, datetime.max.time())
        )
    ).order_by(OHLCVCandle.timestamp.desc()).limit(1)
    
    res = await db.execute(spot_q)
    row = res.scalar_one_or_none()
    return row.close if row else 22000.0


async def generate_daily_recommendation_for_symbol(
    symbol: str,
    trade_date: date,
    db: AsyncSession
) -> Optional[TradeRecommendation]:
    """
    Produce the final actionable options recommendation by joining Phase 17, 18, and strike mapping.
    """
    # 1. Generate Strategy (Phase 17)
    raw_strategy = await generate_options_strategy_recommendation(symbol, trade_date, db)
    
    # 2. Filter Strategy (Phase 18)
    filtered_strategy = evaluate_trade_restrictions(symbol, trade_date, raw_strategy)
    
    strategy_name = filtered_strategy["strategy"]
    if strategy_name == "NO_TRADE":
        return None

    # 3. Calculate Spot and Strikes
    spot = await get_current_spot(symbol, trade_date, db)
    atm_strike = round_to_strike(spot, symbol)
    interval = STRIKE_INTERVALS.get(symbol, 100)

    # Resolve legs to exact strikes
    legs = []
    total_premium_estimate = 0.0
    
    # Fetch near expiry string
    exp_q = select(ExpiryIntelligence).where(
        and_(ExpiryIntelligence.symbol == symbol, ExpiryIntelligence.trade_date == trade_date)
    ).order_by(desc(ExpiryIntelligence.created_at)).limit(1)
    exp_res = await db.execute(exp_q)
    exp_row = exp_res.scalar_one_or_none()
    expiry_date_str = exp_row.expiry_date if exp_row else "Current Expiry"

    for leg in filtered_strategy["legs"]:
        action = leg["action"]
        opt_type = leg["option_type"]
        strike_code = leg["strike"]
        qty = leg["qty_ratio"]
        
        # Strike mapping
        if strike_code == "ATM":
            exact_strike = atm_strike
        elif strike_code == "OTM_1":
            exact_strike = atm_strike + interval if opt_type == "CE" else atm_strike - interval
        elif strike_code == "OTM_2":
            exact_strike = atm_strike + (interval * 2) if opt_type == "CE" else atm_strike - (interval * 2)
        else:
            exact_strike = atm_strike

        # Mock premium estimates based on delta/Black-Scholes proxies (for UI purposes)
        dist_pct = abs(exact_strike - spot) / spot
        if dist_pct == 0:
            est_premium = (spot * 0.008)  # ATM premium approx 0.8% of index value
        else:
            est_premium = (spot * 0.008) * math.exp(-dist_pct * 30)
            
        legs.append({
            "action": action,
            "option_type": opt_type,
            "strike": int(exact_strike),
            "expiry": expiry_date_str,
            "qty_ratio": qty,
            "estimated_premium": round(est_premium, 2)
        })

    # 4. Stop Loss and Target calculations
    risk_metadata = filtered_strategy.get("risk_metadata", {})
    weight = risk_metadata.get("allocation_multiplier", 1.0)
    
    # Simple risk metrics
    if strategy_name in ("LONG_CALL", "LONG_PUT"):
        # Max loss is premium paid
        stop_loss_total = legs[0]["estimated_premium"] * 0.40  # 40% loss on premium
        target_total = legs[0]["estimated_premium"] * 0.60     # 60% gain target
        rr_ratio = 1.5
    else:
        # Spreads and credit sellers
        stop_loss_total = 30.0  # Points on index representation
        target_total = 40.0
        rr_ratio = 1.33

    reco_entry = TradeRecommendation(
        trade_date=trade_date,
        symbol=symbol,
        strategy_name=strategy_name,
        legs_detail={"legs": legs, "spot_price": spot, "expiry": expiry_date_str},
        stop_loss_total=round(stop_loss_total, 2),
        target_total=round(target_total, 2),
        risk_reward_ratio=rr_ratio,
        allocation_weight=weight,
        status="pending",
        details={
            "risk_metadata": risk_metadata,
            "description": filtered_strategy.get("description")
        }
    )

    stmt = select(TradeRecommendation).where(
        and_(
            TradeRecommendation.symbol == symbol,
            TradeRecommendation.trade_date == trade_date,
            TradeRecommendation.strategy_name == strategy_name
        )
    )
    existing = await db.execute(stmt)
    row = existing.scalar_one_or_none()

    if row:
        row.legs_detail = reco_entry.legs_detail
        row.stop_loss_total = reco_entry.stop_loss_total
        row.target_total = reco_entry.target_total
        row.risk_reward_ratio = reco_entry.risk_reward_ratio
        row.allocation_weight = reco_entry.allocation_weight
        row.details = reco_entry.details
        return row
    else:
        db.add(reco_entry)
        return reco_entry


async def run_daily_recommendations(trade_date: Optional[date] = None) -> dict:
    """Trigger daily trade recommendations across targets."""
    td = trade_date or date.today()
    results = {}
    async with AsyncSessionLocal() as db:
        for symbol in ["NIFTY", "BANKNIFTY"]:
            try:
                entry = await generate_daily_recommendation_for_symbol(symbol, td, db)
                if entry:
                    results[symbol] = {
                        "strategy": entry.strategy_name,
                        "weight": entry.allocation_weight,
                        "target": entry.target_total,
                        "stop_loss": entry.stop_loss_total
                    }
                else:
                    results[symbol] = {"status": "NO_TRADE"}
            except Exception as e:
                logger.error("recommendation_failed", symbol=symbol, error=str(e))
                results[symbol] = {"status": "failed", "error": str(e)}
        await db.commit()
    return {"status": "success", "trade_date": str(td), "recommendations": results}
