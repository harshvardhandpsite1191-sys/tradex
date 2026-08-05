"""
AI-QROS — Rate Limiting Middleware
Phase 0: Project Foundation
Simple sliding-window rate limiter using Redis
"""

import time
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import redis.asyncio as aioredis
from app.config import settings

# Rate limit rules per route prefix
RATE_LIMITS = {
    "/auth/token":    {"requests": 10,   "window_seconds": 60},   # 10 logins/min
    "/auth/register": {"requests": 5,    "window_seconds": 60},   # 5 registrations/min
    "/live":          {"requests": 1200, "window_seconds": 60},   # 20 req/sec for live data
    "default":        {"requests": 300,  "window_seconds": 60},   # 300 req/min all other routes
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter.
    Uses Redis to track request counts per IP per route per window.
    """

    def __init__(self, app):
        super().__init__(app)
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            self._redis = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _get_limit(self, path: str) -> dict:
        for prefix, limit in RATE_LIMITS.items():
            if prefix != "default" and path.startswith(prefix):
                return limit
        return RATE_LIMITS["default"]

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health check and metrics
        if request.url.path in ["/health", "/metrics", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        limit = self._get_limit(path)

        try:
            redis = await self._get_redis()
            key = f"rate_limit:{client_ip}:{path}"
            window = limit["window_seconds"]
            max_requests = limit["requests"]

            # Sliding window using Redis sorted set
            now = time.time()
            window_start = now - window

            pipe = redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window)
            results = await pipe.execute()

            request_count = results[2]

            if request_count > max_requests:
                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "error": "Rate limit exceeded",
                        "retry_after_seconds": window,
                    },
                    headers={"Retry-After": str(window)},
                )

        except Exception:
            # If Redis is unavailable, allow the request through (fail open)
            pass

        return await call_next(request)
