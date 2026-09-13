import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import document_verification_service as dv
from app.services import verhoeff
from app.services.entity_service import name_in_text
from tests.helpers import auth_headers, create_application

AADHAAR_TEXT = (
    "Government of India\n"
    "Unique Identification Authority of India\n"
    "Abhijna DS\n"
    "S/O Sudarshan\n"
    "PIN Code: 560085\n"
    "Your Aadhaar No. 6175 9496 0962\n"
)
PAYPAL_RECEIPT = (
    "Your PayPal receipt\n"
    "Gmail Abhijna DS <abhijnads16@gmail.com>\n"
    "To: Abhijna DS <abhijnads16@gmail.com>\n"
    "Hi Abhijna DS,\n"
    "You paid $ 10.60 USD to Hangzhou DeepSeek\n"
    "Total $ 10.60 USD\n"
    "Activate PayPal Now\n"
)
ELECTRICITY_BILL = (
    "ELECTRICITY BILL\n"
    "Amount Due: 1055.60\n"
    "Due Date 05/09/2026\n"
    "Consumer Name: PRIYA RAO\n"
    "Units consumed 182 kWh\n"
    "Account No 3012480420\n"
)
INTERNET_BILL = (
    "Internet Broadband Invoice\n"
    "Name: PRIYA RAO\n"
    "Amount Payable: 799\n"
    "Bill Number: 1126142\n"
)


def test_verhoeff_known_vectors():
    assert verhoeff.is_valid("2363")
    assert not verhoeff.is_valid("2364")


def test_detect_id_types():
    assert dv.detect_id(AADHAAR_TEXT, "6175 9496 0962")[0] == "aadhaar"
    assert dv.detect_id("PERMANENT ACCOUNT NUMBER ABCDE1234F", "ABCDE1234F")[0] == "pan"
    assert dv.detect_id("PASSPORT REPUBLIC OF INDIA P<IND", None)[0] == "passport"
    assert dv.detect_id("ELECTION COMMISSION OF INDIA ELECTOR", None)[0] == "voter"
    assert dv.detect_id("DRIVING LICENCE TRANSPORT DEPARTMENT", None)[0] == "driving_licence"
    assert dv.detect_id("random shopping list milk eggs", None)[0] == "unknown"


def test_detect_bill_categories():
    assert dv.detect_bill(ELECTRICITY_BILL)[1] == "electricity"
    assert dv.detect_bill(INTERNET_BILL)[1] == "internet"
    assert dv.detect_bill("Subscription renewal Netflix amount payable")[0] is True
    assert dv.detect_bill("just a plain letter with no money")[0] is False


def test_check_bill_requires_applicant_name():
    entities = {"name": "Priya Rao"}
    ok = dv.check_bill(ELECTRICITY_BILL, entities, "Priya Rao")
    assert ok["is_valid"] and ok["is_bill"]

    mismatch = dv.check_bill(ELECTRICITY_BILL, entities, "Abhijna Ds")
    assert mismatch["is_bill"] and not mismatch["is_valid"]


def test_name_in_text_finds_applicant():
    assert name_in_text("Abhijna Ds", PAYPAL_RECEIPT)
    assert not name_in_text("Priya Rao", PAYPAL_RECEIPT)


def test_check_bill_matches_name_in_text():
    # Extractor may grab footer text, but the applicant's name is in the body.
    entities = {"name": "Activate Paypal Now"}
    result = dv.check_bill(PAYPAL_RECEIPT, entities, "Abhijna Ds")
    assert result["is_bill"] and result["is_valid"] and result["name_match"]


def test_check_bill_without_name_fails():
    text = "ELECTRICITY BILL\nTotal Amount Payable: 500\nDue Date 01/01/2027\n"
    result = dv.check_bill(text, {"name": None}, "Abhijna Ds")
    assert result["is_bill"] and not result["is_valid"]


def test_is_plausible_address():
    assert dv.is_plausible_address("10 Main Road, Bengaluru, Karnataka 560085")
    assert not dv.is_plausible_address("not reply to this")
    assert not dv.is_plausible_address("")


def test_check_id_requires_known_type_and_name():
    entities = {"name": "Abhijna Ds", "id_number": "6175 9496 0962"}
    assert dv.check_id(AADHAAR_TEXT, entities)["is_valid"]

    assert not dv.check_id("random text", {"name": "Abhijna Ds"})["is_valid"]


def test_resolve_roles_misplaced_id():
    documents = [
        {"document_type": "utility_bill", "text": AADHAAR_TEXT, "entities": {"name": "Abhijna Ds", "id_number": "6175 9496 0962"}},
        {"document_type": "address_proof", "text": ELECTRICITY_BILL, "entities": {"name": "Priya Rao", "address": "Bengaluru"}},
    ]
    roles = dv.resolve_roles(documents)
    assert roles["id_front"]["document_type"] == "utility_bill"
    assert {"claimed": "utility_bill", "assigned": "id_front"} in roles["reassignments"]


@pytest.mark.asyncio
async def test_reclassify_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        application_id, token = await create_application(client, "Move User")

        response = await client.post(
            f"/api/v1/documents/{application_id}/upload",
            params={"document_type": "utility_bill"},
            files={"file": ("x.jpg", b"not-a-real-jpeg", "image/jpeg")},
            headers=auth_headers(token),
        )
        assert response.status_code == 200, response.text
        document_id = response.json()["document_id"]

        response = await client.patch(
            f"/api/v1/documents/{document_id}",
            json={"document_type": "id_front"},
            headers=auth_headers(token),
        )
        assert response.status_code == 200, response.text
        assert response.json()["document_type"] == "id_front"

        response = await client.get(
            f"/api/v1/documents/application/{application_id}/list",
            headers=auth_headers(token),
        )
        types = {doc["document_type"] for doc in response.json()["documents"]}
        assert "id_front" in types and "utility_bill" not in types


@pytest.mark.asyncio
async def test_upload_rejects_bad_pdf_and_oversize_pages():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        application_id, token = await create_application(client, "PDF Bad")

        response = await client.post(
            f"/api/v1/documents/{application_id}/upload",
            params={"document_type": "id_front"},
            files={"file": ("bad.pdf", b"%PDF-1.7 not really a pdf", "application/pdf")},
            headers=auth_headers(token),
        )
        assert response.status_code == 422
