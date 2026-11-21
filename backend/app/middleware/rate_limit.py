"""Redis-backed sliding-window rate limiter.

Keyed by user (JWT sub) when authenticated, otherwise client IP.
Uses a sorted set per key: scores are timestamps; entries older than the
window are trimmed atomically in a pipeline.
"""
import time

import redis.asyncio as aioredis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings

EXEMPT_PATHS = ("/api/v1/health", "/metrics", "/docs", "/openapi.json")

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(EXEMPT_PATHS) or request.method == "OPTIONS":
            return await call_next(request)

        settings = get_settings()
        identity = request.headers.get("authorization", "")[-24:] or (
            request.client.host if request.client else "unknown"
        )
        key = f"ratelimit:{identity}"
        now = time.time()
        window = settings.rate_limit_window_seconds

        try:
            r = get_redis()
            async with r.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(key, 0, now - window)
                pipe.zadd(key, {f"{now}": now})
                pipe.zcard(key)
                pipe.expire(key, window)
                _, _, count, _ = await pipe.execute()
        except Exception:
            # Fail open: never take the API down because Redis is unavailable.
            return await call_next(request)

        if count > settings.rate_limit_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"retry-after": str(window)},
            )
        return await call_next(request)
