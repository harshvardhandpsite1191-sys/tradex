"""
AI-QROS — Logging Middleware
Phase 0: Project Foundation
Structured JSON logging for every request + system events
"""

import time
import uuid
import logging
import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings

# ─────────────────────────────────────────────
# Structlog configuration — structured JSON output
# ─────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer() if settings.DEBUG else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG if settings.DEBUG else logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("aiqros")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs every incoming HTTP request with:
    - Request ID (UUID)
    - Method, path, status code
    - Response time in milliseconds
    - User agent
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start_time = time.time()

        # Bind request ID to all log entries in this request context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Add request ID to response headers for tracing
        request.state.request_id = request_id

        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            query=str(request.url.query),
            client_ip=request.client.host if request.client else "unknown",
        )

        try:
            response = await call_next(request)
            process_time_ms = round((time.time() - start_time) * 1000, 2)

            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=process_time_ms,
            )

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time-Ms"] = str(process_time_ms)
            return response

        except Exception as exc:
            process_time_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                error=str(exc),
                duration_ms=process_time_ms,
            )
            raise
