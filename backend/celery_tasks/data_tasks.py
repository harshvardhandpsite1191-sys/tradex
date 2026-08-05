"""
AI-QROS — Data Ingestion Celery Tasks
Phase 2: Data Infrastructure

Background tasks for scheduled and on-demand data fetching.
These are triggered by:
  - APScheduler (daily cron jobs)
  - API router (manual /data/ingest/* endpoints)

All tasks call the data_ingestion service which handles
DB storage and ingestion logging.
"""

import asyncio
from datetime import date, timedelta
from celery import shared_task
import structlog

logger = structlog.get_logger("aiqros.celery.data_tasks")


def _run_async(coro):
    """Helper to run async functions from synchronous Celery tasks."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If there's already a running loop (shouldn't happen in Celery worker)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ─────────────────────────────────────────────
# Daily Fetch Tasks (triggered by APScheduler)
# ─────────────────────────────────────────────

@shared_task(name="celery_tasks.data_tasks.fetch_daily_bhavcopy")
def fetch_daily_bhavcopy():
    """
    Download latest NSE F&O Bhavcopy and store in option_settlements.
    Scheduled: Daily at 6:00 PM IST (after NSE publishes ~5:30 PM).
    """
    logger.info("task_started", task="fetch_daily_bhavcopy")
    from app.services.data_ingestion import ingest_bhavcopy
    result = _run_async(ingest_bhavcopy(target_date=None, job_type="daily_fetch"))
    logger.info("task_completed", task="fetch_daily_bhavcopy", result=result)
    return result


@shared_task(name="celery_tasks.data_tasks.fetch_global_markets")
def fetch_global_markets():
    """
    Download latest global market data (16 factors) from yfinance.
    Scheduled: Daily at 7:00 AM IST (after US market close).
    """
    logger.info("task_started", task="fetch_global_markets")
    from app.services.data_ingestion import ingest_global_markets
    result = _run_async(ingest_global_markets(job_type="daily_fetch"))
    logger.info("task_completed", task="fetch_global_markets", result=result)
    return result


@shared_task(name="celery_tasks.data_tasks.fetch_angel_one_candles")
def fetch_angel_one_candles(
    symbol_token: str = "26000",
    exchange: str = "NSE",
    interval: str = "1day",
    days_back: int = 5,
):
    """
    Download OHLCV candles from Angel One SmartAPI.
    Scheduled: Daily at 6:15 PM IST (after market close).
    Defaults to NIFTY 50 index, daily candles, last 5 days.
    """
    logger.info(
        "task_started", task="fetch_angel_one_candles",
        symbol_token=symbol_token, interval=interval,
    )
    from app.services.data_ingestion import ingest_angel_one_candles
    result = _run_async(
        ingest_angel_one_candles(
            symbol_token=symbol_token,
            exchange=exchange,
            interval=interval,
            days_back=days_back,
            job_type="daily_fetch",
        )
    )
    logger.info("task_completed", task="fetch_angel_one_candles", result=result)
    return result


# ─────────────────────────────────────────────
# Backfill Tasks (triggered by API on-demand)
# ─────────────────────────────────────────────

@shared_task(name="celery_tasks.data_tasks.backfill_bhavcopy")
def backfill_bhavcopy(start_date_str: str, end_date_str: str):
    """
    Backfill NSE Bhavcopy for a date range.
    Triggered manually via POST /data/ingest/bhavcopy/backfill.
    Dates are ISO format strings (YYYY-MM-DD).
    """
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)
    logger.info(
        "task_started", task="backfill_bhavcopy",
        start=start_date_str, end=end_date_str,
    )
    from app.services.data_ingestion import ingest_bhavcopy_range
    result = _run_async(ingest_bhavcopy_range(start, end))
    logger.info("task_completed", task="backfill_bhavcopy", result=result)
    return result


@shared_task(name="celery_tasks.data_tasks.backfill_global_markets")
def backfill_global_markets(start_date_str: str, end_date_str: str):
    """
    Backfill global market data for a date range.
    Triggered manually via POST /data/ingest/global/backfill.
    """
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)
    logger.info(
        "task_started", task="backfill_global_markets",
        start=start_date_str, end=end_date_str,
    )
    from app.services.data_ingestion import ingest_global_markets
    result = _run_async(
        ingest_global_markets(start_date=start, end_date=end, job_type="backfill")
    )
    logger.info("task_completed", task="backfill_global_markets", result=result)
    return result
