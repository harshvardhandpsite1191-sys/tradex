"""
AI-QROS — Behaviour Extraction Celery Tasks
Phase 5: Behaviour Extraction

Background tasks for scheduled and on-demand behaviour extraction.
Triggered by:
  - APScheduler (daily post-feature-computation)
  - API router (manual POST /behaviours/extract/async)
"""

import asyncio
from datetime import date
from celery import shared_task
import structlog

logger = structlog.get_logger("aiqros.celery.behaviour_tasks")


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@shared_task(name="celery_tasks.behaviour_tasks.extract_daily_behaviours_task")
def extract_daily_behaviours_task(trade_date_str: str = None):
    """
    Extract behaviours for ALL target symbols for a given date.
    Scheduled: Daily at 8:00 PM IST (after feature computation).
    """
    trade_dt = date.fromisoformat(trade_date_str) if trade_date_str else date.today()
    logger.info("task_started", task="extract_daily_behaviours", trade_date=str(trade_dt))
    from app.services.behaviour_engine import extract_daily_behaviours
    result = _run_async(extract_daily_behaviours(trade_dt, triggered_by="scheduler"))
    logger.info("task_completed", task="extract_daily_behaviours", result=result)
    return result


@shared_task(name="celery_tasks.behaviour_tasks.extract_symbol_behaviours_task")
def extract_symbol_behaviours_task(symbol: str, trade_date_str: str = None):
    """Extract behaviours for a single symbol on a given date."""
    trade_dt = date.fromisoformat(trade_date_str) if trade_date_str else date.today()
    logger.info("task_started", task="extract_symbol_behaviours", symbol=symbol)
    from app.services.behaviour_engine import extract_behaviours_for_date
    result = _run_async(extract_behaviours_for_date(symbol, trade_dt, triggered_by="manual"))
    logger.info("task_completed", task="extract_symbol_behaviours", result=result)
    return result
