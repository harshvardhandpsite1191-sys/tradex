"""
AI-QROS — Celery Application
Phase 0: Project Foundation
Task queue for all background processing
"""

from celery import Celery
from app.config import settings

celery_app = Celery(
    "aiqros",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "celery_tasks.data_tasks",       # Phase 2: data ingestion
        "celery_tasks.quality_tasks",    # Phase 3: data quality
        "celery_tasks.feature_tasks",    # Phase 4: feature computation
        "celery_tasks.behaviour_tasks",  # Phase 5: behaviour extraction
        "celery_tasks.research_tasks",   # Phase 6-9: research pipeline
        "celery_tasks.learning_tasks",   # Phase 22: daily learning cycle
    ]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "celery_tasks.data_tasks.*":      {"queue": "data"},
        "celery_tasks.quality_tasks.*":   {"queue": "quality"},
        "celery_tasks.feature_tasks.*":   {"queue": "features"},
        "celery_tasks.research_tasks.*":  {"queue": "research"},
        "celery_tasks.learning_tasks.*":  {"queue": "learning"},
    },
    # NOTE: beat_schedule entries are added here when each phase is built.
    # Phase 2 will add: data ingestion schedules
    # Phase 4 will add: daily feature computation schedule
    # Phase 22 will add: daily learning cycle schedule
    beat_schedule={},
)

