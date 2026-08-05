"""
AI-QROS — Performance Router
Phase 21: Performance Tracking
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional, List, Dict
from datetime import date
from pydantic import BaseModel
from app.db.database import get_db
from app.models.performance import TradePerformanceLog
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/performance", tags=["Performance Tracking"])


class PerformanceLogDetail(BaseModel):
    id: str
    trade_date: str
    symbol: str
    recommendation_id: str
    entry_premium: float
    exit_premium: float
    pnl_value: float
    pnl_pct: float
    outcome: str
    details: Optional[dict]


@router.post("/evaluate", dependencies=[Depends(require_admin)])
async def evaluate_performance(trade_date: Optional[date] = None):
    """Trigger options performance evaluations for completed trades."""
    td = trade_date or date.today()
    from app.services.performance_tracker import run_daily_performance_tracking
    return await run_daily_performance_tracking(td)


@router.get("/metrics", dependencies=[Depends(require_viewer)])
async def get_portfolio_metrics(db: AsyncSession = Depends(get_db)):
    """Get aggregated portfolio level performance metrics."""
    from app.services.performance_tracker import compile_portfolio_metrics
    return await compile_portfolio_metrics(db)


@router.get("/history", response_model=List[PerformanceLogDetail], dependencies=[Depends(require_viewer)])
async def get_performance_history(
    symbol: Optional[str] = Query(None),
    limit: int = Query(30, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed trade P&L log history."""
    q = select(TradePerformanceLog)
    if symbol:
        q = q.where(TradePerformanceLog.symbol == symbol.upper())
    q = q.order_by(desc(TradePerformanceLog.trade_date)).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return [PerformanceLogDetail(
        id=r.id,
        trade_date=str(r.trade_date),
        symbol=r.symbol,
        recommendation_id=r.recommendation_id,
        entry_premium=r.entry_premium,
        exit_premium=r.exit_premium,
        pnl_value=r.pnl_value,
        pnl_pct=r.pnl_pct,
        outcome=r.outcome,
        details=r.details
    ) for r in rows]
