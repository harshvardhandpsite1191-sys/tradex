"""
AI-QROS — Feature Computation API Router
Phase 4: Feature Engineering
Endpoints for triggering feature computation and querying computed features.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from app.db.database import get_db
from app.models.feature_store import ComputedFeatureStore, FeatureComputationLog
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/features", tags=["Feature Engine"])


# ─────────────────────────────────────────────
# Request / Response Schemas
# ─────────────────────────────────────────────

class ComputeRequest(BaseModel):
    symbol: str = "NIFTY"
    trade_date: Optional[date] = None  # defaults to today


class ComputeAllRequest(BaseModel):
    trade_date: Optional[date] = None


class ComputeResponse(BaseModel):
    status: str
    symbol: Optional[str] = None
    trade_date: Optional[str] = None
    total_features: Optional[int] = None
    category_counts: Optional[dict] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
    task_id: Optional[str] = None


class FeatureStoreResponse(BaseModel):
    symbol: str
    trade_date: str
    feature_count: int
    features: dict
    computed_at: str


class ComputationLogResponse(BaseModel):
    id: str
    symbol: str
    trade_date: date
    status: str
    features_computed: int
    categories_computed: Optional[dict]
    started_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    error_message: Optional[str]
    triggered_by: str

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════
# TRIGGER FEATURE COMPUTATION (Admin only)
# ═══════════════════════════════════════════════════════════════

@router.post("/compute", response_model=ComputeResponse,
             dependencies=[Depends(require_admin)])
async def compute_features(request: ComputeRequest):
    """
    Compute features for a single symbol on a given date.
    Runs synchronously. Defaults to NIFTY, today.
    """
    valid_symbols = {"NIFTY", "BANKNIFTY", "SENSEX"}
    symbol = request.symbol.upper()
    if symbol not in valid_symbols:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid symbol '{request.symbol}'. Must be one of: {', '.join(valid_symbols)}"
        )

    trade_dt = request.trade_date or date.today()

    from app.services.feature_engine import compute_features_for_date
    result = await compute_features_for_date(symbol, trade_dt, triggered_by="manual")
    return ComputeResponse(**result)


@router.post("/compute/all", response_model=dict,
             dependencies=[Depends(require_admin)])
async def compute_all_features(request: ComputeAllRequest):
    """
    Compute features for ALL symbols (NIFTY, BANKNIFTY, SENSEX) on a given date.
    Runs synchronously. Defaults to today.
    """
    trade_dt = request.trade_date or date.today()

    from app.services.feature_engine import compute_daily_features
    result = await compute_daily_features(trade_dt, triggered_by="manual")
    return result


@router.post("/compute/async", dependencies=[Depends(require_admin)])
async def compute_features_async(request: ComputeAllRequest):
    """
    Dispatch daily feature computation as a background Celery task.
    Returns task_id for tracking.
    """
    trade_dt = request.trade_date or date.today()

    from celery_tasks.feature_tasks import compute_daily_features_task
    task = compute_daily_features_task.delay(trade_dt.isoformat())
    return {
        "status": "accepted",
        "message": f"Feature computation dispatched for {trade_dt}",
        "task_id": task.id,
    }


# ═══════════════════════════════════════════════════════════════
# QUERY COMPUTED FEATURES (Viewer+)
# ═══════════════════════════════════════════════════════════════

@router.get("/store/{symbol}/{trade_date}",
            dependencies=[Depends(require_viewer)])
async def get_computed_features(symbol: str, trade_date: date):
    """
    Get computed features for a specific symbol and date.
    Returns all features as a JSONB dict.
    """
    from app.services.feature_engine import get_features
    result = await get_features(symbol.upper(), trade_date)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No computed features found for {symbol.upper()} on {trade_date}"
        )
    return result


@router.get("/store", dependencies=[Depends(require_viewer)])
async def list_computed_features(
    symbol: Optional[str] = Query(None, description="Filter: NIFTY, BANKNIFTY, SENSEX"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    """List computed feature store entries (metadata only, not full features)."""
    query = select(
        ComputedFeatureStore.id,
        ComputedFeatureStore.trade_date,
        ComputedFeatureStore.symbol,
        ComputedFeatureStore.feature_count,
        ComputedFeatureStore.computation_version,
        ComputedFeatureStore.computed_at,
        ComputedFeatureStore.duration_seconds,
    )

    if symbol:
        query = query.where(ComputedFeatureStore.symbol == symbol.upper())
    if start_date:
        query = query.where(ComputedFeatureStore.trade_date >= start_date)
    if end_date:
        query = query.where(ComputedFeatureStore.trade_date <= end_date)

    query = query.order_by(ComputedFeatureStore.trade_date.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    rows = result.all()
    return [
        {
            "id": r[0], "trade_date": str(r[1]), "symbol": r[2],
            "feature_count": r[3], "computation_version": r[4],
            "computed_at": r[5].isoformat(), "duration_seconds": r[6],
        }
        for r in rows
    ]


@router.get("/logs", response_model=List[ComputationLogResponse],
            dependencies=[Depends(require_viewer)])
async def list_computation_logs(
    symbol: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """View feature computation job history."""
    query = select(FeatureComputationLog)

    if symbol:
        query = query.where(FeatureComputationLog.symbol == symbol.upper())
    if status:
        query = query.where(FeatureComputationLog.status == status.lower())

    query = query.order_by(FeatureComputationLog.started_at.desc()).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/summary", dependencies=[Depends(require_viewer)])
async def get_feature_summary(db: AsyncSession = Depends(get_db)):
    """
    Summary of feature store: latest computation per symbol,
    total features, date coverage.
    """
    summary = {}
    for symbol in ["NIFTY", "BANKNIFTY", "SENSEX"]:
        result = await db.execute(
            select(ComputedFeatureStore)
            .where(ComputedFeatureStore.symbol == symbol)
            .order_by(ComputedFeatureStore.trade_date.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()

        count_result = await db.execute(
            select(func.count(ComputedFeatureStore.id))
            .where(ComputedFeatureStore.symbol == symbol)
        )
        total_rows = count_result.scalar() or 0

        if latest:
            summary[symbol] = {
                "latest_date": str(latest.trade_date),
                "latest_feature_count": latest.feature_count,
                "latest_computed_at": latest.computed_at.isoformat(),
                "total_days_computed": total_rows,
            }
        else:
            summary[symbol] = {
                "latest_date": None,
                "latest_feature_count": 0,
                "total_days_computed": 0,
            }

    return {"symbols": summary}
