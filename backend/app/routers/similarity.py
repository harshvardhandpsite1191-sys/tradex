"""
AI-QROS — Historical Similarity Router
Phase 14: Historical Similarity (Pattern Matching)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel
from app.db.database import get_db
from app.auth.auth import require_viewer

router = APIRouter(prefix="/similarity", tags=["Historical Similarity"])


class SimilarityResponse(BaseModel):
    trade_date: str
    distance: float
    cosine_similarity: float
    subsequent_return: float


@router.get("/match", response_model=List[SimilarityResponse], dependencies=[Depends(require_viewer)])
async def match_patterns(
    symbol: str = Query("NIFTY"),
    trade_date: Optional[date] = Query(None),
    top_n: int = Query(5, ge=1, le=10),
    db: AsyncSession = Depends(get_db)
):
    """Find top similar historical dates matching the current day's feature vector."""
    td = trade_date or date.today()
    from app.services.similarity_engine import find_similar_dates
    res = await find_similar_dates(symbol.upper(), td, db, top_n)
    return [SimilarityResponse(**r) for r in res]
