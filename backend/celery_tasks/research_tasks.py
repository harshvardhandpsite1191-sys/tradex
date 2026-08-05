"""
AI-QROS — Research Pipeline Celery Tasks
Phase 6-9: Hypothesis Generation → Testing → Historical Verification → Synthesis
"""

import asyncio
from datetime import date
from celery import shared_task, chain
import structlog

logger = structlog.get_logger("aiqros.celery.research_tasks")


def _run(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


@shared_task(name="celery_tasks.research_tasks.generate_hypotheses_task")
def generate_hypotheses_task(trade_date_str: str = None):
    """Phase 6: Generate hypotheses for all symbols."""
    td = date.fromisoformat(trade_date_str) if trade_date_str else date.today()
    from app.services.hypothesis_engine import generate_daily_hypotheses
    result = _run(generate_daily_hypotheses(td, triggered_by="scheduler"))
    logger.info("task_done", task="generate_hypotheses", result=result)
    return result


@shared_task(name="celery_tasks.research_tasks.test_hypotheses_task")
def test_hypotheses_task(trade_date_str: str = None):
    """Phase 7: Statistical testing of pending hypotheses."""
    td = date.fromisoformat(trade_date_str) if trade_date_str else date.today()
    from app.services.hypothesis_tester import run_daily_testing
    result = _run(run_daily_testing(td, triggered_by="scheduler"))
    logger.info("task_done", task="test_hypotheses", result=result)
    return result


@shared_task(name="celery_tasks.research_tasks.historical_verification_task")
def historical_verification_task(trade_date_str: str = None):
    """Phase 8: Historical verification / walk-forward backtest."""
    td = date.fromisoformat(trade_date_str) if trade_date_str else date.today()
    from app.services.historical_verifier import run_historical_verification
    result = _run(run_historical_verification(td, triggered_by="scheduler"))
    logger.info("task_done", task="historical_verification", result=result)
    return result


@shared_task(name="celery_tasks.research_tasks.research_synthesis_task")
def research_synthesis_task(trade_date_str: str = None):
    """Phase 9: Synthesise verified findings into actionable intelligence."""
    td = date.fromisoformat(trade_date_str) if trade_date_str else date.today()
    from app.services.research_synthesizer import run_synthesis
    result = _run(run_synthesis(td, triggered_by="scheduler"))
    logger.info("task_done", task="research_synthesis", result=result)
    return result


@shared_task(name="celery_tasks.research_tasks.run_full_research_pipeline_task")
def run_full_research_pipeline_task(trade_date_str: str = None):
    """Phase 6-9: Full sequential research pipeline."""
    td_str = trade_date_str or date.today().isoformat()
    logger.info("task_started", task="full_research_pipeline", trade_date=td_str)
    r1 = generate_hypotheses_task(td_str)
    r2 = test_hypotheses_task(td_str)
    r3 = historical_verification_task(td_str)
    r4 = research_synthesis_task(td_str)
    return {"generate": r1, "test": r2, "verify": r3, "synthesize": r4}
