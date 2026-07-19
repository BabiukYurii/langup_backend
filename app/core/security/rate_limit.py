"""Redis-backed request quotas, used as FastAPI dependencies.

A fixed window per key: cheap (one INCR plus one EXPIRE) and accurate enough
for what this guards — password guessing and abuse of a CPU-bound model. It can
let through up to two windows' worth of requests at a boundary; a sliding
window would cost more Redis work than that edge is worth here.

Redis being down must never lock users out, so failures are logged and allowed.
"""

import logging

import redis.asyncio as redis
from fastapi import Request

from app.core import settings
from app.core.exc import RateLimitedException

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis.url, socket_connect_timeout=2, socket_timeout=2)
    return _client


def client_ip(request: Request) -> str:
    """Caller's address, trusting the proxy header we sit behind."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce(key: str, limit: int, window_seconds: int) -> None:
    if not settings.rate_limit.RATE_LIMIT_ENABLED:
        return
    try:
        count = await _redis().incr(key)
        if count == 1:
            await _redis().expire(key, window_seconds)
    except Exception:  # noqa: BLE001 — a Redis outage must not lock anyone out
        logger.exception("Rate limit check failed for %s, allowing the request", key)
        return
    if count > limit:
        raise RateLimitedException(window_seconds)


class RateLimiter:
    """Dependency that counts requests per client against one quota."""

    def __init__(self, name: str, limit: int, window_seconds: int) -> None:
        self.name = name
        self.limit = limit
        self.window_seconds = window_seconds

    async def __call__(self, request: Request) -> None:
        await enforce(f"ratelimit:{self.name}:{client_ip(request)}", self.limit, self.window_seconds)


auth_rate_limit = RateLimiter(
    "auth",
    settings.rate_limit.RATE_LIMIT_AUTH_ATTEMPTS,
    settings.rate_limit.RATE_LIMIT_AUTH_WINDOW_SECONDS,
)

generation_rate_limit = RateLimiter(
    "generation",
    settings.rate_limit.RATE_LIMIT_GENERATION_ATTEMPTS,
    settings.rate_limit.RATE_LIMIT_GENERATION_WINDOW_SECONDS,
)
