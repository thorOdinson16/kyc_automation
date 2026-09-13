"""Content-based verification that a document matches its claimed slot.

The applicant chooses a slot (ID / address proof / utility bill); these
classifiers confirm the content actually looks like that kind of document.
"""

import re
from typing import Dict, List, Optional, Tuple

from app.services import verhoeff
from app.services.entity_service import name_in_text, names_match

NAME_MATCH_THRESHOLD = 80

ALLOWED_ID_TYPES = ("aadhaar", "pan", "passport", "voter", "driving_licence")

ADDRESS_PROOF_TYPES = (
    "aadhaar",
    "passport",
    "voter",
    "driving_licence",
    "utility_bill",
    "bank_statement",
    "rent_agreement",
    "property_tax",
)

BILL_CATEGORIES = (
    "electricity",
    "water",
    "gas",
    "telecom",
    "internet",
    "subscription",
    "property_tax",
    "other",
)

_AADHAAR_NUM_RE = re.compile(r"(?<!\d)(\d{4})\s?(\d{4})\s?(\d{4})(?!\d)")
_PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_PASSPORT_RE = re.compile(r"\b[A-PR-WY]\d{7}\b")
_VOTER_RE = re.compile(r"\b[A-Z]{3}\d{7}\b")
_DL_RE = re.compile(r"\b[A-Z]{2}\d{2}\s?\d{11}\b")

_BILL_EVIDENCE_RE = re.compile(
    r"\b(?:bill|invoice|tax\s+invoice|amount\s+(?:due|payable)|"
    r"total\s+(?:amount\s+)?payable|net\s+payable|payable|due\s+date|"
    r"bill\s+(?:date|number|no)|account\s+(?:no|number)|"
    r"consumer\s+(?:no|number)|invoice\s+(?:no|number)|tariff|arrears|"
    r"statement|receipt|payment)\b",
    re.IGNORECASE,
)

_BILL_CATEGORY_PATTERNS = {
    "electricity": r"electricity|kwh|units?\s+consumed|meter\s+reading|discom|energy\s+charges|power\s+supply",
    "water": r"\bwater\b|water\s+board|kilolitre|\bkl\b",
    "gas": r"\bgas\b|lpg|\bpng\b|piped\s+natural|indane|gail|bharat\s+gas|hp\s+gas",
    "telecom": r"telecom|telephone|landline|postpaid|\bmobile\b|airtel|\bjio\b|vodafone|\bvi\b|bsnl",
    "internet": r"internet|broadband|fiber|fibre|\bisp\b|wi-?fi",
    "subscription": r"subscription|monthly\s+plan|renewal|\bott\b|streaming|netflix|hotstar|spotify|prime",
    "property_tax": r"property\s+tax|municipal|corporation|house\s+tax",
}

_BANK_RE = re.compile(r"\bbank\b|statement|ifsc|account\s+statement", re.IGNORECASE)
_RENT_RE = re.compile(r"\brent\b|lease|tenan|landlord", re.IGNORECASE)

_ADDRESS_SIGNAL_RE = re.compile(
    r"\b(?:pin\s*code|pin\b|[1-9]\d{5}|road|street|nagar|layout|colony|"
    r"extension|district|state|city|po\b|vtc\b|floor|block|sector|main)\b",
    re.IGNORECASE,
)
_ADDRESS_JUNK_RE = re.compile(
    r"not\s+reply|reply\s+to|learn\s+more|activate|click|unsubscribe|"
    r"e-?mail|help|contact|http|www\.",
    re.IGNORECASE,
)


def is_plausible_address(value: Optional[str]) -> bool:
    """True when a string looks like a real address rather than footer noise."""
    if not value or len(value) < 8:
        return False
    if _ADDRESS_JUNK_RE.search(value):
        return False
    return bool(_ADDRESS_SIGNAL_RE.search(value))


def _aadhaar_number(text: str) -> Optional[str]:
    match = _AADHAAR_NUM_RE.search(text or "")
    return "".join(match.groups()) if match else None


def detect_id(text: str, id_number: Optional[str] = None) -> Tuple[str, float, List[str]]:
    """Return ``(id_type, confidence, signals)`` for the document text."""
    text = text or ""
    upper = text.upper()
    signals: List[str] = []

    if any(
        keyword in upper
        for keyword in ("AADHAAR", "UIDAI", "UNIQUE IDENTIFICATION AUTHORITY")
    ) or "आधार" in text:
        signals.append("aadhaar_keyword")
        confidence = 0.9
        number = re.sub(r"\D", "", id_number or "") or _aadhaar_number(text)
        if number and len(number) == 12:
            signals.append("aadhaar_number")
            confidence = 0.95
            if verhoeff.is_valid(number):
                signals.append("verhoeff_ok")
                confidence = 0.99
        return "aadhaar", confidence, signals

    if "PERMANENT ACCOUNT NUMBER" in upper or "INCOME TAX" in upper:
        signals.append("pan_keyword")
        if id_number and _PAN_RE.fullmatch(id_number):
            signals.append("pan_number")
            return "pan", 0.98, signals
        return "pan", 0.9, signals

    if id_number and _PAN_RE.fullmatch(id_number):
        return "pan", 0.9, ["pan_number"]

    if "PASSPORT" in upper or "REPUBLIC OF INDIA" in upper:
        signals.append("passport_keyword")
        if "P<IND" in upper or (id_number and _PASSPORT_RE.fullmatch(id_number)):
            signals.append("passport_number")
            return "passport", 0.97, signals
        return "passport", 0.9, signals

    if "ELECTION COMMISSION" in upper or "ELECTOR" in upper or "EPIC" in upper:
        signals.append("voter_keyword")
        return "voter", 0.9, signals

    if id_number and _VOTER_RE.fullmatch(id_number):
        return "voter", 0.85, ["voter_number"]

    if (
        "DRIVING" in upper
        or "LICENCE" in upper
        or "LICENSE" in upper
        or "TRANSPORT DEPARTMENT" in upper
    ):
        signals.append("driving_licence_keyword")
        if id_number and _DL_RE.fullmatch(id_number):
            signals.append("driving_licence_number")
            return "driving_licence", 0.97, signals
        return "driving_licence", 0.9, signals

    return "unknown", 0.0, signals


def detect_bill(text: str) -> Tuple[bool, str, float, List[str]]:
    """Return ``(is_bill, category, confidence, signals)``."""
    text = text or ""
    if not _BILL_EVIDENCE_RE.search(text):
        return False, "other", 0.0, []

    signals = ["bill_evidence"]
    category = "other"
    for candidate, pattern in _BILL_CATEGORY_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            category = candidate
            signals.append(f"category:{candidate}")
            break

    return True, category, 0.9, signals


def detect_address_proof(text: str) -> Tuple[str, float, List[str]]:
    """Return ``(kind, confidence, signals)`` for an address-proof document."""
    id_type, confidence, signals = detect_id(text)
    if id_type in {"aadhaar", "passport", "voter", "driving_licence"}:
        return id_type, confidence, signals

    is_bill, _, confidence, signals = detect_bill(text)
    if is_bill:
        return "utility_bill", confidence, signals

    if _RENT_RE.search(text or ""):
        return "rent_agreement", 0.8, ["rent_keyword"]

    if re.search(r"property\s+tax|municipal", text or "", re.IGNORECASE):
        return "property_tax", 0.8, ["property_tax_keyword"]

    if _BANK_RE.search(text or ""):
        return "bank_statement", 0.75, ["bank_keyword"]

    return "unknown", 0.0, signals


def classify_document(text: str, entities: Dict) -> Dict:
    """Return what a document looks like, independent of its claimed slot."""
    id_type, _, _ = detect_id(text, entities.get("id_number"))
    is_bill, bill_category, _, _ = detect_bill(text)
    address_kind, _, _ = detect_address_proof(text)

    if id_type in ALLOWED_ID_TYPES:
        suggested = "id_front"
    elif is_bill:
        suggested = "utility_bill"
    elif address_kind in ADDRESS_PROOF_TYPES or entities.get("address"):
        suggested = "address_proof"
    else:
        suggested = None

    return {
        "is_id": id_type in ALLOWED_ID_TYPES,
        "id_type": id_type,
        "is_bill": is_bill,
        "bill_category": bill_category,
        "address_kind": address_kind,
        "has_name": bool(entities.get("name")),
        "has_address": bool(entities.get("address")),
        "suggested_role": suggested,
    }


def check_id(text: str, entities: Dict) -> Dict:
    id_type, confidence, signals = detect_id(text, entities.get("id_number"))
    has_name = bool(entities.get("name"))
    is_valid = id_type in ALLOWED_ID_TYPES and has_name
    return {
        "slot": "id_front",
        "category": "id",
        "detected": id_type,
        "is_valid": bool(is_valid),
        "confidence": confidence,
        "signals": signals,
        "has_name": has_name,
    }


def check_bill(text: str, entities: Dict, applicant_name: Optional[str] = None) -> Dict:
    is_bill, category, confidence, signals = detect_bill(text)
    bill_name = entities.get("name")

    # Primary signal: the applicant's name printed anywhere in the bill text.
    found_in_text = name_in_text(applicant_name, text) if applicant_name else False
    field_match = (
        names_match(applicant_name, bill_name, NAME_MATCH_THRESHOLD)
        if applicant_name
        else False
    )
    name_match = bool(found_in_text or field_match)
    is_valid = is_bill and (not applicant_name or name_match)
    return {
        "slot": "utility_bill",
        "category": "bill",
        "detected": category,
        "is_bill": is_bill,
        "is_valid": bool(is_valid),
        "confidence": confidence,
        "signals": signals,
        "has_name": bool(bill_name) or found_in_text,
        "name_match": name_match,
    }


def check_address(text: str, entities: Dict, applicant_name: Optional[str] = None) -> Dict:
    kind, confidence, signals = detect_address_proof(text)
    has_address = is_plausible_address(entities.get("address"))
    name_match = (
        names_match(applicant_name, entities.get("name"), NAME_MATCH_THRESHOLD)
        if applicant_name and entities.get("name")
        else False
    )
    known = kind in ADDRESS_PROOF_TYPES
    is_valid = known or (has_address and (name_match or not entities.get("name")))
    return {
        "slot": "address_proof",
        "category": "address",
        "detected": kind,
        "is_valid": bool(is_valid),
        "confidence": confidence,
        "signals": signals,
        "has_address": has_address,
        "name_match": bool(name_match),
    }


def resolve_roles(documents: List[Dict]) -> Dict:
    """Assign uploaded documents to pipeline roles by detected content.

    ``documents`` items: ``{"document_type", "text", "entities"}``. Returns a
    mapping of role -> document plus the list of automatic reassignments.
    """

    def matches(document: Dict, predicate) -> bool:
        return predicate(document["text"], document["entities"])

    def pick(predicate, preferred_type: str) -> Optional[Dict]:
        for document in documents:
            if document["document_type"] == preferred_type and matches(document, predicate):
                return document
        for document in documents:
            if matches(document, predicate):
                return document
        return None

    id_doc = pick(lambda text, entities: check_id(text, entities)["is_valid"], "id_front")
    bill_doc = pick(
        lambda text, entities: check_bill(text, entities)["is_bill"], "utility_bill"
    )
    address_doc = pick(
        lambda text, entities: check_address(text, entities)["is_valid"], "address_proof"
    )

    reassignments = []
    for role, document in (
        ("id_front", id_doc),
        ("utility_bill", bill_doc),
        ("address_proof", address_doc),
    ):
        if document and document["document_type"] != role:
            reassignments.append(
                {"claimed": document["document_type"], "assigned": role}
            )

    return {
        "id_front": id_doc,
        "utility_bill": bill_doc,
        "address_proof": address_doc,
        "reassignments": reassignments,
    }
