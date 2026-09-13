"""Shared test helpers for application creation, authorization and AI stubs."""
import os
from importlib import import_module

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.audit_log import AuditLog
from app.models.risk_score import RiskScore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
ID_CARD = os.path.join(FIXTURES, "id_card.jpeg")
SELFIE = os.path.join(FIXTURES, "selfie.jpeg")


async def create_application(client, name="Test User", **extra):
    """Create an application and return ``(application_id, access_token)``."""
    response = await client.post(
        "/api/v1/applications/", json={"name": name, **extra}
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return data["application_id"], data["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def install_ai_stubs(monkeypatch, face_delay=0.0):
    """Stub the heavy AI services and return a call-counter dict.

    ``face_delay`` holds the face stage open so concurrent pipeline calls
    genuinely overlap (used to exercise the advisory lock).
    """
    ocr_module = import_module("app.services.ocr_service")
    face_module = import_module("app.services.face_service")
    liveness_module = import_module("app.services.liveness_service")
    entity_module = import_module("app.services.entity_service")

    calls = {"ocr": 0, "face": 0}

    async def _fake_ocr(image_path, use_fallback=True):
        calls["ocr"] += 1
        return {
            "text": "Name: Abhi Sharma\nDOB: 01/01/1995\n123 Main Street, Mumbai",
            "raw_results": [],
            "confidence": 0.92,
            "ocr_engine": "easyocr",
        }

    async def _fake_face(selfie_path, id_photo_path):
        import asyncio

        import numpy as np

        calls["face"] += 1
        if face_delay:
            await asyncio.sleep(face_delay)
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

    monkeypatch.setattr(ocr_module.ocr_service, "extract_text", _fake_ocr)
    monkeypatch.setattr(face_module.face_service, "verify_faces", _fake_face)
    monkeypatch.setattr(liveness_module.liveness_service, "detect_liveness", _fake_liveness)
    monkeypatch.setattr(entity_module.entity_service, "extract_entities", _fake_entities)

    return calls


async def setup_application(client, name="Test User"):
    """Create an application and upload the full document set.

    Returns ``(application_id, access_token)``.
    """
    application_id, token = await create_application(client, name)

    for document_type in ("id_front", "address_proof", "utility_bill"):
        with open(ID_CARD, "rb") as handle:
            response = await client.post(
                f"/api/v1/documents/{application_id}/upload",
                params={"document_type": document_type},
                files={"file": (os.path.basename(ID_CARD), handle, "image/jpeg")},
                headers=auth_headers(token),
            )
        assert response.status_code == 200, response.text

    with open(SELFIE, "rb") as handle:
        response = await client.post(
            f"/api/v1/documents/{application_id}/upload",
            params={"document_type": "selfie"},
            files={"file": (os.path.basename(SELFIE), handle, "image/jpeg")},
            headers=auth_headers(token),
        )
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

    return application_id, token


async def risk_rows(application_id):
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                select(RiskScore).where(RiskScore.application_id == application_id)
            )
        ).scalars().all()


async def action_count(application_id, action):
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.application_id == application_id,
                    AuditLog.action_type == action,
                )
            )
        ).scalars().all()
        return len(rows)
