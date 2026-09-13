import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import auth as auth_module
from app.config import settings
from app.core import rate_limit as rate_limit_module
from app.core.rate_limit import LoginRateLimiter
from app.main import app


def _degraded_limiter(monkeypatch, fail_counter=None):
    """A limiter whose Redis backend always fails (forces in-memory path)."""
    limiter = LoginRateLimiter()

    async def _boom(*args, **kwargs):
        if fail_counter is not None:
            fail_counter["calls"] += 1
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(limiter, "_check_redis", _boom)
    return limiter


@pytest.mark.asyncio
async def test_memory_limiter_blocks_after_limit(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    limiter = _degraded_limiter(monkeypatch)

    results = [await limiter.check("k", limit=3, window=60) for _ in range(4)]
    assert [allowed for allowed, _ in results] == [True, True, True, False]
    assert results[-1][1] >= 1


@pytest.mark.asyncio
async def test_degraded_backend_logs_error_once(caplog, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    limiter = _degraded_limiter(monkeypatch)

    with caplog.at_level(logging.ERROR, logger="app.rate_limit"):
        await limiter.check("k", limit=3, window=60)
        await limiter.check("k", limit=3, window=60)

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "RATE LIMITER UNAVAILABLE" in errors[0].message


@pytest.mark.asyncio
async def test_circuit_breaker_skips_redis_during_cooldown(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(settings, "REDIS_COOLDOWN_SECONDS", 30)
    counter = {"calls": 0}
    limiter = _degraded_limiter(monkeypatch, fail_counter=counter)

    for _ in range(5):
        await limiter.check("k", limit=3, window=60)

    assert counter["calls"] == 1


@pytest.mark.asyncio
async def test_probes_redis_again_after_cooldown(caplog, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(settings, "REDIS_COOLDOWN_SECONDS", 30)

    clock = {"now": 1000.0}
    monkeypatch.setattr(rate_limit_module.time, "monotonic", lambda: clock["now"])

    limiter = LoginRateLimiter()
    calls = {"n": 0}

    async def _flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("redis unavailable")
        return True, 0

    monkeypatch.setattr(limiter, "_check_redis", _flaky)

    await limiter.check("k", limit=3, window=60)  # fails, trips breaker
    await limiter.check("k", limit=3, window=60)  # within cooldown, skipped
    assert calls["n"] == 1

    clock["now"] += 31
    with caplog.at_level(logging.INFO, logger="app.rate_limit"):
        await limiter.check("k", limit=3, window=60)  # probes again, succeeds

    assert calls["n"] == 2
    assert any("recovered" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_memory_only_when_redis_url_unset(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "REDIS_URL", "")
    limiter = LoginRateLimiter()
    calls = {"n": 0}

    async def _boom(*args, **kwargs):
        calls["n"] += 1
        raise AssertionError("Redis must not be contacted when REDIS_URL is unset")

    monkeypatch.setattr(limiter, "_check_redis", _boom)

    results = [await limiter.check("k", limit=2, window=60) for _ in range(3)]
    assert calls["n"] == 0
    assert [allowed for allowed, _ in results] == [True, True, False]


@pytest.mark.asyncio
async def test_login_returns_429(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT", 2)
    monkeypatch.setattr(settings, "LOGIN_RATE_WINDOW_SECONDS", 60)
    monkeypatch.setattr(auth_module, "login_rate_limiter", _degraded_limiter(monkeypatch))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"email": "nobody@kyc.ai", "password": "wrong"}
        first = await client.post("/api/v1/auth/login", json=payload)
        second = await client.post("/api/v1/auth/login", json=payload)
        third = await client.post("/api/v1/auth/login", json=payload)

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert third.headers.get("Retry-After")
