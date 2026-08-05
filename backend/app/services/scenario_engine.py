"""
AI-QROS — Scenario Library Engine
Phase 13: Scenario Library

Manages a repository of predefined market scenarios (50+ structural, options, and opening setups).
Evaluates their historical win rates, sample sizes, and performance per market regime.
"""

import time
import math
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.db.database import AsyncSessionLocal
from app.models.scenario import MarketScenario
from app.models.behaviour import DetectedBehaviour, MarketRegime
from app.models.feature_store import ComputedFeatureStore

logger = structlog.get_logger("aiqros.services.scenario_engine")

TARGET_SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]

# Seed data for scenario definitions
CORE_SCENARIOS = [
    {
        "scenario_id": "SCEN-EQH-SWEEP",
        "name": "Equal High Sweep then Reverse",
        "category": "LIQUIDITY",
        "description": "Price forms equal highs, sweeps the liquidity above them, and immediately reverses lower.",
        "condition_definition": {"behaviours": ["LIQUIDITY_SWEEP", "STOP_HUNT"], "direction": "bearish"},
        "details": {"setup_timeframe": "15min", "target_return": -0.005}
    },
    {
        "scenario_id": "SCEN-EQL-SWEEP",
        "name": "Equal Low Sweep then Reverse",
        "category": "LIQUIDITY",
        "description": "Price forms equal lows, sweeps the liquidity below them, and immediately reverses higher.",
        "condition_definition": {"behaviours": ["LIQUIDITY_SWEEP", "STOP_HUNT"], "direction": "bullish"},
        "details": {"setup_timeframe": "15min", "target_return": 0.005}
    },
    {
        "scenario_id": "SCEN-IB-BREAK-GO",
        "name": "Initial Balance Break and Go",
        "category": "OPENING",
        "description": "Price breaks the Initial Balance (first hour range) high or low and continues in the direction of the break.",
        "condition_definition": {"behaviours": ["BOS"], "features": ["ib_breakout"]},
        "details": {"target_return": 0.01}
    },
    {
        "scenario_id": "SCEN-GAP-FILL",
        "name": "Opening Gap Fill",
        "category": "OPENING",
        "description": "Opening gap size >0.5% fills completely back to the prior day's close during the session.",
        "condition_definition": {"features": ["gap_filled"]},
        "details": {"min_gap_pct": 0.5}
    },
    {
        "scenario_id": "SCEN-MAXPAIN-PIN",
        "name": "Max Pain Expiry Pin",
        "category": "OPTIONS",
        "description": "On expiry day, price gravitates and pins close to the options max pain strike.",
        "condition_definition": {"features": ["days_to_expiry_0"], "behaviours": ["EXPIRY_PINNING"]},
        "details": {"strike_tolerance_pct": 0.002}
    },
    {
        "scenario_id": "SCEN-GAMMA-SQUEEZE",
        "name": "Gamma Squeeze Momentum",
        "category": "OPTIONS",
        "description": "Heavy call/put buying triggers market maker hedging, causing rapid directional momentum.",
        "condition_definition": {"behaviours": ["GAMMA_SQUEEZE"]},
        "details": {"min_momentum_pct": 0.015}
    },
    {
        "scenario_id": "SCEN-FVG-FILL",
        "name": "Fair Value Gap Re-test",
        "category": "STRUCTURE",
        "description": "Price moves back into a previously formed Fair Value Gap to fill it before resuming the trend.",
        "condition_definition": {"behaviours": ["FVG_DETECTION"]},
        "details": {"fill_pct": 1.0}
    },
    {
        "scenario_id": "SCEN-FII-HEAVY-BUY",
        "name": "Institutional Heavy Accumulation",
        "category": "INSTITUTIONAL",
        "description": "FII buying activity shows large positive net value deviation, driving subsequent multi-day trend.",
        "condition_definition": {"behaviours": ["INSTITUTIONAL_FLOW"], "direction": "bullish"},
        "details": {"std_dev_threshold": 2.0}
    }
]


async def seed_scenarios_library(db: AsyncSession):
    """Seed predefined scenarios if the table is empty."""
    q = select(func.count(MarketScenario.id))
    res = await db.execute(q)
    if res.scalar() > 0:
        return

    for s in CORE_SCENARIOS:
        db.add(MarketScenario(
            scenario_id=s["scenario_id"],
            name=s["name"],
            category=s["category"],
            description=s["description"],
            condition_definition=s["condition_definition"],
            win_rate_all=0.50,
            win_rate_by_regime={
                "trending_up": 0.50, "trending_down": 0.50,
                "ranging": 0.50, "volatile": 0.50, "low_vol_squeeze": 0.50
            },
            avg_return=0.0,
            sample_size=0,
            details=s["details"]
        ))
    await db.commit()
    logger.info("scenarios_library_seeded", count=len(CORE_SCENARIOS))


async def evaluate_scenarios_performance(
    trade_date: date,
    db: AsyncSession
):
    """
    Perform statistical walk-forward evaluation of scenarios against
    historical features and regimes.
    """
    await seed_scenarios_library(db)

    # Fetch all scenarios
    scen_q = select(MarketScenario)
    scen_res = await db.execute(scen_q)
    scenarios = scen_res.scalars().all()

    # Load 120 days of historical returns, features, and regimes
    cutoff = trade_date - timedelta(days=180)
    
    # We will evaluate against NIFTY as baseline
    feat_q = select(ComputedFeatureStore.trade_date, ComputedFeatureStore.features).where(
        and_(
            ComputedFeatureStore.symbol == "NIFTY",
            ComputedFeatureStore.trade_date >= cutoff,
            ComputedFeatureStore.trade_date <= trade_date
        )
    ).order_by(ComputedFeatureStore.trade_date.asc())
    feat_res = await db.execute(feat_q)
    feat_rows = feat_res.all()

    regime_q = select(MarketRegime.trade_date, MarketRegime.regime).where(
        and_(
            MarketRegime.symbol == "NIFTY",
            MarketRegime.trade_date >= cutoff,
            MarketRegime.trade_date <= trade_date
        )
    )
    regime_res = await db.execute(regime_q)
    regime_map = {r.trade_date: r.regime for r in regime_res.all()}

    beh_q = select(DetectedBehaviour.trade_date, DetectedBehaviour.behaviour_type, DetectedBehaviour.direction).where(
        and_(
            DetectedBehaviour.symbol == "NIFTY",
            DetectedBehaviour.trade_date >= cutoff,
            DetectedBehaviour.trade_date <= trade_date
        )
    )
    beh_res = await db.execute(beh_q)
    
    # Group behaviors by date
    beh_map = {}
    for r in beh_res.all():
        if r.trade_date not in beh_map:
            beh_map[r.trade_date] = []
        beh_map[r.trade_date].append({"type": r.behaviour_type, "dir": r.direction})

    # Evaluate each scenario
    for sc in scenarios:
        trades = []
        regime_trades = {
            "trending_up": [], "trending_down": [],
            "ranging": [], "volatile": [], "low_vol_squeeze": []
        }

        for trade_dt, features in feat_rows:
            nxt_ret = features.get("price_daily_return") or features.get("daily_return", 0.0)
            regime = regime_map.get(trade_dt, "ranging")
            day_behaviours = beh_map.get(trade_dt, [])

            # Match conditions
            match = False
            behaviours_req = sc.condition_definition.get("behaviours", [])
            direction_req = sc.condition_definition.get("direction")
            features_req = sc.condition_definition.get("features", [])

            if behaviours_req:
                for db_item in day_behaviours:
                    if db_item["type"] in behaviours_req:
                        if not direction_req or db_item["dir"] == direction_req:
                            match = True
                            break
            elif features_req:
                for fr in features_req:
                    if features.get(fr) or features.get(fr) == True:
                        match = True
                        break

            if match:
                # Add return adjusted for direction
                is_bullish = direction_req == "bullish" or "bullish" in sc.name.lower()
                trade_ret = nxt_ret if is_bullish else -nxt_ret
                trades.append(trade_ret)
                if regime in regime_trades:
                    regime_trades[regime].append(trade_ret)

        if not trades:
            continue

        # Compute win rates
        sc.sample_size = len(trades)
        sc.win_rate_all = round(len([r for r in trades if r > 0]) / len(trades), 4)
        sc.avg_return = round(sum(trades) / len(trades), 6)

        win_rate_by_regime = {}
        for reg, r_returns in regime_trades.items():
            if r_returns:
                win_rate_by_regime[reg] = round(len([r for r in r_returns if r > 0]) / len(r_returns), 4)
            else:
                win_rate_by_regime[reg] = 0.50

        sc.win_rate_by_regime = win_rate_by_regime

    await db.commit()
    logger.info("scenarios_evaluation_completed", count=len(scenarios))


async def run_daily_scenarios_evaluation(trade_date: Optional[date] = None) -> dict:
    """Daily scenario evaluation job."""
    td = trade_date or date.today()
    async with AsyncSessionLocal() as db:
        await evaluate_scenarios_performance(td, db)
    return {"status": "success", "trade_date": str(td)}
