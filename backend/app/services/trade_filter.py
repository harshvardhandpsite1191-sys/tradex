"""
AI-QROS — Trade Filter Engine
Phase 18: Trade Filter

Filters proposed options strategies based on risk boundaries, macro events,
and high-volatility regime flags.
"""

import time
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.feature_store import ComputedFeatureStore

logger = structlog.get_logger("aiqros.services.trade_filter")

# Mock event database dictionary for risk scheduling
MACRO_EVENTS = {
    # Format: "YYYY-MM-DD": "EVENT_NAME"
    "2026-02-01": "UNION_BUDGET",
    "2026-06-05": "RBI_RATE_DECISION",
    "2026-09-15": "US_FOMC_MEETING",
    "2026-11-03": "US_PRESIDENTIAL_ELECTION"
}


def evaluate_trade_restrictions(
    symbol: str,
    trade_date: date,
    strategy: Dict
) -> Dict:
    """
    Applies event and volatility filters to the proposed strategy.
    """
    strategy_name = strategy.get("strategy", "NO_TRADE")
    legs = strategy.get("legs", [])
    filtered_strategy = strategy.copy()
    
    # 1. Macro Calendar Checks
    # Check if there is a major event tomorrow or day after
    event_days = [trade_date + timedelta(days=i) for i in range(3)]
    active_event = None
    for d in event_days:
        date_str = str(d)
        if date_str in MACRO_EVENTS:
            active_event = MACRO_EVENTS[date_str]
            break

    caution_flags = []
    allocation_multiplier = 1.0

    if active_event:
        caution_flags.append(f"HIGH_IMPACT_EVENT_NEAR: {active_event}")
        # High impact events force lower risk allocation and block naked options buys
        allocation_multiplier = 0.5
        
        if strategy_name in ("LONG_CALL", "LONG_PUT", "SHORT_STRADDLE"):
            # Naked buys/sells blocked; convert to capped risk spreads
            logger.info("filtering_strategy_due_to_macro_event", event=active_event, original=strategy_name)
            if "CALL" in strategy_name or "CE" in str(legs):
                filtered_strategy["strategy"] = "BULL_CALL_SPREAD"
                filtered_strategy["legs"] = [
                    {"action": "BUY", "option_type": "CE", "strike": "ATM", "qty_ratio": 1},
                    {"action": "SELL", "option_type": "CE", "strike": "OTM_1", "qty_ratio": 1}
                ]
                filtered_strategy["description"] = f"Bull Call Spread (Risk Capped) — modified due to near-term event: {active_event}."
            elif "PUT" in strategy_name or "PE" in str(legs):
                filtered_strategy["strategy"] = "BEAR_PUT_SPREAD"
                filtered_strategy["legs"] = [
                    {"action": "BUY", "option_type": "PE", "strike": "ATM", "qty_ratio": 1},
                    {"action": "SELL", "option_type": "PE", "strike": "OTM_1", "qty_ratio": 1}
                ]
                filtered_strategy["description"] = f"Bear Put Spread (Risk Capped) — modified due to near-term event: {active_event}."
            else:
                # Straddle converted to Iron Condor (capped risk)
                filtered_strategy["strategy"] = "IRON_CONDOR"
                filtered_strategy["legs"] = [
                    {"action": "SELL", "option_type": "CE", "strike": "OTM_1", "qty_ratio": 1},
                    {"action": "SELL", "option_type": "PE", "strike": "OTM_1", "qty_ratio": 1},
                    {"action": "BUY", "option_type": "CE", "strike": "OTM_2", "qty_ratio": 1},
                    {"action": "BUY", "option_type": "PE", "strike": "OTM_2", "qty_ratio": 1}
                ]
                filtered_strategy["description"] = f"Iron Condor (Risk Capped) — modified due to near-term event: {active_event}."

    # 2. VIX / Volatility Filter
    iv_pct = strategy.get("iv_percentile", 50.0)
    if iv_pct > 85.0:
        caution_flags.append("EXTREME_IV_PERCENTILE")
        allocation_multiplier = min(allocation_multiplier, 0.7)
        if filtered_strategy["strategy"] == "LONG_CALL":
            filtered_strategy["strategy"] = "BULL_CALL_SPREAD"
            filtered_strategy["description"] += " (Modified to Spread: High IV)"
        elif filtered_strategy["strategy"] == "LONG_PUT":
            filtered_strategy["strategy"] = "BEAR_PUT_SPREAD"
            filtered_strategy["description"] += " (Modified to Spread: High IV)"

    filtered_strategy["risk_metadata"] = {
        "allocation_multiplier": allocation_multiplier,
        "caution_flags": caution_flags,
        "is_approved": len([f for f in caution_flags if "BLOCK" in f]) == 0
    }
    
    logger.info("trade_filter_applied", symbol=symbol, strategy=filtered_strategy["strategy"], flags=caution_flags)
    return filtered_strategy
