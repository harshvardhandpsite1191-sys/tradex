"""
AI-QROS — Data Quality Celery Tasks
Phase 3: Data Quality & Governance

Background tasks for scheduled and on-demand data quality checks.
Triggered by:
  - APScheduler (daily post-ingestion quality run)
  - API router (manual POST /quality/run/async)
"""

import asyncio
from celery import shared_task
import structlog

logger = structlog.get_logger("aiqros.celery.quality_tasks")


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


@shared_task(name="celery_tasks.quality_tasks.run_quality_checks_task")
def run_quality_checks_task(source: str = "ALL", triggered_by: str = "manual"):
    """
    Run all quality checks for a given data source.
    Creates a DataQualityReport with individual DataQualityCheck entries.
    """
    logger.info("task_started", task="run_quality_checks", source=source)
    from app.services.quality_engine import run_quality_checks
    result = _run_async(run_quality_checks(source=source, triggered_by=triggered_by))
    logger.info("task_completed", task="run_quality_checks", result=result)
    return result


@shared_task(name="celery_tasks.quality_tasks.daily_quality_run")
def daily_quality_run():
    """
    Daily quality check across ALL sources.
    Scheduled: Daily at 7:00 PM IST (after all ingestion jobs complete).
    """
    logger.info("task_started", task="daily_quality_run")
    from app.services.quality_engine import run_quality_checks
    result = _run_async(run_quality_checks(source="ALL", triggered_by="scheduler"))
    logger.info("task_completed", task="daily_quality_run", result=result)
    return result
