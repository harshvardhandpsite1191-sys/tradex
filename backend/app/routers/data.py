"""
AI-QROS — Data API Router
Phase 2: Data Infrastructure
Endpoints for triggering data ingestion and querying stored market data.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from app.db.database import get_db
from app.models.market_data import (
    OptionSettlement, GlobalMarketData, OHLCVCandle, DataIngestionLog,
)
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/data", tags=["Data Infrastructure"])


# ─────────────────────────────────────────────
# Request / Response Schemas
# ─────────────────────────────────────────────

class BackfillRequest(BaseModel):
    start_date: date
    end_date: date


class CandleRequest(BaseModel):
    symbol_token: str = "26000"
    exchange: str = "NSE"
    interval: str = "1day"
    days_back: int = 30


class IngestionResponse(BaseModel):
    status: str
    message: Optional[str] = None
    rows_fetched: Optional[int] = None
    rows_inserted: Optional[int] = None
    rows_skipped: Optional[int] = None
    task_id: Optional[str] = None


class SettlementResponse(BaseModel):
    id: str
    trade_date: date
    underlying: str
    expiry_date: str
    strike: float
    option_type: str
    open: float
    high: float
    low: float
    close: float
    settle_price: Optional[float]
    contracts: Optional[int]
    oi: Optional[int]
    change_oi: Optional[int]
    data_source: str

    class Config:
        from_attributes = True


class GlobalDataResponse(BaseModel):
    id: str
    trade_date: date
    factor_name: str
    ticker: str
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[int]
    data_source: str

    class Config:
        from_attributes = True


class CandleResponse(BaseModel):
    id: str
    timestamp: datetime
    symbol_token: str
    exchange: str
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    data_source: str

    class Config:
        from_attributes = True


class IngestionLogResponse(BaseModel):
    id: str
    source: str
    job_type: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    rows_fetched: Optional[int]
    rows_inserted: Optional[int]
    rows_skipped: Optional[int]
    error_message: Optional[str]

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════
# INGESTION TRIGGER ENDPOINTS (Admin only)
# ═══════════════════════════════════════════════════════════════

@router.post("/ingest/bhavcopy", response_model=IngestionResponse,
             dependencies=[Depends(require_admin)])
async def trigger_bhavcopy_ingest():
    """
    Trigger manual NSE Bhavcopy download for the latest available trading day.
    Runs synchronously — returns result directly.
    """
    from app.services.data_ingestion import ingest_bhavcopy
    result = await ingest_bhavcopy(target_date=None, job_type="manual_trigger")
    return IngestionResponse(**result)


@router.post("/ingest/bhavcopy/backfill", response_model=IngestionResponse,
             dependencies=[Depends(require_admin)])
async def trigger_bhavcopy_backfill(request: BackfillRequest, run_sync: bool = False):
    """
    Trigger backfill of NSE Bhavcopy for a date range.
    Dispatched as a background Celery task, or runs synchronously if run_sync is True.
    """
    if request.start_date > request.end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")
    if (request.end_date - request.start_date).days > 365:
        raise HTTPException(status_code=400, detail="Maximum backfill range is 1 year per request")

    if run_sync:
        from app.services.data_ingestion import ingest_bhavcopy_range
        result = await ingest_bhavcopy_range(request.start_date, request.end_date)
        return IngestionResponse(
            status="success",
            message=f"Synchronous backfill completed for {request.start_date} to {request.end_date}",
            rows_fetched=result.get("rows_fetched", 0),
            rows_inserted=result.get("rows_inserted", 0),
            rows_skipped=result.get("rows_skipped", 0),
        )

        )\n\n    from celery_tasks.data_tasks import backfill_bhavcopy
    task = backfill_bhavcopy.delay(
        request.start_date.isoformat(),
        request.end_date.isoformat(),
    )
    return IngestionResponse(
        status="accepted",
        message=f"Backfill task dispatched for {request.start_date} to {request.end_date}",
        task_id=task.id,
    )


# ═══════════════════════════════════════════════════════════════
# ANGEL ONE INGESTION ENDPOINTS (bypasses NSE cloud IP block)
# ═══════════════════════════════════════════════════════════════

@router.post("/ingest/angel/daily", response_model=IngestionResponse,
             dependencies=[Depends(require_admin)])
async def trigger_angel_daily_ingest(target_date: Optional[date] = None):
    """
    Fetch F&O settlement data for a single trading day via Angel One SmartAPI.
    Defaults to today. Bypasses NSE's cloud IP restrictions.
    Runs synchronously — returns row counts directly.
    """
    from app.services.angel_ingestion import ingest_fo_via_angel_one
    from datetime import date as date_cls
    td = target_date or date_cls.today()
    result = await ingest_fo_via_angel_one(td)
    return IngestionResponse(
        status=result.get("status", "failed"),
        message=f"Angel One ingestion for {td}: {result.get('rows_fetched', 0)} fetched, {result.get('rows_inserted', 0)} inserted",
        rows_fetched=result.get("rows_fetched", 0),
        rows_inserted=result.get("rows_inserted", 0),
    )


@router.post("/ingest/angel/backfill", response_model=IngestionResponse,
             dependencies=[Depends(require_admin)])
async def trigger_angel_backfill(request: BackfillRequest):
    """
    Backfill F&O data for a date range via Angel One SmartAPI.
    Skips weekends. Runs synchronously — may take several minutes for long ranges.
    """
    if request.start_date > request.end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")
    if (request.end_date - request.start_date).days > 30:
        raise HTTPException(status_code=400, detail="Maximum Angel One backfill range is 30 days per request")

    from app.services.angel_ingestion import ingest_fo_via_angel_one_range
    result = await ingest_fo_via_angel_one_range(request.start_date, request.end_date)
    return IngestionResponse(
        status=result.get("status", "failed"),
        message=f"Angel One backfill {request.start_date} to {request.end_date}: {result.get('rows_fetched', 0)} fetched",
        rows_fetched=result.get("rows_fetched", 0),
        rows_inserted=result.get("rows_inserted", 0),
    )


@router.post("/seed/demo", response_model=IngestionResponse)
async def trigger_demo_seed(force: bool = False):
    """
    Seed rich demo market intelligence (Regimes, Expiries, Signals, Options chains).
    Allows setting force=true to re-seed. Publicly accessible for instant demo setup.
    """
    from app.db.seed_demo import seed_demo_data
    result = await seed_demo_data(force=force)
    counts = result.get("counts", {})
    total_inserted = sum(counts.values()) if isinstance(counts, dict) else 0
    return IngestionResponse(
        status=result.get("status", "success"),
        message=result.get("message", f"Demo intelligence seeded: {total_inserted} records inserted."),
        rows_fetched=total_inserted,
        rows_inserted=total_inserted,
    )


@router.post("/ingest/global", response_model=IngestionResponse,
             dependencies=[Depends(require_admin)])
async def trigger_global_ingest():
    """
    Trigger manual global market data download (16 factors from yfinance).
    Fetches last 7 days. Runs synchronously.
    """
    from app.services.data_ingestion import ingest_global_markets
    result = await ingest_global_markets(job_type="manual_trigger")
    return IngestionResponse(**result)


@router.post("/ingest/global/backfill", response_model=IngestionResponse,
             dependencies=[Depends(require_admin)])
async def trigger_global_backfill(request: BackfillRequest):
    """
    Trigger backfill of global market data for a date range.
    Dispatched as a background Celery task.
    """
    if request.start_date > request.end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")

    from celery_tasks.data_tasks import backfill_global_markets
    task = backfill_global_markets.delay(
        request.start_date.isoformat(),
        request.end_date.isoformat(),
    )
    return IngestionResponse(
        status="accepted",
        message=f"Global backfill task dispatched for {request.start_date} to {request.end_date}",
        task_id=task.id,
    )


@router.post("/ingest/candles", response_model=IngestionResponse,
             dependencies=[Depends(require_admin)])
async def trigger_candle_ingest(request: CandleRequest):
    """
    Trigger Angel One candle data download.
    Requires Angel One credentials in .env.
    """
    from app.services.data_ingestion import ingest_angel_one_candles
    result = await ingest_angel_one_candles(
        symbol_token=request.symbol_token,
        exchange=request.exchange,
        interval=request.interval,
        days_back=request.days_back,
        job_type="manual_trigger",
    )
    return IngestionResponse(**result)


# ═══════════════════════════════════════════════════════════════
# DATA QUERY ENDPOINTS (Viewer+)
# ═══════════════════════════════════════════════════════════════

@router.get("/settlements", response_model=List[SettlementResponse],
            dependencies=[Depends(require_viewer)])
async def query_settlements(
    underlying: Optional[str] = Query(None, description="Filter: NIFTY, BANKNIFTY, SENSEX"),
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    strike: Optional[float] = Query(None, description="Filter by exact strike price"),
    option_type: Optional[str] = Query(None, description="Filter: CE or PE"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    """Query stored option settlement data from NSE Bhavcopy."""
    query = select(OptionSettlement)

    if underlying:
        query = query.where(OptionSettlement.underlying == underlying.upper())
    if start_date:
        query = query.where(OptionSettlement.trade_date >= start_date)
    if end_date:
        query = query.where(OptionSettlement.trade_date <= end_date)
    if strike is not None:
        query = query.where(OptionSettlement.strike == strike)
    if option_type:
        query = query.where(OptionSettlement.option_type == option_type.upper())

    query = query.order_by(
        OptionSettlement.trade_date.desc(),
        OptionSettlement.underlying,
        OptionSettlement.strike,
    ).limit(limit).offset(offset)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/global", response_model=List[GlobalDataResponse],
            dependencies=[Depends(require_viewer)])
async def query_global_data(
    factor_name: Optional[str] = Query(None, description="Filter: SP500, NASDAQ, VIX, etc."),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    """Query stored global market data (16 macro factors)."""
    query = select(GlobalMarketData)

    if factor_name:
        query = query.where(GlobalMarketData.factor_name == factor_name.upper())
    if start_date:
        query = query.where(GlobalMarketData.trade_date >= start_date)
    if end_date:
        query = query.where(GlobalMarketData.trade_date <= end_date)

    query = query.order_by(
        GlobalMarketData.trade_date.desc(),
        GlobalMarketData.factor_name,
    ).limit(limit).offset(offset)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/candles", response_model=List[CandleResponse],
            dependencies=[Depends(require_viewer)])
async def query_candles(
    symbol_token: Optional[str] = Query(None, description="Angel One symbol token"),
    interval: Optional[str] = Query(None, description="1min, 5min, 15min, 30min, 60min, 1day"),
    exchange: Optional[str] = Query(None, description="NSE or NFO"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(100, le=5000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    """Query stored OHLCV candle data from Angel One."""
    query = select(OHLCVCandle)

    if symbol_token:
        query = query.where(OHLCVCandle.symbol_token == symbol_token)
    if interval:
        query = query.where(OHLCVCandle.interval == interval)
    if exchange:
        query = query.where(OHLCVCandle.exchange == exchange.upper())
    if start_date:
        query = query.where(OHLCVCandle.timestamp >= start_date)
    if end_date:
        query = query.where(OHLCVCandle.timestamp <= end_date)

    query = query.order_by(OHLCVCandle.timestamp.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/ingestion-logs", response_model=List[IngestionLogResponse],
            dependencies=[Depends(require_viewer)])
async def get_ingestion_logs(
    source: Optional[str] = Query(None, description="Filter: NSE_BHAVCOPY, YFINANCE, ANGEL_ONE"),
    status: Optional[str] = Query(None, description="Filter: pending, running, success, failed"),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """View data ingestion job history."""
    query = select(DataIngestionLog)

    if source:
        query = query.where(DataIngestionLog.source == source.upper())
    if status:
        query = query.where(DataIngestionLog.status == status.lower())

    query = query.order_by(DataIngestionLog.started_at.desc()).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/status", dependencies=[Depends(require_viewer)])
async def get_data_status():
    """
    Summary of all stored data: row counts per table,
    last successful ingestion times per source.
    """
    from app.services.data_ingestion import get_data_status as _get_status
    return await _get_status()
