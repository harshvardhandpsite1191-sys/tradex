"""
AI-QROS — Behaviour Extraction API Router
Phase 5: Behaviour Extraction
Endpoints for triggering extraction, querying behaviours, and viewing regimes.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from app.db.database import get_db
from app.models.behaviour import DetectedBehaviour, MarketRegime, BehaviourExtractionLog
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/behaviours", tags=["Behaviour Extraction"])


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────

class ExtractRequest(BaseModel):
    symbol: str = "NIFTY"
    trade_date: Optional[date] = None


class ExtractAllRequest(BaseModel):
    trade_date: Optional[date] = None


class BehaviourResponse(BaseModel):
    id: str
    trade_date: str
    symbol: str
    behaviour_type: str
    category: str
    confidence: float
    direction: Optional[str]
    description: str
    details: Optional[dict]


class RegimeResponse(BaseModel):
    symbol: str
    trade_date: str
    regime: str
    sub_regime: Optional[str]
    trend_strength: Optional[float]
    volatility_state: Optional[str]
    options_regime: Optional[str]
    confidence: float
    details: Optional[dict]


class ExtractionLogResponse(BaseModel):
    id: str
    symbol: str
    trade_date: date
    status: str
    behaviours_detected: int
    categories_detected: Optional[dict]
    started_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    error_message: Optional[str]
    triggered_by: str

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════
# TRIGGER EXTRACTION (Admin only)
# ═══════════════════════════════════════════════════════════════

@router.post("/extract", dependencies=[Depends(require_admin)])
async def extract_behaviours(request: ExtractRequest):
    """Extract behaviours for a single symbol. Runs synchronously."""
    valid_symbols = {"NIFTY", "BANKNIFTY", "SENSEX"}
    symbol = request.symbol.upper()
    if symbol not in valid_symbols:
        raise HTTPException(status_code=400, detail=f"Invalid symbol. Must be: {', '.join(valid_symbols)}")

    trade_dt = request.trade_date or date.today()
    from app.services.behaviour_engine import extract_behaviours_for_date
    return await extract_behaviours_for_date(symbol, trade_dt, triggered_by="manual")


@router.post("/extract/all", dependencies=[Depends(require_admin)])
async def extract_all_behaviours(request: ExtractAllRequest):
    """Extract behaviours for ALL symbols. Runs synchronously."""
    trade_dt = request.trade_date or date.today()
    from app.services.behaviour_engine import extract_daily_behaviours
    return await extract_daily_behaviours(trade_dt, triggered_by="manual")


@router.post("/extract/async", dependencies=[Depends(require_admin)])
async def extract_behaviours_async(request: ExtractAllRequest):
    """Dispatch behaviour extraction as background Celery task."""
    trade_dt = request.trade_date or date.today()
    from celery_tasks.behaviour_tasks import extract_daily_behaviours_task
    task = extract_daily_behaviours_task.delay(trade_dt.isoformat())
    return {"status": "accepted", "message": f"Extraction dispatched for {trade_dt}", "task_id": task.id}


# ═══════════════════════════════════════════════════════════════
# QUERY BEHAVIOURS (Viewer+)
# ═══════════════════════════════════════════════════════════════

@router.get("/", response_model=List[BehaviourResponse], dependencies=[Depends(require_viewer)])
async def list_behaviours(
    symbol: Optional[str] = Query(None),
    trade_date: Optional[date] = Query(None),
    category: Optional[str] = Query(None, description="STRUCTURE, LIQUIDITY, INSTITUTIONAL, OPTIONS, VOLUME, REGIME"),
    behaviour_type: Optional[str] = Query(None),
    direction: Optional[str] = Query(None, description="bullish, bearish, neutral"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Query detected behaviours with filters."""
    query = select(DetectedBehaviour)
    if symbol:
        query = query.where(DetectedBehaviour.symbol == symbol.upper())
    if trade_date:
        query = query.where(DetectedBehaviour.trade_date == trade_date)
    if category:
        query = query.where(DetectedBehaviour.category == category.upper())
    if behaviour_type:
        query = query.where(DetectedBehaviour.behaviour_type == behaviour_type.upper())
    if direction:
        query = query.where(DetectedBehaviour.direction == direction.lower())
    if min_confidence > 0:
        query = query.where(DetectedBehaviour.confidence >= min_confidence)

    query = query.order_by(DetectedBehaviour.detected_at.desc()).limit(limit)
    result = await db.execute(query)
    rows = result.scalars().all()

    return [BehaviourResponse(
        id=r.id, trade_date=str(r.trade_date), symbol=r.symbol,
        behaviour_type=r.behaviour_type, category=r.category,
        confidence=r.confidence, direction=r.direction,
        description=r.description, details=r.details,
    ) for r in rows]


# ═══════════════════════════════════════════════════════════════
# MARKET REGIME (Viewer+)
# ═══════════════════════════════════════════════════════════════

@router.get("/regime/{symbol}/{trade_date}", response_model=RegimeResponse,
            dependencies=[Depends(require_viewer)])
async def get_regime(symbol: str, trade_date: date):
    """Get market regime classification for a symbol on a date."""
    from app.services.behaviour_engine import get_regime as _get_regime
    result = await _get_regime(symbol.upper(), trade_date)
    if not result:
        raise HTTPException(status_code=404, detail=f"No regime data for {symbol.upper()} on {trade_date}")
    return result


@router.get("/regime/latest", dependencies=[Depends(require_viewer)])
async def get_latest_regimes(db: AsyncSession = Depends(get_db)):
    """Get the latest regime for each symbol."""
    regimes = {}
    for symbol in ["NIFTY", "BANKNIFTY", "SENSEX"]:
        result = await db.execute(
            select(MarketRegime)
            .where(MarketRegime.symbol == symbol)
            .order_by(MarketRegime.trade_date.desc())
            .limit(1)
        )
        r = result.scalar_one_or_none()
        if r:
            regimes[symbol] = {
                "trade_date": str(r.trade_date), "regime": r.regime,
                "sub_regime": r.sub_regime, "trend_strength": r.trend_strength,
                "volatility_state": r.volatility_state, "options_regime": r.options_regime,
                "confidence": r.confidence,
            }
        else:
            regimes[symbol] = None
    return {"regimes": regimes}


@router.get("/regime/history", dependencies=[Depends(require_viewer)])
async def get_regime_history(
    symbol: str = Query("NIFTY"),
    limit: int = Query(30, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get regime history for a symbol."""
    result = await db.execute(
        select(MarketRegime)
        .where(MarketRegime.symbol == symbol.upper())
        .order_by(MarketRegime.trade_date.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [{
        "trade_date": str(r.trade_date), "regime": r.regime,
        "sub_regime": r.sub_regime, "trend_strength": r.trend_strength,
        "volatility_state": r.volatility_state, "confidence": r.confidence,
    } for r in rows]


# ═══════════════════════════════════════════════════════════════
# LOGS & SUMMARY (Viewer+)
# ═══════════════════════════════════════════════════════════════

@router.get("/logs", response_model=List[ExtractionLogResponse],
            dependencies=[Depends(require_viewer)])
async def list_extraction_logs(
    symbol: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """View behaviour extraction job history."""
    query = select(BehaviourExtractionLog)
    if symbol:
        query = query.where(BehaviourExtractionLog.symbol == symbol.upper())
    if status:
        query = query.where(BehaviourExtractionLog.status == status.lower())
    query = query.order_by(BehaviourExtractionLog.started_at.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/summary", dependencies=[Depends(require_viewer)])
async def get_behaviour_summary(
    trade_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Summary of detected behaviours — count by type and category."""
    filters = []
    if trade_date:
        filters.append(DetectedBehaviour.trade_date == trade_date)

    # Count by category
    cat_result = await db.execute(
        select(DetectedBehaviour.category, func.count(DetectedBehaviour.id))
        .where(*filters)
        .group_by(DetectedBehaviour.category)
    )
    by_category = {r[0]: r[1] for r in cat_result.all()}

    # Count by type
    type_result = await db.execute(
        select(DetectedBehaviour.behaviour_type, func.count(DetectedBehaviour.id))
        .where(*filters)
        .group_by(DetectedBehaviour.behaviour_type)
        .order_by(func.count(DetectedBehaviour.id).desc())
    )
    by_type = {r[0]: r[1] for r in type_result.all()}

    # Direction distribution
    dir_result = await db.execute(
        select(DetectedBehaviour.direction, func.count(DetectedBehaviour.id))
        .where(*filters)
        .group_by(DetectedBehaviour.direction)
    )
    by_direction = {r[0] or "none": r[1] for r in dir_result.all()}

    return {
        "trade_date": str(trade_date) if trade_date else "all",
        "total_behaviours": sum(by_category.values()),
        "by_category": by_category,
        "by_type": by_type,
        "by_direction": by_direction,
    }
