import os
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.main import app

@pytest.mark.asyncio
async def test_full_kyc_flow():
    application_id = "00000000-0000-0000-0000-000000000123"
    user_id = "11111111-1111-1111-1111-111111111111"

    # ---- Insert USER first ----
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("""
                INSERT INTO users (user_id, email, created_at)
                VALUES (:uid, 'test@example.com', NOW())
            """),
            {"uid": user_id}
        )
        await db.commit()

    # ---- Insert APPLICATION ----
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("""
                INSERT INTO kyc_applications (application_id, user_id, status, submitted_at)
                VALUES (:aid, :uid, 'PROCESSING', NOW())
            """),
            {"aid": application_id, "uid": user_id}
        )
        await db.commit()

    # ---- File paths ----
    id_path = "backend/tests/abhi_id.jpeg"
    selfie_path = "backend/tests/selfie.jpeg"

    assert os.path.exists(id_path)
    assert os.path.exists(selfie_path)

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:

        # Upload ID
        with open(id_path, "rb") as f1:
            upload_res = await client.post(
                f"/api/v1/documents/{application_id}/upload",
                params={"document_type": "id_front"},
                files={"file": ("abhi_id.jpeg", f1, "image/jpeg")},
            )
        assert upload_res.status_code == 200

        # Upload selfie
        with open(selfie_path, "rb") as f2:
            upload_res2 = await client.post(
                f"/api/v1/documents/{application_id}/upload",
                params={"document_type": "selfie"},
                files={"file": ("selfie.jpeg", f2, "image/jpeg")},
            )
        assert upload_res2.status_code == 200

        # Trigger verification
        verify_res = await client.post(f"/api/v1/verification/{application_id}/process")
        assert verify_res.status_code == 200

        # Fetch results
        result_res = await client.get(f"/api/v1/verification/{application_id}/results")
        assert result_res.status_code == 200

        print("\n--- RESULT ---")
        print(result_res.json())
        print("--------------")