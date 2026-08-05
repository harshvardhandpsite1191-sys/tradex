"""
AI-QROS — Signal Generation Router
Phase 15: Signal Generation
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel
from app.db.database import get_db
from app.models.signal import TradeSignal
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/signals", tags=["Signal Generation"])


class SignalDetail(BaseModel):
    symbol: str
    trade_date: str
    signal_type: str
    direction: str
    confidence_score: float
    contributing_factors: dict


@router.post("/generate", dependencies=[Depends(require_admin)])
async def generate_signals(trade_date: Optional[date] = None):
    """Trigger daily directional signal generation."""
    td = trade_date or date.today()
    from app.services.signal_engine import run_daily_signal_generation
    return await run_daily_signal_generation(td)


@router.get("/latest", response_model=List[SignalDetail], dependencies=[Depends(require_viewer)])
async def get_latest_signals(db: AsyncSession = Depends(get_db)):
    """Get the latest daily trade signals."""
    results = []
    for symbol in ["NIFTY", "BANKNIFTY", "SENSEX"]:
        q = select(TradeSignal).where(TradeSignal.symbol == symbol).order_by(desc(TradeSignal.trade_date)).limit(1)
        res = await db.execute(q)
        row = res.scalar_one_or_none()
        if row:
            results.append(SignalDetail(
                symbol=row.symbol,
                trade_date=str(row.trade_date),
                signal_type=row.signal_type,
                direction=row.direction,
                confidence_score=row.confidence_score,
                contributing_factors=row.contributing_factors
            ))
    return results


@router.get("/history", response_model=List[SignalDetail], dependencies=[Depends(require_viewer)])
async def get_signal_history(
    symbol: str = Query("NIFTY"),
    limit: int = Query(30, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get historical signals for a symbol."""
    q = select(TradeSignal).where(TradeSignal.symbol == symbol.upper()).order_by(desc(TradeSignal.trade_date)).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return [SignalDetail(
        symbol=r.symbol,
        trade_date=str(r.trade_date),
        signal_type=r.signal_type,
        direction=r.direction,
        confidence_score=r.confidence_score,
        contributing_factors=r.contributing_factors
    ) for r in rows]
