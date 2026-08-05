"""
AI-QROS — Database Connection
Phase 0: Project Foundation
Connects to Neon PostgreSQL (free tier)
TimescaleDB: auto-detects availability, falls back to plain PG partitioning
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Async Engine — used by FastAPI endpoints
# ─────────────────────────────────────────────
db_url = settings.DATABASE_URL
connect_args = {}

if "asyncpg" in db_url:
    if "sslmode=" in db_url:
        import re
        # Strip sslmode from query string as asyncpg doesn't support it directly
        db_url = re.sub(r'[?&]sslmode=[a-zA-Z0-9_-]+', '', db_url)
    connect_args["ssl"] = "require"

engine = create_async_engine(
    db_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
    connect_args=connect_args,
)

# ─────────────────────────────────────────────
# Session Factory
# ─────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ─────────────────────────────────────────────
# Base Model — all SQLAlchemy models inherit from this
# ─────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────
# Dependency — FastAPI dependency injection
# ─────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """
    Provides a database session for FastAPI dependency injection.
    Automatically closes the session after the request completes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────
async def check_db_connection() -> bool:
    """Verify database connection is alive."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


# ─────────────────────────────────────────────
# Create all tables (called on startup)
# ─────────────────────────────────────────────
async def create_tables():
    """Create all tables defined in SQLAlchemy models."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("All database tables created/verified.")


# ─────────────────────────────────────────────
# TimescaleDB Auto-Detect + Hypertable Setup
# ─────────────────────────────────────────────
# Neon supports TimescaleDB Apache-2 license:
#   create_hypertable()  WORKS on Neon free tier
#   native compression   NOT available on Neon free
#   continuous aggregates incremental refresh   NOT available on Neon free
# We only use create_hypertable() which is fully supported.

_timescale_available = None  # cached after first check


async def is_timescaledb_available() -> bool:
    """
    Check if the TimescaleDB extension is available.
    Result is cached after first check.
    """
    global _timescale_available
    if _timescale_available is not None:
        return _timescale_available

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")
            )
            _timescale_available = result.fetchone() is not None
    except Exception:
        _timescale_available = False

    if _timescale_available:
        logger.info("timescaledb_available — hypertables enabled.")
    else:
        logger.warning(
            "timescaledb_not_available — using plain PostgreSQL with BRIN indexes. "
            "To enable: CREATE EXTENSION IF NOT EXISTS timescaledb; on your Neon instance."
        )

    return _timescale_available


async def create_hypertable_if_timescale(
    table_name: str,
    time_column: str = "timestamp",
    chunk_interval: str = "7 days",
) -> bool:
    """
    Create TimescaleDB hypertable for a table.
    If TimescaleDB is not available, falls back to plain PostgreSQL BRIN index.
    Returns True if hypertable was created, False if fell back to plain index.
    """
    if await is_timescaledb_available():
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text(
                    f"SELECT create_hypertable('{table_name}', '{time_column}', "
                    f"chunk_time_interval => INTERVAL '{chunk_interval}', "
                    f"if_not_exists => TRUE);"
                ))
                await session.commit()
                logger.info(f"hypertable_created: {table_name}")
                return True
        except Exception as e:
            logger.warning(f"hypertable_creation_failed for {table_name}: {e}")

    # Fallback: plain PostgreSQL BRIN index (efficient for time-series)
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{time_column}_brin "
                f"ON {table_name} USING BRIN ({time_column}) "
                f"WITH (pages_per_range = 128);"
            ))
            await session.commit()
            logger.info(f"BRIN index created as fallback for {table_name}")
    except Exception as e:
        logger.warning(f"BRIN index fallback also failed for {table_name}: {e}")

    return False


async def setup_timescale_extensions():
    """
    Attempt to enable TimescaleDB extension.
    Safe to call every startup — idempotent.
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text(
                "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"
            ))
            await session.commit()
            logger.info("timescaledb_extension_enabled")
    except Exception as e:
        logger.info(
            f"timescaledb_extension_skipped ({e}) — plain PostgreSQL will be used."
        )
