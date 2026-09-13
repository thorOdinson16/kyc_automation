"""Stress-tests the per-application pipeline lock.

Repeatedly triggers two concurrent `process_kyc_pipeline` runs for the same
application and asserts the Postgres advisory lock (`app/core/pipeline_lock.py`)
admits exactly one real run and rejects the other. This is the in-repo evidence
that the lock is stable under contention, rather than a one-off manual check.

Override the iteration count with ``PIPELINE_STRESS_ITERATIONS`` (default 10).
"""
import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.pipeline import process_kyc_pipeline
from app.main import app
from tests.helpers import (
    action_count,
    install_ai_stubs,
    risk_rows,
    setup_application,
)

ITERATIONS = int(os.getenv("PIPELINE_STRESS_ITERATIONS", "10"))


@pytest.fixture(autouse=True)
def stub_ai_services(monkeypatch):
    # Hold the face stage open so the two runs are guaranteed to overlap.
    return install_ai_stubs(monkeypatch, face_delay=0.3)


@pytest.mark.asyncio
async def test_pipeline_lock_allows_exactly_one_run_under_concurrency():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for iteration in range(ITERATIONS):
            application_id, _ = await setup_application(
                client, f"Stress {iteration}"
            )

            results = await asyncio.gather(
                process_kyc_pipeline(application_id),
                process_kyc_pipeline(application_id),
            )

            statuses = [result["status"] for result in results]
            assert statuses.count("completed") == 1, f"iteration {iteration}: {statuses}"
            assert (
                statuses.count("already_running") == 1
            ), f"iteration {iteration}: {statuses}"
            assert (
                await action_count(application_id, "RISK_CALCULATED") == 1
            ), f"iteration {iteration}: duplicate risk calculation"
            assert len(await risk_rows(application_id)) == 1, (
                f"iteration {iteration}: duplicate risk rows"
            )
