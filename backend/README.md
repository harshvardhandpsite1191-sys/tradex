# AI-QROS Backend

FastAPI application serving all AI-QROS intelligence APIs.

## Structure
```
app/
├── main.py           → FastAPI app entry point
├── config.py         → Environment settings
├── auth/             → JWT authentication
├── db/               → Database connection, seeders
├── middleware/       → Logging, rate limiting, error handling
├── models/           → SQLAlchemy DB models
└── routers/          → API route handlers
celery_app.py         → Celery task queue + beat scheduler
celery_tasks/         → Background task modules (added per phase)
```

## Running
```bash
uvicorn app.main:app --reload --port 8000
```

## Celery Worker
```bash
celery -A celery_app worker --loglevel=info
```

## Celery Beat (Scheduler)
```bash
celery -A celery_app beat --loglevel=info
```
