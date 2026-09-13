import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.security import security
from app.database import AsyncSessionLocal
from app.main import app
from app.models.user import User, UserRole
from importlib import import_module
from tests.helpers import auth_headers, create_application

ocr_module = import_module("app.services.ocr_service")
face_module = import_module("app.services.face_service")
liveness_module = import_module("app.services.liveness_service")
entity_module = import_module("app.services.entity_service")

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
ID_CARD = os.path.join(FIXTURES, "id_card.jpeg")
SELFIE = os.path.join(FIXTURES, "selfie.jpeg")


def _fake_ocr(text="Name: Abhi Sharma\nDOB: 01/01/1995\n123 Main Street, Mumbai"):
    async def _extract(image_path, use_fallback=True):
        return {
            "text": text,
            "raw_results": [],
            "confidence": 0.92,
            "ocr_engine": "easyocr",
        }

    return _extract


async def _fake_face(selfie_path, id_photo_path):
    import numpy as np

    embedding = np.ones(512, dtype=float)
    return {
        "is_match": True,
        "similarity": 0.91,
        "selfie_embedding": embedding,
        "id_embedding": embedding,
    }


async def _fake_liveness(frames):
    return {
        "is_live": True,
        "confidence": 0.88,
        "blink_count": 1,
        "motion": 0.02,
        "faces_detected": 4,
        "frames_processed": 4,
        "method": "mediapipe",
    }


async def _fake_entities(text):
    return {
        "name": "Abhi Sharma",
        "date_of_birth": "1995-01-01",
        "address": "Mumbai",
        "id_number": "ABCD12345678",
    }


@pytest.fixture(autouse=True)
def stub_ai_services(monkeypatch):
    """Stub heavy/download-dependent models so the integration test is fast."""
    monkeypatch.setattr(ocr_module.ocr_service, "extract_text", _fake_ocr())
    monkeypatch.setattr(face_module.face_service, "verify_faces", _fake_face)
    monkeypatch.setattr(liveness_module.liveness_service, "detect_liveness", _fake_liveness)
    monkeypatch.setattr(entity_module.entity_service, "extract_entities", _fake_entities)


async def _upload(client, application_id, document_type, path, token):
    with open(path, "rb") as handle:
        return await client.post(
            f"/api/v1/documents/{application_id}/upload",
            params={"document_type": document_type},
            files={"file": (os.path.basename(path), handle, "image/jpeg")},
            headers=auth_headers(token),
        )


@pytest.mark.asyncio
async def test_full_kyc_flow():
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        application_id, token = await create_application(
            client, "Test User", email="test@example.com", phone="1234567890"
        )

        for document_type in ("id_front", "address_proof", "utility_bill"):
            response = await _upload(
                client, application_id, document_type, ID_CARD, token
            )
            assert response.status_code == 200, response.text

        response = await _upload(client, application_id, "selfie", SELFIE, token)
        assert response.status_code == 200, response.text

        with open(SELFIE, "rb") as first, open(SELFIE, "rb") as second:
            response = await client.post(
                f"/api/v1/documents/{application_id}/upload/liveness",
                files=[
                    ("frames", ("frame0.jpg", first, "image/jpeg")),
                    ("frames", ("frame1.jpg", second, "image/jpeg")),
                ],
                headers=auth_headers(token),
            )
        assert response.status_code == 200, response.text

        response = await client.post(f"/api/v1/verification/{application_id}/process")
        assert response.status_code == 200, response.text

        response = await client.get(f"/api/v1/verification/{application_id}/results")
        assert response.status_code == 200, response.text
        result = response.json()

        assert result["status"] in {"approved", "review_required", "rejected"}
        assert result["risk_score"] is not None
        assert result["explainability"] is not None
        assert result["extracted"]["name"] == "Abhi Sharma"

        response = await client.get(f"/api/v1/audit/{application_id}/trail")
        assert response.status_code == 200
        action_types = {entry["action_type"] for entry in response.json()["audit_trail"]}
        assert {"OCR_EXTRACTED", "FACE_MATCHED", "RISK_CALCULATED"} <= action_types


@pytest.mark.asyncio
async def test_reviewer_rbac():
    email = "reviewer_test@kyc.ai"
    password = "reviewpass123"

    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if not existing:
            db.add(
                User(
                    name="Test Reviewer",
                    email=email,
                    password_hash=security.hash_password(password),
                    role=UserRole.REVIEWER,
                )
            )
            await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/applications/")
        assert response.status_code == 401

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]

        response = await client.get(
            "/api/v1/applications/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_missing_liveness_routes_to_review():
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        application_id, token = await create_application(
            client, "No Liveness", email="noliveness@example.com"
        )

        for document_type in ("id_front", "address_proof", "utility_bill"):
            assert (
                await _upload(client, application_id, document_type, ID_CARD, token)
            ).status_code == 200
        assert (await _upload(client, application_id, "selfie", SELFIE, token)).status_code == 200

        response = await client.post(f"/api/v1/verification/{application_id}/process")
        assert response.status_code == 200

        response = await client.get(f"/api/v1/verification/{application_id}/results")
        assert response.status_code == 200
        assert response.json()["status"] == "review_required"

        response = await client.get(f"/api/v1/audit/{application_id}/trail")
        actions = {entry["action_type"] for entry in response.json()["audit_trail"]}
        assert "LIVENESS_NOT_CAPTURED" in actions
