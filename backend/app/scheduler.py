"""
AI-QROS — APScheduler In-Process Scheduler
Phase 0/2: Replaces separate Celery Beat process on free hosting

Problem: Render free tier spins down background worker services.
Solution: Embed APScheduler inside the FastAPI process (which stays alive
          via UptimeRobot pinging /ping every 5 minutes).

This scheduler handles all timed tasks:
- Daily data fetching (after market close)
- Daily feature computation
- Daily learning cycle (Phase 22)
- Daily research cycle (Phase 6-9)

Celery is still used for heavy, on-demand tasks (ML training, backtesting).
APScheduler handles the lightweight scheduled triggers.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import structlog

logger = structlog.get_logger("aiqros.scheduler")

# Global scheduler instance
scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


def start_scheduler():
    """
    Start the APScheduler with all scheduled jobs.
    Called during FastAPI lifespan startup.
    Jobs are added here as each phase is built.
    """
    if scheduler.running:
        return

    # ── Phase 2 Jobs — Data Infrastructure ───────────────────────
    # These dispatch Celery tasks for background execution.
    # APScheduler is the lightweight trigger; Celery does the heavy work.

    def _trigger_bhavcopy():
        from celery_tasks.data_tasks import fetch_daily_bhavcopy
        fetch_daily_bhavcopy.delay()
        logger.info("scheduled_job_triggered", job="bhavcopy_daily")

    def _trigger_global_markets():
        from celery_tasks.data_tasks import fetch_global_markets
        fetch_global_markets.delay()
        logger.info("scheduled_job_triggered", job="global_daily")

    def _trigger_angel_one_candles():
        from celery_tasks.data_tasks import fetch_angel_one_candles
        fetch_angel_one_candles.delay()
        logger.info("scheduled_job_triggered", job="angel_one_daily")

    # Daily NSE Bhavcopy download — 6:00 PM IST (NSE publishes ~5:30 PM)
    scheduler.add_job(
        _trigger_bhavcopy,
        CronTrigger(hour=18, minute=0),
        id="bhavcopy_daily",
        replace_existing=True,
    )

    # Daily global markets data — 7:00 AM IST (after US market close)
    scheduler.add_job(
        _trigger_global_markets,
        CronTrigger(hour=7, minute=0),
        id="global_daily",
        replace_existing=True,
    )

    # Daily Angel One NIFTY candles — 6:15 PM IST (after Indian market close)
    scheduler.add_job(
        _trigger_angel_one_candles,
        CronTrigger(hour=18, minute=15),
        id="angel_one_daily",
        replace_existing=True,
    )

    # ── Phase 3 Jobs — Data Quality ───────────────────────────────

    def _trigger_quality_checks():
        from celery_tasks.quality_tasks import daily_quality_run
        daily_quality_run.delay()
        logger.info("scheduled_job_triggered", job="quality_daily")

    # Daily quality checks — 7:00 PM IST (after all ingestion jobs complete)
    scheduler.add_job(
        _trigger_quality_checks,
        CronTrigger(hour=19, minute=0),
        id="quality_daily",
        replace_existing=True,
    )

    # ── Phase 4 Jobs — Feature Engineering ─────────────────────────

    def _trigger_feature_computation():
        from celery_tasks.feature_tasks import compute_daily_features_task
        compute_daily_features_task.delay()
        logger.info("scheduled_job_triggered", job="features_daily")

    # Daily feature computation — 7:30 PM IST (after quality checks)
    scheduler.add_job(
        _trigger_feature_computation,
        CronTrigger(hour=19, minute=30),
        id="features_daily",
        replace_existing=True,
    )

    # ── Phase 5 Jobs — Behaviour Extraction ─────────────────────

    def _trigger_behaviour_extraction():
        from celery_tasks.behaviour_tasks import extract_daily_behaviours_task
        extract_daily_behaviours_task.delay()
        logger.info("scheduled_job_triggered", job="behaviours_daily")

    # Daily behaviour extraction — 8:00 PM IST (after feature computation)
    scheduler.add_job(
        _trigger_behaviour_extraction,
        CronTrigger(hour=20, minute=0),
        id="behaviours_daily",
        replace_existing=True,
    )

    # ── Phase 6-9 Jobs — Research Pipeline ──────────────────────

    def _trigger_research_pipeline():
        from celery_tasks.research_tasks import run_full_research_pipeline_task
        run_full_research_pipeline_task.delay()
        logger.info("scheduled_job_triggered", job="research_daily")

    # Daily research pipeline — 8:30 PM IST (after behaviour extraction)
    scheduler.add_job(
        _trigger_research_pipeline,
        CronTrigger(hour=20, minute=30),
        id="research_daily",
        replace_existing=True,
    )

    # ── Phase 10 Jobs — Regime Classification ───────────────────

    def _trigger_regime_classification():
        from app.services.regime_engine import run_daily_regime_classification
        import asyncio
        asyncio.run(run_daily_regime_classification())
        logger.info("scheduled_job_triggered", job="regimes_daily")

    scheduler.add_job(
        _trigger_regime_classification,
        CronTrigger(hour=21, minute=0),
        id="regimes_daily",
        replace_existing=True,
    )

    # ── Phase 11-19 Jobs — Signals & Recommendations ─────────────

    def _trigger_trade_generation():
        from app.services.opening_engine import run_daily_opening_intelligence
        from app.services.expiry_engine import run_daily_expiry_intelligence
        from app.services.signal_engine import run_daily_signal_generation
        from app.services.recommendation_engine import run_daily_recommendations
        import asyncio
        async def _run_flow():
            await run_daily_opening_intelligence()
            await run_daily_expiry_intelligence()
            await run_daily_signal_generation()
            await run_daily_recommendations()
        asyncio.run(_run_flow())
        logger.info("scheduled_job_triggered", job="trades_daily")

    scheduler.add_job(
        _trigger_trade_generation,
        CronTrigger(hour=21, minute=30),
        id="trades_daily",
        replace_existing=True,
    )

    # ── Phase 21 Jobs — Performance Tracking ────────────────────

    def _trigger_performance_tracking():
        from app.services.performance_tracker import run_daily_performance_tracking
        import asyncio
        asyncio.run(run_daily_performance_tracking())
        logger.info("scheduled_job_triggered", job="performance_daily")

    scheduler.add_job(
        _trigger_performance_tracking,
        CronTrigger(hour=22, minute=0),
        id="performance_daily",
        replace_existing=True,
    )

    # ── Phase 22 Jobs — Continuous Learning ─────────────────────

    def _trigger_learning_cycle():
        from celery_tasks.learning_tasks import daily_learning_cycle_task
        daily_learning_cycle_task.delay()
        logger.info("scheduled_job_triggered", job="learning_daily")

    scheduler.add_job(
        _trigger_learning_cycle,
        CronTrigger(hour=22, minute=30),
        id="learning_daily",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("scheduler_started", timezone="Asia/Kolkata", phase2_jobs=3, phase3_jobs=1, phase4_jobs=1, phase5_jobs=1, research_jobs=1, regime_jobs=1, trade_jobs=1, perf_jobs=1, learning_jobs=1)


def stop_scheduler():
    """Stop the scheduler gracefully during FastAPI lifespan shutdown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
