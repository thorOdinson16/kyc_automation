"""Login rate limiting.

Primary backend is Redis (a fixed-window counter) so the limit is shared across
workers. If Redis is unreachable we degrade to a per-process in-memory sliding
window and log at ERROR level — a fail-open auth control that no-ops silently is
worse than no control at all, so the degradation must be loud.
"""
import logging
import time
from collections import defaultdict, deque
from typing import Dict, Tuple

from redis import asyncio as aioredis

from app.config import settings

logger = logging.getLogger("app.rate_limit")


class LoginRateLimiter:
    """Fixed-window (Redis) / sliding-window (memory) request limiter."""

    def __init__(self) -> None:
        self._redis = None
        self._memory: Dict[str, deque] = defaultdict(deque)

    async def _client(self):
        if self._redis is None:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def check(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        """Return ``(allowed, retry_after_seconds)`` for ``key``."""
        if not settings.RATE_LIMIT_ENABLED:
            return True, 0
        try:
            return await self._check_redis(key, limit, window)
        except Exception:  # noqa: BLE001 - any backend error must degrade safely
            logger.error(
                "LOGIN RATE LIMITER UNAVAILABLE — falling back to in-process "
                "limiting; requests may not be limited across workers",
                exc_info=True,
            )
            return self._check_memory(key, limit, window)

    async def _check_redis(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        client = await self._client()
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, window)
        if count > limit:
            ttl = await client.ttl(key)
            return False, max(int(ttl), 1)
        return True, 0

    def _check_memory(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        now = time.monotonic()
        bucket = self._memory[key]
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = int(window - (now - bucket[0])) + 1
            return False, max(retry_after, 1)
        bucket.append(now)
        return True, 0


login_rate_limiter = LoginRateLimiter()
