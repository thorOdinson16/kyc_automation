from importlib import import_module

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.pipeline import get_stage_timings
from app.database import AsyncSessionLocal
from app.main import app
from tests.helpers import (
    action_count,
    install_ai_stubs,
    risk_rows,
    setup_application,
)

risk_module = import_module("app.services.risk_service")


@pytest.fixture(autouse=True)
def stub_ai_services(monkeypatch):
    return install_ai_stubs(monkeypatch)


@pytest.mark.asyncio
async def test_second_process_call_is_a_noop(stub_ai_services):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        application_id, _ = await setup_application(client, "Resume User")

        first = await client.post(f"/api/v1/verification/{application_id}/process")
        assert first.status_code == 200, first.text
        assert len(await risk_rows(application_id)) == 1

        second = await client.post(f"/api/v1/verification/{application_id}/process")
        assert second.status_code == 200, second.text
        assert second.json()["message"] == "Verification already completed"

        assert len(await risk_rows(application_id)) == 1
        assert await action_count(application_id, "RISK_CALCULATED") == 1
        # No re-OCR on the second call.
        assert stub_ai_services["ocr"] == 3

        async with AsyncSessionLocal() as db:
            timings = await get_stage_timings(db, application_id)
        assert {"ocr", "face", "liveness", "entities", "risk"} <= set(timings)
        assert all(value >= 0 for value in timings.values())


@pytest.mark.asyncio
async def test_concurrent_process_runs_once(monkeypatch):
    import asyncio

    from app.core.pipeline import process_kyc_pipeline

    # Hold the face stage open so the two calls genuinely overlap.
    install_ai_stubs(monkeypatch, face_delay=0.3)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        application_id, _ = await setup_application(client, "Concurrent User")

        results = await asyncio.gather(
            process_kyc_pipeline(application_id),
            process_kyc_pipeline(application_id),
        )

    statuses = sorted(result["status"] for result in results)
    assert statuses == ["already_running", "completed"]
    assert await action_count(application_id, "RISK_CALCULATED") == 1
    assert len(await risk_rows(application_id)) == 1


@pytest.mark.asyncio
async def test_resume_after_partial_failure_skips_completed_stages(monkeypatch, stub_ai_services):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        application_id, _ = await setup_application(client, "Resume Failure User")

        real_risk = risk_module.risk_service.calculate_risk_score

        async def _boom(features):
            raise RuntimeError("risk boom")

        monkeypatch.setattr(risk_module.risk_service, "calculate_risk_score", _boom)
        await client.post(f"/api/v1/verification/{application_id}/process")

        async with AsyncSessionLocal() as db:
            from app.models.application import KYCApplication

            application = await db.get(KYCApplication, application_id)
            assert application.status.value == "review_required"

        assert stub_ai_services["ocr"] == 3

        # Restore risk and retry: it should resume, not restart.
        monkeypatch.setattr(
            risk_module.risk_service, "calculate_risk_score", real_risk
        )
        retry = await client.post(f"/api/v1/verification/{application_id}/process")
        assert retry.status_code == 200, retry.text

        assert stub_ai_services["ocr"] == 3  # OCR not re-run
        assert await action_count(application_id, "OCR_EXTRACTED") == 1
        assert await action_count(application_id, "RISK_CALCULATED") == 1

        results = await client.get(f"/api/v1/verification/{application_id}/results")
        assert results.status_code == 200
        assert results.json()["status"] in {"approved", "review_required", "rejected"}
