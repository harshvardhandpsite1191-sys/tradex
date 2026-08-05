"""
AI-QROS — Expiry Intelligence Router
Phase 12: Expiry Intelligence
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel
from app.db.database import get_db
from app.models.expiry import ExpiryIntelligence
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/expiry", tags=["Expiry Intelligence"])


class ExpiryDetail(BaseModel):
    symbol: str
    trade_date: str
    expiry_date: str
    max_pain: float
    pcr_oi: float
    total_call_oi: float
    total_put_oi: float
    net_gex: Optional[float]
    predicted_pin_strike: Optional[float]
    pinning_probability: float
    details: Optional[dict]


@router.post("/analyze", dependencies=[Depends(require_admin)])
async def analyze_expiry(trade_date: Optional[date] = None):
    """Trigger options expiry intelligence calculations."""
    td = trade_date or date.today()
    from app.services.expiry_engine import run_daily_expiry_intelligence
    return await run_daily_expiry_intelligence(td)


@router.get("/latest", response_model=List[ExpiryDetail], dependencies=[Depends(require_viewer)])
async def get_latest_expiries(db: AsyncSession = Depends(get_db)):
    """Get the latest option expiry intelligence."""
    results = []
    for symbol in ["NIFTY", "BANKNIFTY", "SENSEX"]:
        q = select(ExpiryIntelligence).where(ExpiryIntelligence.symbol == symbol).order_by(desc(ExpiryIntelligence.trade_date)).limit(1)
        res = await db.execute(q)
        row = res.scalars().first()
        if row:
            results.append(ExpiryDetail(
                symbol=row.symbol,
                trade_date=str(row.trade_date),
                expiry_date=row.expiry_date,
                max_pain=row.max_pain,
                pcr_oi=row.pcr_oi,
                total_call_oi=row.total_call_oi,
                total_put_oi=row.total_put_oi,
                net_gex=row.net_gex,
                predicted_pin_strike=row.predicted_pin_strike,
                pinning_probability=row.pinning_probability,
                details=row.details
            ))
    return results


@router.get("/history", response_model=List[ExpiryDetail], dependencies=[Depends(require_viewer)])
async def get_expiry_history(
    symbol: str = Query("NIFTY"),
    limit: int = Query(30, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get historical expiry intelligence for a symbol."""
    q = select(ExpiryIntelligence).where(ExpiryIntelligence.symbol == symbol.upper()).order_by(desc(ExpiryIntelligence.trade_date)).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return [ExpiryDetail(
        symbol=r.symbol,
        trade_date=str(r.trade_date),
        expiry_date=r.expiry_date,
        max_pain=r.max_pain,
        pcr_oi=r.pcr_oi,
        total_call_oi=r.total_call_oi,
        total_put_oi=r.total_put_oi,
        net_gex=r.net_gex,
        predicted_pin_strike=r.predicted_pin_strike,
        pinning_probability=r.pinning_probability,
        details=r.details
    ) for r in rows]
