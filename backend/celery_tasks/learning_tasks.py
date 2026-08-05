"""
AI-QROS — Continuous Learning Background Tasks
Phase 22: Continuous Learning
"""

import asyncio
from datetime import date
from celery import shared_task
import structlog

logger = structlog.get_logger("aiqros.celery.learning_tasks")


def _run(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


@shared_task(name="celery_tasks.learning_tasks.daily_learning_cycle_task")
def daily_learning_cycle_task(trade_date_str: str = None):
    """
    Evaluates drift across all targets and runs model update fine-tuning.
    Scheduled: Daily at 10:30 PM IST (after performance evaluation).
    """
    td = date.fromisoformat(trade_date_str) if trade_date_str else date.today()
    logger.info("task_started", task="daily_learning_cycle", trade_date=str(td))
    from app.services.continuous_learning import run_daily_drift_monitoring
    result = _run(run_daily_drift_monitoring(td))
    logger.info("task_completed", task="daily_learning_cycle", result=result)
    return result
