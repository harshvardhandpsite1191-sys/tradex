"""
AI-QROS — Trade Recommendations Router
Phase 19: Trade Recommendation
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from typing import Optional, List
from datetime import date
from pydantic import BaseModel
from app.db.database import get_db
from app.models.recommendation import TradeRecommendation
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/recommendations", tags=["Trade Recommendations"])


class LegDetail(BaseModel):
    action: str
    option_type: str
    strike: int
    expiry: str
    qty_ratio: int
    estimated_premium: float


class RecommendationDetail(BaseModel):
    symbol: str
    trade_date: str
    strategy_name: str
    legs_detail: dict
    stop_loss_total: Optional[float]
    target_total: Optional[float]
    risk_reward_ratio: Optional[float]
    allocation_weight: float
    status: str
    details: Optional[dict]


@router.post("/generate", dependencies=[Depends(require_admin)])
async def generate_recommendations(trade_date: Optional[date] = None):
    """Trigger daily options trade recommendation generation."""
    td = trade_date or date.today()
    from app.services.recommendation_engine import run_daily_recommendations
    return await run_daily_recommendations(td)


@router.get("/latest", response_model=List[RecommendationDetail], dependencies=[Depends(require_viewer)])
async def get_latest_recommendations(db: AsyncSession = Depends(get_db)):
    """Get the latest daily trade recommendations."""
    results = []
    for symbol in ["NIFTY", "BANKNIFTY"]:
        q = select(TradeRecommendation).where(TradeRecommendation.symbol == symbol).order_by(desc(TradeRecommendation.trade_date)).limit(1)
        res = await db.execute(q)
        row = res.scalar_one_or_none()
        if row:
            results.append(RecommendationDetail(
                symbol=row.symbol,
                trade_date=str(row.trade_date),
                strategy_name=row.strategy_name,
                legs_detail=row.legs_detail,
                stop_loss_total=row.stop_loss_total,
                target_total=row.target_total,
                risk_reward_ratio=row.risk_reward_ratio,
                allocation_weight=row.allocation_weight,
                status=row.status,
                details=row.details
            ))
    return results


@router.get("/history", response_model=List[RecommendationDetail], dependencies=[Depends(require_viewer)])
async def get_recommendation_history(
    symbol: str = Query("NIFTY"),
    limit: int = Query(30, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get historical trade recommendations for a symbol."""
    q = select(TradeRecommendation).where(TradeRecommendation.symbol == symbol.upper()).order_by(desc(TradeRecommendation.trade_date)).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return [RecommendationDetail(
        symbol=r.symbol,
        trade_date=str(r.trade_date),
        strategy_name=r.strategy_name,
        legs_detail=r.legs_detail,
        stop_loss_total=r.stop_loss_total,
        target_total=r.target_total,
        risk_reward_ratio=r.risk_reward_ratio,
        allocation_weight=r.allocation_weight,
        status=r.status,
        details=r.details
    ) for r in rows]
