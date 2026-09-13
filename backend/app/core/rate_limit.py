"""Login rate limiting.

Primary backend is Redis (a fixed-window counter) so the limit is shared across
workers. If ``REDIS_URL`` is not configured we use the in-process window only.

When Redis *is* configured but unreachable we fail open to the in-process window
and trip a circuit breaker: the first failure is logged loudly at ERROR, then we
stop probing Redis for ``REDIS_COOLDOWN_SECONDS`` so a dead cache cannot add
latency (or log volume) to every login. The connection is configured to fail
fast (short socket timeouts, no exponential retries) rather than inherit
redis-py's multi-second default retry policy.
"""
import logging
import time
from collections import defaultdict, deque
from typing import Dict, Tuple

from redis import asyncio as aioredis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from app.config import settings

logger = logging.getLogger("app.rate_limit")


class LoginRateLimiter:
    """Fixed-window (Redis) / sliding-window (memory) request limiter."""

    def __init__(self) -> None:
        self._redis = None
        self._memory: Dict[str, deque] = defaultdict(deque)
        self._redis_unavailable_until = 0.0
        self._redis_down = False

    @property
    def _redis_configured(self) -> bool:
        return bool(settings.REDIS_URL)

    async def _client(self):
        if self._redis is None:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                retry=Retry(NoBackoff(), 0),
            )
        return self._redis

    async def check(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        """Return ``(allowed, retry_after_seconds)`` for ``key``."""
        if not settings.RATE_LIMIT_ENABLED:
            return True, 0
        if not self._redis_configured:
            return self._check_memory(key, limit, window)
        if time.monotonic() < self._redis_unavailable_until:
            return self._check_memory(key, limit, window)

        try:
            result = await self._check_redis(key, limit, window)
        except Exception:  # noqa: BLE001 - any backend error must degrade safely
            self._on_redis_failure()
            return self._check_memory(key, limit, window)

        self._on_redis_success()
        return result

    def _on_redis_failure(self) -> None:
        first_failure = not self._redis_down
        self._redis_down = True
        self._redis_unavailable_until = (
            time.monotonic() + settings.REDIS_COOLDOWN_SECONDS
        )
        if first_failure:
            logger.error(
                "LOGIN RATE LIMITER UNAVAILABLE — falling back to in-process "
                "limiting; requests may not be limited across workers",
                exc_info=True,
            )
        else:
            logger.debug("Rate limiter still degraded; using in-process limiting")

    def _on_redis_success(self) -> None:
        if self._redis_down:
            logger.info("Rate limiter recovered; using Redis backend")
        self._redis_down = False
        self._redis_unavailable_until = 0.0

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
