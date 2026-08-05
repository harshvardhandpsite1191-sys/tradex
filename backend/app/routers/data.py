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
async def trigger_bhavcopy_backfill(request: BackfillRequest):
    """
    Trigger backfill of NSE Bhavcopy for a date range.
    Dispatched as a background Celery task — returns task ID.
    """
    if request.start_date > request.end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")
    if (request.end_date - request.start_date).days > 365:
        raise HTTPException(status_code=400, detail="Maximum backfill range is 1 year per request")

    from celery_tasks.data_tasks import backfill_bhavcopy
    task = backfill_bhavcopy.delay(
        request.start_date.isoformat(),
        request.end_date.isoformat(),
    )
    return IngestionResponse(
        status="accepted",
        message=f"Backfill task dispatched for {request.start_date} to {request.end_date}",
        task_id=task.id,
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
