import pytest

from app.services.entity_service import (
    addresses_match,
    entity_service,
    names_match,
)

AADHAAR_TEXT = """Government of India
Unique Identification Authority of India
Enrollment No. : 0012/12026/01281
Abhijna DS
S/O: Sudarshan
#10 Sirangadhama, 10th Main, Hosakerehalli Extension
BSK 3rd Stage, Bengaluru
PO: Hosakerehalli, Sub District: Bengaluru South
District: Bengaluru, State: Karnataka
PIN Code: 560085
Mobile: 9986013436
Your Aadhaar No. 6175 9496 0962
"""

PAN_TEXT = """INCOME TAX DEPARTMENT
Permanent Account Number Card
Name: PRIYA RAO
Father's Name: RAO
Date of Birth: 01/01/1990
PAN: ABCDE1234F
"""


@pytest.fixture(autouse=True)
def stub_ner(monkeypatch):
    # Prevent the BERT fallback from downloading a model during unit tests.
    monkeypatch.setattr(entity_service, "_nlp", lambda text: [])


@pytest.mark.asyncio
async def test_aadhaar_fields_extracted():
    entities = await entity_service.extract_entities(AADHAAR_TEXT)

    assert entities["name"].lower() == "abhijna ds"
    assert entities["id_number"] == "6175 9496 0962"
    assert entities["id_type"] == "aadhaar"
    assert "560085" in (entities["address"] or "")


@pytest.mark.asyncio
async def test_mobile_number_is_not_taken_as_id():
    text = "Mobile: 998G013436\nYour Aadhaar No. 6175 9496 0962"
    entities = await entity_service.extract_entities(text)
    assert entities["id_number"] == "6175 9496 0962"


@pytest.mark.asyncio
async def test_pan_and_dob_extracted():
    entities = await entity_service.extract_entities(PAN_TEXT)
    assert entities["id_number"] == "ABCDE1234F"
    assert entities["id_type"] == "pan"
    assert entities["date_of_birth"] == "1990-01-01"
    assert entities["name"].title() == "Priya Rao"


def test_names_match_fuzzy():
    assert names_match("Abhijna DS", "Abhijna D S")
    assert names_match("Abhijna DS", "Abhijna")
    assert not names_match("Abhijna DS", "Priya Rao")


def test_addresses_match_by_pin():
    a = "10 Main Road, Bengaluru, Karnataka 560085"
    b = "Some other layout, Bengaluru 560085"
    assert addresses_match(a, b)
    assert not addresses_match(a, "Mysore, Karnataka 570001")
