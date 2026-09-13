import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import auth as auth_module
from app.config import settings
from app.core.rate_limit import LoginRateLimiter
from app.main import app


def _degraded_limiter(monkeypatch):
    """A limiter whose Redis backend always fails (forces in-memory path)."""
    limiter = LoginRateLimiter()

    async def _boom(*args, **kwargs):
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(limiter, "_check_redis", _boom)
    return limiter


@pytest.mark.asyncio
async def test_memory_limiter_blocks_after_limit(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    limiter = _degraded_limiter(monkeypatch)

    results = [await limiter.check("k", limit=3, window=60) for _ in range(4)]
    assert [allowed for allowed, _ in results] == [True, True, True, False]
    assert results[-1][1] >= 1


@pytest.mark.asyncio
async def test_degraded_backend_logs_error(caplog, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    limiter = _degraded_limiter(monkeypatch)

    with caplog.at_level(logging.ERROR, logger="app.rate_limit"):
        await limiter.check("k", limit=3, window=60)

    assert any("RATE LIMITER UNAVAILABLE" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_login_returns_429(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
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
