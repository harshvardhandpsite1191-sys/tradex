"""
AI-QROS — FastAPI Main Application
Phase 0 + Phase 2: Project Foundation + Data Infrastructure
Entry point for the entire backend
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
import structlog

from app.config import settings
from app.db.database import create_tables, check_db_connection, AsyncSessionLocal, setup_timescale_extensions, create_hypertable_if_timescale
from app.db.seeders import seed_default_rules
from app.db.knowledge_seeder import seed_knowledge_base
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.middleware.rate_limiter import RateLimitMiddleware
from app.middleware.error_handler import (
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
)
from app.scheduler import start_scheduler, stop_scheduler

# Routers
from app.routers import auth, governance, feature_registry, model_registry, knowledge, data, quality, features, behaviours, research, regimes, opening, expiry, scenarios, similarity, signals, predictions, strategies, recommendations, live, performance, learning

# Import Phase 2 models so they register with SQLAlchemy Base.metadata
import app.models.market_data  # noqa: F401
import app.models.data_quality  # noqa: F401
import app.models.feature_store  # noqa: F401
import app.models.behaviour  # noqa: F401  — Phase 5 behaviour tables
import app.models.research   # noqa: F401  — Phase 6-9 research tables
import app.models.opening    # noqa: F401  — Phase 11 opening tables
import app.models.expiry     # noqa: F401  — Phase 12 expiry tables
import app.models.scenario   # noqa: F401  — Phase 13 scenario tables
import app.models.signal     # noqa: F401  — Phase 15 signal tables
import app.models.recommendation # noqa: F401  — Phase 19 recommendation tables
import app.models.performance    # noqa: F401  — Phase 21 performance tables

logger = structlog.get_logger("aiqros.main")


# ─────────────────────────────────────────────
# Lifespan — startup and shutdown
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("aiqros_starting", version=settings.APP_VERSION)

    # 1. Verify DB connection
    db_ok = await check_db_connection()
    if not db_ok:
        logger.error("startup_failed", reason="Database connection failed")
        raise RuntimeError("Cannot connect to database. Check DATABASE_URL in .env")

    # 2. Attempt to enable TimescaleDB extension (auto-detects, safe to call always)
    await setup_timescale_extensions()

    # 3. Create all tables
    await create_tables()
    logger.info("database_tables_ready")

    # 4. Seed default rules into Rule Registry (Phase 0)
    async with AsyncSessionLocal() as db:
        await seed_default_rules(db)

    # 5. Seed 104 institutional concepts into Knowledge Base (Phase 1)
    async with AsyncSessionLocal() as db:
        await seed_knowledge_base(db)

    # 6. Setup TimescaleDB hypertables for Phase 2 time-series tables
    await create_hypertable_if_timescale("ohlcv_candles", "timestamp", "7 days")
    await create_hypertable_if_timescale("option_settlements", "trade_date", "30 days")
    await create_hypertable_if_timescale("global_market_data", "trade_date", "30 days")
    logger.info("timescale_hypertables_configured")

    # 7. Start APScheduler (in-process task scheduler — keeps alive on Render free)
    start_scheduler()

    logger.info("aiqros_ready", message="AI-QROS backend is running. Phase 0-9 complete.")

    yield  # App is running

    # Shutdown
    stop_scheduler()
    logger.info("aiqros_shutting_down")


# ─────────────────────────────────────────────
# FastAPI Application
# ─────────────────────────────────────────────
app = FastAPI(
    title="AI-QROS",
    description="Artificial Intelligence - Quantitative Research & Options Intelligence System",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Exception Handlers
# ─────────────────────────────────────────────
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)


# ─────────────────────────────────────────────
# Prometheus Metrics (Monitoring — Phase 0)
# ─────────────────────────────────────────────
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# ─────────────────────────────────────────────
# Routers — Phase 0
# ─────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(governance.router)
app.include_router(feature_registry.router)
app.include_router(model_registry.router)

# ─────────────────────────────────────────────
# Routers — Phase 1
# ─────────────────────────────────────────────
app.include_router(knowledge.router)

# ─────────────────────────────────────────────
# Routers — Phase 2
# ─────────────────────────────────────────────
app.include_router(data.router)

# ─────────────────────────────────────────────
# Routers — Phase 3
# ─────────────────────────────────────────────
app.include_router(quality.router)

# ─────────────────────────────────────────────
# Routers — Phase 4
# ─────────────────────────────────────────────
app.include_router(features.router)

app.include_router(behaviours.router)

# ─────────────────────────────────────────────
# Routers — Phase 6-9
# ─────────────────────────────────────────────
app.include_router(research.router)

# ─────────────────────────────────────────────
# Routers — Phase 10
# ─────────────────────────────────────────────
app.include_router(regimes.router)

# ─────────────────────────────────────────────
# Routers — Phase 11
# ─────────────────────────────────────────────
app.include_router(opening.router)

# ─────────────────────────────────────────────
# Routers — Phase 12
# ─────────────────────────────────────────────
app.include_router(expiry.router)

# ─────────────────────────────────────────────
# Routers — Phase 13
# ─────────────────────────────────────────────
app.include_router(scenarios.router)

# ─────────────────────────────────────────────
# Routers — Phase 14
# ─────────────────────────────────────────────
app.include_router(similarity.router)

# ─────────────────────────────────────────────
# Routers — Phase 15
# ─────────────────────────────────────────────
app.include_router(signals.router)

# ─────────────────────────────────────────────
# Routers — Phase 16
# ─────────────────────────────────────────────
app.include_router(predictions.router)

# ─────────────────────────────────────────────
# Routers — Phase 17
# ─────────────────────────────────────────────
app.include_router(strategies.router)

# ─────────────────────────────────────────────
# Routers — Phase 19
# ─────────────────────────────────────────────
app.include_router(recommendations.router)

# ─────────────────────────────────────────────
# Routers — Phase 20
# ─────────────────────────────────────────────
app.include_router(live.router)

# ─────────────────────────────────────────────
# Routers — Phase 21
# ─────────────────────────────────────────────
app.include_router(performance.router)

# ─────────────────────────────────────────────
# Routers — Phase 22
# ─────────────────────────────────────────────
app.include_router(learning.router)

# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    db_ok = await check_db_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "version": settings.APP_VERSION,
        "database": "connected" if db_ok else "disconnected",
        "phase": "Phase 22 — Continuous Learning",
    }


@app.get("/ping", tags=["System"])
async def ping():
    """
    Lightweight keep-alive endpoint.
    UptimeRobot (free) pings this every 5 minutes to prevent Render free tier from sleeping.
    Configure at: https://uptimerobot.com — Monitor Type: HTTP(s), URL: https://your-app.onrender.com/ping
    """
    return {"status": "alive"}


@app.get("/", tags=["System"])
async def root():
    return {
        "name": "AI-QROS",
        "description": "Artificial Intelligence - Quantitative Research & Options Intelligence System",
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }
