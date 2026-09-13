"""Postgres advisory lock guarding a single pipeline run per application.

The lock is held on a dedicated connection for the lifetime of the run so a
second concurrent trigger cannot execute the same pipeline twice. Session-level
locks are released automatically if the connection drops, so a crashed run does
not stay locked forever.

Lock key namespace: the ``kyc_pipeline:`` prefix is reserved for this purpose.
Do not reuse it for any other advisory lock.
"""
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text

from app.database import engine

_LOCK_PREFIX = "kyc_pipeline:"


def _lock_key(application_id: UUID) -> str:
    return f"{_LOCK_PREFIX}{application_id}"


async def is_pipeline_locked(application_id: UUID) -> bool:
    """Probe whether another run currently holds the lock."""
    async with advisory_lock(application_id) as acquired:
        return not acquired


@asynccontextmanager
async def advisory_lock(application_id: UUID):
    """Yield ``True`` if the lock was acquired, ``False`` if already held."""
    connection = await engine.connect()
    acquired = False
    try:
        acquired = bool(
            (
                await connection.execute(
                    text("SELECT pg_try_advisory_lock(hashtext(:key)::bigint)"),
                    {"key": _lock_key(application_id)},
                )
            ).scalar()
        )
        yield acquired
        if acquired:
            await connection.execute(
                text("SELECT pg_advisory_unlock(hashtext(:key)::bigint)"),
                {"key": _lock_key(application_id)},
            )
    finally:
        await connection.close()
