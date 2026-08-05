"""
AI-QROS — Opening Intelligence Router
Phase 11: Opening Intelligence
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel
from app.db.database import get_db
from app.models.opening import OpeningIntelligence
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/opening", tags=["Opening Intelligence"])


class OpeningDetail(BaseModel):
    symbol: str
    trade_date: str
    global_sentiment_score: float
    gift_nifty_change_pct: Optional[float]
    expected_gap_pct: float
    actual_gap_pct: Optional[float]
    opening_bias: str
    ib_high_predicted: Optional[float]
    ib_low_predicted: Optional[float]
    ib_high_actual: Optional[float]
    ib_low_actual: Optional[float]
    details: Optional[dict]


@router.post("/analyze", dependencies=[Depends(require_admin)])
async def analyze_opening(trade_date: Optional[date] = None):
    """Trigger daily opening intelligence analysis."""
    td = trade_date or date.today()
    from app.services.opening_engine import run_daily_opening_intelligence
    return await run_daily_opening_intelligence(td)


@router.get("/latest", response_model=List[OpeningDetail], dependencies=[Depends(require_viewer)])
async def get_latest_openings(db: AsyncSession = Depends(get_db)):
    """Get the latest pre-market opening projections."""
    results = []
    for symbol in ["NIFTY", "BANKNIFTY", "SENSEX"]:
        q = select(OpeningIntelligence).where(OpeningIntelligence.symbol == symbol).order_by(desc(OpeningIntelligence.trade_date)).limit(1)
        res = await db.execute(q)
        row = res.scalar_one_or_none()
        if row:
            results.append(OpeningDetail(
                symbol=row.symbol,
                trade_date=str(row.trade_date),
                global_sentiment_score=row.global_sentiment_score,
                gift_nifty_change_pct=row.gift_nifty_change_pct,
                expected_gap_pct=row.expected_gap_pct,
                actual_gap_pct=row.actual_gap_pct,
                opening_bias=row.opening_bias,
                ib_high_predicted=row.ib_high_predicted,
                ib_low_predicted=row.ib_low_predicted,
                ib_high_actual=row.ib_high_actual,
                ib_low_actual=row.ib_low_actual,
                details=row.details
            ))
    return results


@router.get("/history", response_model=List[OpeningDetail], dependencies=[Depends(require_viewer)])
async def get_opening_history(
    symbol: str = Query("NIFTY"),
    limit: int = Query(30, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get historical pre-market predictions for a symbol."""
    q = select(OpeningIntelligence).where(OpeningIntelligence.symbol == symbol.upper()).order_by(desc(OpeningIntelligence.trade_date)).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return [OpeningDetail(
        symbol=r.symbol,
        trade_date=str(r.trade_date),
        global_sentiment_score=r.global_sentiment_score,
        gift_nifty_change_pct=r.gift_nifty_change_pct,
        expected_gap_pct=r.expected_gap_pct,
        actual_gap_pct=r.actual_gap_pct,
        opening_bias=r.opening_bias,
        ib_high_predicted=r.ib_high_predicted,
        ib_low_predicted=r.ib_low_predicted,
        ib_high_actual=r.ib_high_actual,
        ib_low_actual=r.ib_low_actual,
        details=r.details
    ) for r in rows]
