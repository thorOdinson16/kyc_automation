import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.security import security
from app.database import AsyncSessionLocal
from app.main import app
from app.models.user import User, UserRole
from tests.helpers import auth_headers, create_application

REVIEWER_EMAIL = "authz_reviewer@kyc.ai"
REVIEWER_PASSWORD = "authzreview123"


async def _ensure_reviewer():
    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.email == REVIEWER_EMAIL))
        ).scalar_one_or_none()
        if existing:
            return
        db.add(
            User(
                name="Authz Reviewer",
                email=REVIEWER_EMAIL,
                password_hash=security.hash_password(REVIEWER_PASSWORD),
                role=UserRole.REVIEWER,
            )
        )
        await db.commit()


async def _upload(client, application_id, token, document_type="id_front"):
    return await client.post(
        f"/api/v1/documents/{application_id}/upload",
        params={"document_type": document_type},
        files={"file": ("x.jpg", b"not-a-real-jpeg", "image/jpeg")},
        headers=auth_headers(token),
    )


@pytest.mark.asyncio
async def test_document_endpoints_require_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        application_id, token = await create_application(client, "Authz User")
        upload = await _upload(client, application_id, token)
        assert upload.status_code == 200, upload.text
        document_id = upload.json()["document_id"]

        response = await client.get(
            f"/api/v1/documents/application/{application_id}/list"
        )
        assert response.status_code == 401

        response = await client.get(f"/api/v1/documents/{document_id}/view")
        assert response.status_code == 401

        response = await client.post(
            f"/api/v1/documents/{application_id}/upload",
            params={"document_type": "utility_bill"},
            files={"file": ("x.jpg", b"not-a-real-jpeg", "image/jpeg")},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_cross_application_token_is_forbidden():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        owner_id, owner_token = await create_application(client, "Owner")
        other_id, other_token = await create_application(client, "Other")

        upload = await _upload(client, owner_id, owner_token)
        assert upload.status_code == 200, upload.text

        response = await client.get(
            f"/api/v1/documents/application/{owner_id}/list",
            headers=auth_headers(other_token),
        )
        assert response.status_code == 403

        response = await client.get(
            f"/api/v1/documents/application/{other_id}/list",
            headers=auth_headers(owner_token),
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_owner_and_reviewer_can_access_documents():
    await _ensure_reviewer()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        application_id, owner_token = await create_application(client, "Owner Two")
        upload = await _upload(client, application_id, owner_token)
        document_id = upload.json()["document_id"]

        response = await client.get(
            f"/api/v1/documents/application/{application_id}/list",
            headers=auth_headers(owner_token),
        )
        assert response.status_code == 200

        response = await client.get(
            f"/api/v1/documents/{document_id}/view",
            headers=auth_headers(owner_token),
        )
        assert response.status_code == 200

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD},
        )
        assert login.status_code == 200, login.text
        reviewer_token = login.json()["access_token"]

        response = await client.get(
            f"/api/v1/documents/application/{application_id}/list",
            headers=auth_headers(reviewer_token),
        )
        assert response.status_code == 200

        response = await client.get(
            f"/api/v1/documents/{document_id}/view",
            headers=auth_headers(reviewer_token),
        )
        assert response.status_code == 200
