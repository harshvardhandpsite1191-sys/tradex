"""
AI-QROS — Continuous Learning Router
Phase 22: Continuous Learning
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict
from datetime import date
from app.db.database import get_db
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/learning", tags=["Continuous Learning"])


@router.post("/check-drift", dependencies=[Depends(require_admin)])
async def trigger_drift_check(trade_date: Optional[date] = None):
    """Trigger Population Stability Index (PSI) feature drift analysis."""
    td = trade_date or date.today()
    from app.services.continuous_learning import run_daily_drift_monitoring
    return await run_daily_drift_monitoring(td)


@router.get("/metrics/{symbol}", dependencies=[Depends(require_viewer)])
async def get_drift_metrics(
    symbol: str,
    trade_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve the drift analysis metrics for a symbol."""
    td = trade_date or date.today()
    from app.services.continuous_learning import check_feature_drift
    return await check_feature_drift(symbol.upper(), td, db)
