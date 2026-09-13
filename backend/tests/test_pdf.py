import os
import tempfile

import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.ocr_service import ocr_service
from tests.helpers import auth_headers, create_application


def _make_text_pdf(path: str) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Government of India\n"
        "Abhijna DS\n"
        "S/O Sudarshan\n"
        "PIN Code: 560085\n"
        "Your Aadhaar No. 6175 9496 0962\n",
        fontsize=12,
    )
    document.save(path)
    document.close()


@pytest.mark.asyncio
async def test_pdf_text_layer_extraction():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "id.pdf")
        _make_text_pdf(path)

        result = await ocr_service.extract_text(path)

    assert result["ocr_engine"] == "pdf"
    assert "Abhijna" in result["text"]
    assert "560085" in result["text"]


@pytest.mark.asyncio
async def test_upload_accepts_pdf_and_rejects_unsupported():
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        application_id, token = await create_application(client, "PDF User")

        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = os.path.join(tmp, "doc.pdf")
            _make_text_pdf(pdf_path)
            with open(pdf_path, "rb") as handle:
                response = await client.post(
                    f"/api/v1/documents/{application_id}/upload",
                    params={"document_type": "id_front"},
                    files={"file": ("doc.pdf", handle, "application/pdf")},
                    headers=auth_headers(token),
                )
        assert response.status_code == 200, response.text
        assert response.json()["mime_type"] == "application/pdf"

        response = await client.post(
            f"/api/v1/documents/{application_id}/upload",
            params={"document_type": "utility_bill"},
            files={"file": ("notes.txt", b"hello world", "text/plain")},
            headers=auth_headers(token),
        )
        assert response.status_code == 415
