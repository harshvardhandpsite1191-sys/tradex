"""
AI-QROS — Feature Computation Celery Tasks
Phase 4: Feature Engineering

Background tasks for scheduled and on-demand feature computation.
Triggered by:
  - APScheduler (daily post-ingestion feature computation)
  - API router (manual POST /features/compute/async)
"""

import asyncio
from datetime import date
from celery import shared_task
import structlog

logger = structlog.get_logger("aiqros.celery.feature_tasks")


def _run_async(coro):
    """Helper to run async functions from synchronous Celery tasks."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@shared_task(name="celery_tasks.feature_tasks.compute_daily_features_task")
def compute_daily_features_task(trade_date_str: str = None):
    """
    Compute features for ALL target symbols for a given date.
    Scheduled: Daily at 7:30 PM IST (after quality checks complete).
    """
    trade_dt = date.fromisoformat(trade_date_str) if trade_date_str else date.today()
    logger.info("task_started", task="compute_daily_features", trade_date=str(trade_dt))
    from app.services.feature_engine import compute_daily_features
    result = _run_async(compute_daily_features(trade_dt, triggered_by="scheduler"))
    logger.info("task_completed", task="compute_daily_features", result=result)
    return result


@shared_task(name="celery_tasks.feature_tasks.compute_symbol_features_task")
def compute_symbol_features_task(symbol: str, trade_date_str: str = None):
    """
    Compute features for a single symbol on a given date.
    Triggered on-demand via API.
    """
    trade_dt = date.fromisoformat(trade_date_str) if trade_date_str else date.today()
    logger.info("task_started", task="compute_symbol_features", symbol=symbol, trade_date=str(trade_dt))
    from app.services.feature_engine import compute_features_for_date
    result = _run_async(compute_features_for_date(symbol, trade_dt, triggered_by="manual"))
    logger.info("task_completed", task="compute_symbol_features", result=result)
    return result
