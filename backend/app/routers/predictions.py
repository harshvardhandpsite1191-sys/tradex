"""
AI-QROS — ML Predictions Router
Phase 16: AI Decision Engine
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel
from app.db.database import get_db
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/predictions", tags=["AI Decision Engine (ML)"])


class PredictionResponse(BaseModel):
    symbol: str
    trade_date: str
    probability_up: float
    probability_down: float
    verdict: str


@router.post("/train", dependencies=[Depends(require_admin)])
async def train_models(
    symbol: str = Query("NIFTY"),
    mode: str = Query("incremental", description="initial, incremental")
):
    """Trigger ML model training or incremental update."""
    async with AsyncSessionLocal() as db:
        from app.ml.trainer import train_initial_model, update_model_incrementally
        if mode == "initial":
            path = await train_initial_model(symbol.upper(), db)
        else:
            path = await update_model_incrementally(symbol.upper(), db)
        await db.commit()
    return {"status": "success", "mode": mode, "artifact_path": path}


@router.get("/predict", response_model=PredictionResponse, dependencies=[Depends(require_viewer)])
async def get_direction_prediction(
    symbol: str = Query("NIFTY"),
    trade_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get next-day return direction prediction for a symbol."""
    td = trade_date or date.today()
    from app.ml.predictor import predict_next_day_direction
    prob_up, prob_down = await predict_next_day_direction(symbol.upper(), td, db)
    
    verdict = "BULLISH" if prob_up > 0.55 else "BEARISH" if prob_down > 0.55 else "NEUTRAL"
    
    return PredictionResponse(
        symbol=symbol.upper(),
        trade_date=str(td),
        probability_up=prob_up,
        probability_down=prob_down,
        verdict=verdict
    )
    
# Simple import hook
from app.db.database import AsyncSessionLocal
