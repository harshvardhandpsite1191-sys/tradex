"""
AI-QROS — Regime Classification Router
Phase 10: Market Regime Engine
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import Optional, List
from datetime import date, datetime
from app.db.database import get_db
from app.models.behaviour import MarketRegime
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/regimes", tags=["Regime Classification"])


class RegimeResponse(BaseModel):
    pass  # We'll use dictionaries for simple output

# Pydantic is required for standard validation, but since we keep imports light, we can use simple responses.
from pydantic import BaseModel

class RegimeDetail(BaseModel):
    symbol: str
    trade_date: str
    regime: str
    sub_regime: Optional[str]
    trend_strength: Optional[float]
    volatility_state: Optional[str]
    options_regime: Optional[str]
    confidence: float
    details: Optional[dict]


@router.post("/classify", dependencies=[Depends(require_admin)])
async def classify_regimes(trade_date: Optional[date] = None):
    """Trigger ML GMM and heuristic-based regime classification for all symbols."""
    td = trade_date or date.today()
    from app.services.regime_engine import run_daily_regime_classification
    return await run_daily_regime_classification(td)


@router.get("/latest", response_model=List[RegimeDetail], dependencies=[Depends(require_viewer)])
async def get_latest_regimes(db: AsyncSession = Depends(get_db)):
    """Get the latest classified regime for all targets."""
    results = []
    for symbol in ["NIFTY", "BANKNIFTY", "SENSEX"]:
        q = select(MarketRegime).where(MarketRegime.symbol == symbol).order_by(desc(MarketRegime.trade_date)).limit(1)
        res = await db.execute(q)
        row = res.scalar_one_or_none()
        if row:
            results.append(RegimeDetail(
                symbol=row.symbol,
                trade_date=str(row.trade_date),
                regime=row.regime,
                sub_regime=row.sub_regime,
                trend_strength=row.trend_strength,
                volatility_state=row.volatility_state,
                options_regime=row.options_regime,
                confidence=row.confidence,
                details=row.details
            ))
    return results


@router.get("/history", response_model=List[RegimeDetail], dependencies=[Depends(require_viewer)])
async def get_regime_history(
    symbol: str = Query("NIFTY"),
    limit: int = Query(30, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get historical regimes for a symbol."""
    q = select(MarketRegime).where(MarketRegime.symbol == symbol.upper()).order_by(desc(MarketRegime.trade_date)).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return [RegimeDetail(
        symbol=r.symbol,
        trade_date=str(r.trade_date),
        regime=r.regime,
        sub_regime=r.sub_regime,
        trend_strength=r.trend_strength,
        volatility_state=r.volatility_state,
        options_regime=r.options_regime,
        confidence=r.confidence,
        details=r.details
    ) for r in rows]
