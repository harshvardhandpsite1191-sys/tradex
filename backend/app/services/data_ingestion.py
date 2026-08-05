"""
AI-QROS — Data Ingestion Service
Phase 2: Data Infrastructure

Central service that:
1. Calls data providers → receives DataFrames
2. Validates and transforms data
3. Bulk-inserts into database (upsert / on_conflict_do_nothing)
4. Logs every job to data_ingestion_logs

Used by both Celery tasks (scheduled) and API router (manual triggers).
"""

import time
from datetime import datetime, date, timedelta
from typing import Optional
import pandas as pd
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, func

from app.db.database import AsyncSessionLocal
from app.models.market_data import (
    OHLCVCandle, OptionSettlement, GlobalMarketData, DataIngestionLog,
)

logger = structlog.get_logger("aiqros.services.data_ingestion")


# ─────────────────────────────────────────────
# Ingestion Log Helpers
# ─────────────────────────────────────────────

async def _create_ingestion_log(
    db: AsyncSession,
    source: str,
    job_type: str,
    date_start: Optional[date] = None,
    date_end: Optional[date] = None,
) -> str:
    """Create an ingestion log entry and return its ID."""
    log = DataIngestionLog(
        source=source,
        job_type=job_type,
        status="running",
        started_at=datetime.utcnow(),
        date_range_start=date_start,
        date_range_end=date_end,
    )
    db.add(log)
    await db.flush()
    return log.id


async def _complete_ingestion_log(
    db: AsyncSession,
    log_id: str,
    status: str,
    rows_fetched: int = 0,
    rows_inserted: int = 0,
    rows_skipped: int = 0,
    error_message: Optional[str] = None,
    details: Optional[dict] = None,
):
    """Update an ingestion log entry with results."""
    result = await db.execute(
        select(DataIngestionLog).where(DataIngestionLog.id == log_id)
    )
    log = result.scalar_one_or_none()
    if log:
        now = datetime.utcnow()
        log.status = status
        log.completed_at = now
        log.duration_seconds = round((now - log.started_at).total_seconds(), 2)
        log.rows_fetched = rows_fetched
        log.rows_inserted = rows_inserted
        log.rows_skipped = rows_skipped
        log.error_message = error_message
        log.details = details


# ─────────────────────────────────────────────
# NSE BHAVCOPY INGESTION
# ─────────────────────────────────────────────

async def ingest_bhavcopy(
    target_date: Optional[date] = None,
    job_type: str = "daily_fetch",
) -> dict:
    """
    Download NSE Bhavcopy for a specific date and store in option_settlements.
    If target_date is None, fetches the latest available (today or most recent trading day).
    Returns summary dict with status and row counts.
    """
    from app.data_providers.nse_bhavcopy import download_latest_bhavcopy, _download_bhavcopy
    import aiohttp

    async with AsyncSessionLocal() as db:
        log_id = await _create_ingestion_log(
            db, "NSE_BHAVCOPY", job_type,
            date_start=target_date, date_end=target_date,
        )
        await db.commit()

        try:
            start_time = time.time()

            # Fetch data
            if target_date is None:
                df = await download_latest_bhavcopy()
            else:
                from app.data_providers.nse_bhavcopy import NSE_HEADERS
                async with aiohttp.ClientSession() as session:
                    try:
                        async with session.get(
                            "https://www.nseindia.com",
                            headers=NSE_HEADERS,
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as _:
                            pass
                    except Exception:
                        pass
                    df = await _download_bhavcopy(target_date, session)

            if df is None or df.empty:
                await _complete_ingestion_log(
                    db, log_id, "success",
                    rows_fetched=0, rows_inserted=0,
                    details={"message": "No data available for the requested date"},
                )
                await db.commit()
                return {"status": "success", "rows_fetched": 0, "rows_inserted": 0,
                        "message": "No data available"}

            rows_fetched = len(df)

            # Prepare records for bulk insert
            records = []
            for _, row in df.iterrows():
                records.append({
                    "trade_date": pd.to_datetime(row.get("trade_date")).date()
                    if pd.notna(row.get("trade_date")) else target_date or date.today(),
                    "underlying": str(row.get("underlying", "")),
                    "expiry_date": str(row.get("expiry_date", "")),
                    "strike": float(row.get("strike", 0)),
                    "option_type": str(row.get("option_type", "")),
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "settle_price": float(row["settle_price"]) if pd.notna(row.get("settle_price")) else None,
                    "contracts": int(row["contracts"]) if pd.notna(row.get("contracts")) else None,
                    "value_lakh": float(row["value_lakh"]) if pd.notna(row.get("value_lakh")) else None,
                    "oi": int(row["oi"]) if pd.notna(row.get("oi")) else None,
                    "change_oi": int(row["change_oi"]) if pd.notna(row.get("change_oi")) else None,
                    "data_source": "NSE_BHAVCOPY",
                })

            # Bulk upsert — skip duplicates
            if records:
                stmt = pg_insert(OptionSettlement).values(records)
                stmt = stmt.on_conflict_do_nothing(
                    constraint="uq_option_settlement"
                )
                result = await db.execute(stmt)
                rows_inserted = result.rowcount if result.rowcount else 0
            else:
                rows_inserted = 0

            rows_skipped = rows_fetched - rows_inserted

            await _complete_ingestion_log(
                db, log_id, "success",
                rows_fetched=rows_fetched,
                rows_inserted=rows_inserted,
                rows_skipped=rows_skipped,
            )
            await db.commit()

            logger.info(
                "bhavcopy_ingested",
                rows_fetched=rows_fetched,
                rows_inserted=rows_inserted,
                rows_skipped=rows_skipped,
                duration_s=round(time.time() - start_time, 2),
            )

            return {
                "status": "success",
                "rows_fetched": rows_fetched,
                "rows_inserted": rows_inserted,
                "rows_skipped": rows_skipped,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error("bhavcopy_ingestion_failed", error=error_msg)
            await _complete_ingestion_log(db, log_id, "failed", error_message=error_msg)
            await db.commit()
            return {"status": "failed", "error": error_msg}


async def ingest_bhavcopy_range(
    start_date: date,
    end_date: date,
) -> dict:
    """
    Backfill NSE Bhavcopy for a date range.
    Downloads in batches to avoid overwhelming NSE.
    """
    from app.data_providers.nse_bhavcopy import download_historical_bhavcopy

    async with AsyncSessionLocal() as db:
        log_id = await _create_ingestion_log(
            db, "NSE_BHAVCOPY", "backfill",
            date_start=start_date, date_end=end_date,
        )
        await db.commit()

        try:
            dfs = await download_historical_bhavcopy(start_date, end_date)
            total_fetched = 0
            total_inserted = 0

            for df in dfs:
                if df is None or df.empty:
                    continue

                total_fetched += len(df)
                records = []
                for _, row in df.iterrows():
                    records.append({
                        "trade_date": pd.to_datetime(row.get("trade_date")).date()
                        if pd.notna(row.get("trade_date")) else start_date,
                        "underlying": str(row.get("underlying", "")),
                        "expiry_date": str(row.get("expiry_date", "")),
                        "strike": float(row.get("strike", 0)),
                        "option_type": str(row.get("option_type", "")),
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "close": float(row.get("close", 0)),
                        "settle_price": float(row["settle_price"]) if pd.notna(row.get("settle_price")) else None,
                        "contracts": int(row["contracts"]) if pd.notna(row.get("contracts")) else None,
                        "value_lakh": float(row["value_lakh"]) if pd.notna(row.get("value_lakh")) else None,
                        "oi": int(row["oi"]) if pd.notna(row.get("oi")) else None,
                        "change_oi": int(row["change_oi"]) if pd.notna(row.get("change_oi")) else None,
                        "data_source": "NSE_BHAVCOPY",
                    })

                if records:
                    stmt = pg_insert(OptionSettlement).values(records)
                    stmt = stmt.on_conflict_do_nothing(constraint="uq_option_settlement")
                    result = await db.execute(stmt)
                    total_inserted += result.rowcount if result.rowcount else 0

            await _complete_ingestion_log(
                db, log_id, "success",
                rows_fetched=total_fetched,
                rows_inserted=total_inserted,
                rows_skipped=total_fetched - total_inserted,
            )
            await db.commit()

            logger.info(
                "bhavcopy_backfill_complete",
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                rows_fetched=total_fetched,
                rows_inserted=total_inserted,
            )

            return {
                "status": "success",
                "rows_fetched": total_fetched,
                "rows_inserted": total_inserted,
                "rows_skipped": total_fetched - total_inserted,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error("bhavcopy_backfill_failed", error=error_msg)
            await _complete_ingestion_log(db, log_id, "failed", error_message=error_msg)
            await db.commit()
            return {"status": "failed", "error": error_msg}


# ─────────────────────────────────────────────
# GLOBAL MARKETS INGESTION (yfinance)
# ─────────────────────────────────────────────

async def ingest_global_markets(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    job_type: str = "daily_fetch",
) -> dict:
    """
    Fetch global market data for all 16 factors from yfinance and store.
    Defaults to last 5 trading days if no dates specified.
    """
    from app.data_providers.yfinance_global import fetch_historical_global_data
    import asyncio

    if start_date is None:
        start_date = date.today() - timedelta(days=7)
    if end_date is None:
        end_date = date.today()

    async with AsyncSessionLocal() as db:
        log_id = await _create_ingestion_log(
            db, "YFINANCE", job_type,
            date_start=start_date, date_end=end_date,
        )
        await db.commit()

        try:
            # yfinance is synchronous — run in thread pool
            loop = asyncio.get_event_loop()
            data_dict = await loop.run_in_executor(
                None,
                lambda: fetch_historical_global_data(start_date, end_date)
            )

            total_fetched = 0
            total_inserted = 0

            for factor_name, df in data_dict.items():
                if df is None or df.empty:
                    continue

                total_fetched += len(df)
                records = []
                for _, row in df.iterrows():
                    trade_dt = pd.to_datetime(row.get("trade_date"))
                    if pd.isna(trade_dt):
                        continue
                    records.append({
                        "trade_date": trade_dt.date(),
                        "factor_name": factor_name,
                        "ticker": str(row.get("ticker", "")),
                        "open": float(row["open"]) if pd.notna(row.get("open")) else None,
                        "high": float(row["high"]) if pd.notna(row.get("high")) else None,
                        "low": float(row["low"]) if pd.notna(row.get("low")) else None,
                        "close": float(row["close"]) if pd.notna(row.get("close")) else None,
                        "volume": int(row["volume"]) if pd.notna(row.get("volume")) else None,
                        "data_source": "YFINANCE",
                    })

                if records:
                    stmt = pg_insert(GlobalMarketData).values(records)
                    stmt = stmt.on_conflict_do_nothing(constraint="uq_global_market_data")
                    result = await db.execute(stmt)
                    total_inserted += result.rowcount if result.rowcount else 0

            await _complete_ingestion_log(
                db, log_id, "success",
                rows_fetched=total_fetched,
                rows_inserted=total_inserted,
                rows_skipped=total_fetched - total_inserted,
                details={"factors_fetched": list(data_dict.keys())},
            )
            await db.commit()

            logger.info(
                "global_markets_ingested",
                factors=len(data_dict),
                rows_fetched=total_fetched,
                rows_inserted=total_inserted,
            )

            return {
                "status": "success",
                "factors_fetched": len(data_dict),
                "rows_fetched": total_fetched,
                "rows_inserted": total_inserted,
                "rows_skipped": total_fetched - total_inserted,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error("global_markets_ingestion_failed", error=error_msg)
            await _complete_ingestion_log(db, log_id, "failed", error_message=error_msg)
            await db.commit()
            return {"status": "failed", "error": error_msg}


# ─────────────────────────────────────────────
# ANGEL ONE CANDLES INGESTION
# ─────────────────────────────────────────────

async def ingest_angel_one_candles(
    symbol_token: str = "26000",
    exchange: str = "NSE",
    interval: str = "1day",
    days_back: int = 30,
    job_type: str = "daily_fetch",
) -> dict:
    """
    Fetch OHLCV candles from Angel One SmartAPI and store.
    Defaults to NIFTY 50 index, daily candles, last 30 days.
    """
    from app.data_providers.angel_one import angel_one
    import asyncio
    from datetime import datetime as dt

    end_date = dt.utcnow()
    start_date = end_date - timedelta(days=days_back)

    async with AsyncSessionLocal() as db:
        log_id = await _create_ingestion_log(
            db, "ANGEL_ONE", job_type,
            date_start=start_date.date(), date_end=end_date.date(),
        )
        await db.commit()

        try:
            # Angel One SDK is synchronous — run in thread pool
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None,
                lambda: angel_one.get_candles(symbol_token, exchange, interval, start_date, end_date)
            )

            if df is None or df.empty:
                await _complete_ingestion_log(
                    db, log_id, "success",
                    rows_fetched=0, rows_inserted=0,
                    details={"message": "No candle data returned (check Angel One credentials)"},
                )
                await db.commit()
                return {"status": "success", "rows_fetched": 0, "rows_inserted": 0,
                        "message": "No data (check Angel One credentials in .env)"}

            rows_fetched = len(df)
            records = []
            for _, row in df.iterrows():
                records.append({
                    "timestamp": pd.to_datetime(row["timestamp"]),
                    "symbol_token": str(row.get("symbol_token", symbol_token)),
                    "exchange": str(row.get("exchange", exchange)),
                    "interval": str(row.get("interval", interval)),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(row["volume"]) if pd.notna(row.get("volume")) else 0,
                    "data_source": "ANGEL_ONE",
                })

            if records:
                stmt = pg_insert(OHLCVCandle).values(records)
                stmt = stmt.on_conflict_do_nothing(constraint="uq_ohlcv_candle")
                result = await db.execute(stmt)
                rows_inserted = result.rowcount if result.rowcount else 0
            else:
                rows_inserted = 0

            await _complete_ingestion_log(
                db, log_id, "success",
                rows_fetched=rows_fetched,
                rows_inserted=rows_inserted,
                rows_skipped=rows_fetched - rows_inserted,
            )
            await db.commit()

            logger.info(
                "angel_one_candles_ingested",
                symbol_token=symbol_token,
                interval=interval,
                rows_fetched=rows_fetched,
                rows_inserted=rows_inserted,
            )

            return {
                "status": "success",
                "rows_fetched": rows_fetched,
                "rows_inserted": rows_inserted,
                "rows_skipped": rows_fetched - rows_inserted,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error("angel_one_ingestion_failed", error=error_msg)
            await _complete_ingestion_log(db, log_id, "failed", error_message=error_msg)
            await db.commit()
            return {"status": "failed", "error": error_msg}


# ─────────────────────────────────────────────
# DATA STATUS — summary of all stored data
# ─────────────────────────────────────────────

async def get_data_status() -> dict:
    """Return row counts and last ingestion times for all data tables."""
    async with AsyncSessionLocal() as db:
        # Row counts
        settlements_count = (await db.execute(
            select(func.count(OptionSettlement.id))
        )).scalar() or 0

        global_count = (await db.execute(
            select(func.count(GlobalMarketData.id))
        )).scalar() or 0

        candles_count = (await db.execute(
            select(func.count(OHLCVCandle.id))
        )).scalar() or 0

        # Last successful ingestion per source
        last_ingestions = {}
        for source in ["NSE_BHAVCOPY", "YFINANCE", "ANGEL_ONE"]:
            result = await db.execute(
                select(DataIngestionLog)
                .where(
                    DataIngestionLog.source == source,
                    DataIngestionLog.status == "success",
                )
                .order_by(DataIngestionLog.completed_at.desc())
                .limit(1)
            )
            log = result.scalar_one_or_none()
            last_ingestions[source] = {
                "last_success": log.completed_at.isoformat() if log else None,
                "rows_inserted": log.rows_inserted if log else 0,
            }

        return {
            "tables": {
                "option_settlements": settlements_count,
                "global_market_data": global_count,
                "ohlcv_candles": candles_count,
            },
            "last_ingestions": last_ingestions,
        }
