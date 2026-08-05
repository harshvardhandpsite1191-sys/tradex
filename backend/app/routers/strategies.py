"""
AI-QROS — Options Strategy Router
Phase 17: Options Strategy Engine
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict
from datetime import date
from app.db.database import get_db
from app.auth.auth import require_viewer

router = APIRouter(prefix="/strategies", tags=["Options Strategy Engine"])


@router.get("/recommend", dependencies=[Depends(require_viewer)])
async def recommend_strategy(
    symbol: str = Query("NIFTY"),
    trade_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Recommend the optimal options strategy for a symbol on a given date."""
    td = trade_date or date.today()
    from app.services.options_strategy_engine import generate_options_strategy_recommendation
    return await generate_options_strategy_recommendation(symbol.upper(), td, db)
