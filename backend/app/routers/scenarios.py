"""
AI-QROS — Scenario Library Router
Phase 13: Scenario Library
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel
from app.db.database import get_db
from app.models.scenario import MarketScenario
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/scenarios", tags=["Scenario Library"])


class ScenarioDetail(BaseModel):
    scenario_id: str
    name: str
    category: str
    description: str
    win_rate_all: float
    win_rate_by_regime: dict
    avg_return: float
    sample_size: int
    details: Optional[dict]


@router.post("/evaluate", dependencies=[Depends(require_admin)])
async def evaluate_scenarios(trade_date: Optional[date] = None):
    """Trigger statistical walk-forward evaluation of scenarios."""
    td = trade_date or date.today()
    from app.services.scenario_engine import run_daily_scenarios_evaluation
    return await run_daily_scenarios_evaluation(td)


@router.get("/", response_model=List[ScenarioDetail], dependencies=[Depends(require_viewer)])
async def list_scenarios(
    category: Optional[str] = Query(None),
    min_win_rate: float = Query(0.0, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    """List all registered scenarios in the library."""
    q = select(MarketScenario)
    if category:
        q = q.where(MarketScenario.category == category.upper())
    if min_win_rate > 0:
        q = q.where(MarketScenario.win_rate_all >= min_win_rate)
        
    res = await db.execute(q)
    rows = res.scalars().all()
    return [ScenarioDetail(
        scenario_id=r.scenario_id,
        name=r.name,
        category=r.category,
        description=r.description,
        win_rate_all=r.win_rate_all,
        win_rate_by_regime=r.win_rate_by_regime,
        avg_return=r.avg_return,
        sample_size=r.sample_size,
        details=r.details
    ) for r in rows]
