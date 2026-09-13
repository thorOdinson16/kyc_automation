import re
from datetime import datetime
from typing import Dict, List, Optional

from rapidfuzz import fuzz

from app.config import settings

_AADHAAR_RE = re.compile(r"(?<!\d)(\d{4})\s?(\d{4})\s?(\d{4})(?!\d)")
_PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_PASSPORT_RE = re.compile(r"\b[A-PR-WY]\d{7}\b")
_VOTER_RE = re.compile(r"\b[A-Z]{3}\d{7}\b")
_MOBILE_RE = re.compile(r"(?<!\d)[6-9]\d{9}(?!\d)")
_PIN_RE = re.compile(r"(?<!\d)[1-9]\d{5}(?!\d)")
_GENERIC_ID_RE = re.compile(r"\b[A-Z0-9]{8,15}\b")

_DATE_DMY_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
_DATE_YMD_RE = re.compile(r"\b(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b")
_DOB_LABEL_RE = re.compile(
    r"(?:date\s+of\s+birth|d\.?\s?o\.?\s?b\.?|year\s+of\s+birth|y\.?\s?o\.?\s?b\.?|जन्म)",
    re.IGNORECASE,
)
_NAME_LABEL_RE = re.compile(
    r"\b(?:full\s+name|consumer\s+name|customer\s+name|subscriber\s+name|"
    r"account\s+holder|billed\s+to|payment\s+from|received\s+from|"
    r"name\s+and\s+address|name)\b\s*[:\-]?\s*"
    r"([A-Za-z][A-Za-z .'\-]{2,60})",
    re.IGNORECASE,
)
_TO_LABEL_RE = re.compile(
    r"\bto\s*[:\-]\s*([A-Za-z][A-Za-z .'\-]{2,60})", re.IGNORECASE
)
_HI_LABEL_RE = re.compile(
    r"\bhi\s*[,:]?\s+([A-Za-z][A-Za-z .'\-]{2,60})", re.IGNORECASE
)
_EMAIL_NAME_RE = re.compile(r"([A-Za-z][A-Za-z .'\-]{2,40}?)\s*<[^<>@\s]+@[^<>\s]+>")
_NAME_REJECT_RE = re.compile(
    r"activate|click|learn\s+more|sign\s+in|unsubscribe|view\s+in\s+browser|"
    r"\bhelp\b|\bcontact\b|\baccount\b|\breceipt\b|paypal|google|gmail",
    re.IGNORECASE,
)
_ADDRESS_LABEL_RE = re.compile(r"(?:address|addr|पता)\s*[:\-]?\s*", re.IGNORECASE)

# Guardian / care-of markers, tolerant of common OCR confusions (S/O -> SiG).
_ADDRESS_START_RE = re.compile(
    r"(?:\bS\s?[/|i]?\s?[G0O]\b|\bD\s?[/|]?\s?[O0]\b|\bW\s?[/|]?\s?[O0]\b|"
    r"\bC\s?[/|]?\s?[O0]\b|care\s+of)",
    re.IGNORECASE,
)
_ADDRESS_STOP_RE = re.compile(
    r"(?:mobile|mob\.?|phone|aadhaar|आधार|enrollment|your\s+aadhaar|government\s+of\s+india|"
    r"unique\s+identification|help|uidai|www\.|e-?mail|issued|signature|permanent\s+account)",
    re.IGNORECASE,
)
_ADDRESS_KEYWORDS_RE = re.compile(
    r"(?:main|road|rd\b|street|nagar|layout|colony|extension|stage|district|dist\b|state|"
    r"city|po\b|post|vtc\b|pin\s*code|pin\b|floor|block|sector|cross|plot|house|flat|"
    r"apartment|near|opp\b|bangalore|bengaluru|mumbai|delhi|karnataka|ward)",
    re.IGNORECASE,
)

_NAME_STOPWORDS = {
    "s", "o", "d", "w", "c", "son", "daughter", "wife", "of", "care", "father",
    "mother", "husband", "guardian", "government", "india", "unique",
    "identification", "authority", "enrollment", "address", "dob", "date",
    "birth", "male", "female", "gender", "aadhaar", "your", "help", "uidai",
    "name", "no", "to", "card", "income", "tax", "department", "permanent",
    "account", "number", "signature", "gmail", "email", "mail", "paypal",
}


class EntityService:
    """Document-aware, rule/structure-first entity extraction.

    BERT NER is kept only as a sparse fallback for names and addresses.
    """

    def __init__(self):
        self._nlp = None

    @property
    def nlp(self):
        if self._nlp is None:
            from transformers import pipeline

            self._nlp = pipeline(
                "ner",
                model=settings.BERT_MODEL_NAME,
                aggregation_strategy="simple",
            )
        return self._nlp

    async def extract_entities(self, text: str) -> Dict:
        text = text or ""
        entities = {
            "name": self._extract_name(text),
            "date_of_birth": self._extract_dob(text),
            "address": self._extract_address(text),
            "id_number": self._extract_id_number(text),
        }

        if not entities["name"] or not entities["address"]:
            entities = self._apply_ner_fallback(text, entities)

        entities = self._validate_entities(entities)
        entities["id_type"] = self._detect_id_type(text, entities.get("id_number"))
        return entities

    # ------------------------------------------------------------------ name
    @staticmethod
    def _name_tokens(value: str) -> Optional[str]:
        """Return the rightmost run of name-like tokens in a text fragment."""
        runs = []
        current = []
        for token in re.split(r"\s+", value.strip()):
            cleaned = token.strip(".,;:#@()[]/\\|")
            is_alpha = bool(cleaned) and re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", cleaned)
            if is_alpha and cleaned.lower() not in _NAME_STOPWORDS:
                current.append(cleaned)
            else:
                if current:
                    runs.append(current)
                    current = []
        if current:
            runs.append(current)

        best = None
        for run in runs:
            candidate = " ".join(run)
            if 2 <= len(candidate) <= 60:
                best = run

        if not best:
            return None
        name = " ".join(best[:5]).strip()
        return name if 2 <= len(name) <= 60 else None

    @staticmethod
    def _person_name_line(line: str) -> Optional[str]:
        tokens = []
        for token in re.split(r"\s+", line.strip()):
            cleaned = token.strip(".,;:#@()[]/\\|")
            if not cleaned:
                continue
            if not re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", cleaned):
                return None
            if cleaned.lower() in _NAME_STOPWORDS:
                return None
            tokens.append(cleaned)

        if not 1 <= len(tokens) <= 4:
            return None
        if max(len(token) for token in tokens) < 4:
            return None
        return " ".join(tokens)

    def _extract_name(self, text: str) -> Optional[str]:
        for pattern in (_NAME_LABEL_RE, _TO_LABEL_RE, _HI_LABEL_RE):
            match = pattern.search(text)
            if not match:
                continue
            candidate = self._name_tokens(match.group(1))
            if candidate and not re.search(
                r"address|authority|government", candidate, re.IGNORECASE
            ):
                return candidate

        email = _EMAIL_NAME_RE.search(text)
        if email and not _NAME_REJECT_RE.search(email.group(1)):
            candidate = self._name_tokens(email.group(1))
            if candidate:
                return candidate

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        address_start = len(lines)
        for index, line in enumerate(lines):
            if _ADDRESS_START_RE.search(line) or self._looks_like_address_line(line):
                address_start = index
                break

        # Closest plausible name line above the address block.
        best = None
        for line in lines[:address_start]:
            if _NAME_REJECT_RE.search(line):
                continue
            candidate = self._person_name_line(line)
            if candidate:
                best = candidate
        if best:
            return best

        for line in lines:
            if _NAME_REJECT_RE.search(line):
                continue
            candidate = self._person_name_line(line)
            if candidate:
                best = candidate
        return best

    # ------------------------------------------------------------------- dob
    def _extract_dob(self, text: str) -> Optional[str]:
        for match in _DOB_LABEL_RE.finditer(text):
            window = text[match.end() : match.end() + 40]
            date = self._find_date(window)
            if date:
                return date
            year = re.search(r"\b(19|20)\d{2}\b", window)
            if year:
                return year.group()

        return self._find_date(text)

    @staticmethod
    def _find_date(value: str) -> Optional[str]:
        match = _DATE_DMY_RE.search(value)
        if match:
            first, second, year = (
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
            day, month = (first, second) if first > 12 else (second, first) if second > 12 else (first, second)
            try:
                return datetime(year, month, day).strftime("%Y-%m-%d")
            except ValueError:
                pass

        match = _DATE_YMD_RE.search(value)
        if match:
            year, month, day = (
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
            try:
                return datetime(year, month, day).strftime("%Y-%m-%d")
            except ValueError:
                return None

        return None

    # --------------------------------------------------------------- address
    @staticmethod
    def _looks_like_address_line(line: str) -> bool:
        if _ADDRESS_STOP_RE.search(line):
            return False
        if re.search(r"\d", line):
            return True
        return bool(_ADDRESS_KEYWORDS_RE.search(line))

    def _build_address(self, lines: List[str], start: int) -> Optional[str]:
        parts = []
        for line in lines[start : start + 8]:
            if parts and _ADDRESS_STOP_RE.search(line):
                break
            parts.append(line)
        return self._clean_address(" ".join(parts))

    def _address_backwards(self, lines: List[str], end: int) -> Optional[str]:
        start = end
        while start - 1 >= 0 and (end - start + 1) < 8 and self._looks_like_address_line(lines[start - 1]):
            start -= 1
        return self._clean_address(" ".join(lines[start : end + 1]))

    def _extract_address(self, text: str) -> Optional[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        for index, line in enumerate(lines):
            match = _ADDRESS_LABEL_RE.search(line)
            if match and len(re.sub(r"\W", "", line[match.end() :])) >= 3:
                address = self._build_address(lines, index)
                if address:
                    return address

        for index, line in enumerate(lines):
            if _ADDRESS_START_RE.search(line):
                address = self._build_address(lines, index)
                if address:
                    return address

        for index, line in enumerate(lines):
            if "PIN" in line.upper() and _PIN_RE.search(line):
                address = self._address_backwards(lines, index)
                if address:
                    return address

        for index, line in enumerate(lines):
            if _PIN_RE.search(line) and re.search(r"[A-Za-z]{3}", line):
                address = self._address_backwards(lines, index)
                if address:
                    return address

        return None

    @staticmethod
    def _clean_address(value: str) -> Optional[str]:
        start = _ADDRESS_START_RE.search(value)
        if start:
            value = value[start.start() :]

        stop = _ADDRESS_STOP_RE.search(value)
        if stop:
            value = value[: stop.start()]

        value = _ADDRESS_START_RE.sub(" ", value, count=1)
        value = re.sub(
            r"^(?:address|addr)\s*[:\-]?\s*", "", value, flags=re.IGNORECASE
        )
        value = re.sub(r"[^\x00-\x7F]+", " ", value)
        value = re.sub(r"\s+", " ", value).strip(" ;,#-:")
        return value if len(value) >= 12 else None

    # ------------------------------------------------------------- id number
    def _extract_id_number(self, text: str) -> Optional[str]:
        labeled = re.search(
            r"(?:aadhaar|आधार)\s*(?:no|number|#)?\.?\s*[:\-]?\s*((?:\d[\s-]?){12})",
            text,
            re.IGNORECASE,
        )
        if labeled:
            digits = re.sub(r"\D", "", labeled.group(1))
            if len(digits) == 12:
                return f"{digits[:4]} {digits[4:8]} {digits[8:]}"

        aadhaar = _AADHAAR_RE.search(text)
        if aadhaar:
            return f"{aadhaar.group(1)} {aadhaar.group(2)} {aadhaar.group(3)}"

        pan = _PAN_RE.search(text.upper())
        if pan:
            return pan.group()

        passport = _PASSPORT_RE.search(text.upper())
        if passport:
            return passport.group()

        voter = _VOTER_RE.search(text.upper())
        if voter:
            return voter.group()

        for match in _GENERIC_ID_RE.finditer(text.upper()):
            candidate = match.group()
            context = text[max(0, match.start() - 15) : match.start()].lower()
            if any(word in context for word in ("mobile", "mob", "phone")):
                continue
            if _MOBILE_RE.fullmatch(candidate):
                continue
            if len(re.findall(r"\d", candidate)) < 6:
                continue
            return candidate

        return None

    @staticmethod
    def _detect_id_type(text: str, id_number: Optional[str]) -> str:
        upper = (text or "").upper()
        if "AADHAAR" in upper or "आधार" in text:
            return "aadhaar"
        if id_number and _PAN_RE.fullmatch(id_number):
            return "pan"
        if id_number and _PASSPORT_RE.fullmatch(id_number):
            return "passport"
        if id_number and _VOTER_RE.fullmatch(id_number):
            return "voter"
        return "unknown"

    # ------------------------------------------------------------------- bert
    def _apply_ner_fallback(self, text: str, entities: Dict) -> Dict:
        if not text.strip():
            return entities
        try:
            results = self.nlp(text)
        except Exception:
            return entities

        if not entities.get("name"):
            names = [
                item["word"]
                for item in results
                if str(item.get("entity_group", "")).startswith("PER")
            ]
            joined = " ".join(names).strip()
            if joined:
                entities["name"] = joined

        if not entities.get("address"):
            locations = [
                item["word"]
                for item in results
                if str(item.get("entity_group", "")).startswith("LOC")
            ]
            joined = " ".join(locations).strip()
            if len(joined) >= 3:
                entities["address"] = joined

        return entities

    # --------------------------------------------------------------- validate
    def _validate_entities(self, entities: Dict) -> Dict:
        validated = dict(entities)

        name = validated.get("name")
        if name:
            validated["name"] = re.sub(r"\s+", " ", name).strip().title()

        dob = validated.get("date_of_birth")
        if dob and len(dob) == 10:
            try:
                if datetime.strptime(dob, "%Y-%m-%d") > datetime.now():
                    validated["date_of_birth"] = None
            except ValueError:
                validated["date_of_birth"] = None

        return validated


# ------------------------------------------------------------- matching utils
def normalize_name(value: Optional[str]) -> str:
    if not value:
        return ""
    value = re.sub(r"[^A-Za-z ]", " ", value.upper())
    return re.sub(r"\s+", " ", value).strip()


def name_in_text(applicant_name: Optional[str], text: Optional[str], threshold: float = 0.8) -> bool:
    """True when the applicant's name appears as words inside the document text.

    Used for name-gated documents (bills/receipts) where the extractor may not
    isolate the name field but the name is clearly printed in the text.
    """
    if not applicant_name or not text:
        return False

    tokens = [token for token in normalize_name(applicant_name).split() if len(token) >= 2]
    if not tokens:
        return False

    haystack = normalize_name(text)
    matched = sum(
        1 for token in tokens if re.search(rf"\b{re.escape(token)}\b", haystack)
    )
    if matched == 0:
        return False
    if len(tokens) == 1:
        return matched == 1
    return matched / len(tokens) >= threshold


def normalize_address(value: Optional[str]) -> str:
    if not value:
        return ""
    value = re.sub(r"[^A-Z0-9 ]", " ", value.upper())
    return re.sub(r"\s+", " ", value).strip()


def names_match(first: Optional[str], second: Optional[str], threshold: int = 80) -> bool:
    left, right = normalize_name(first), normalize_name(second)
    if not left or not right:
        return False
    if left == right:
        return True
    return fuzz.token_set_ratio(left, right) >= threshold


def addresses_match(
    first: Optional[str], second: Optional[str], threshold: int = 70
) -> bool:
    if not first or not second:
        return False

    pins_a = set(_PIN_RE.findall(first))
    pins_b = set(_PIN_RE.findall(second))
    if pins_a and pins_b and pins_a & pins_b:
        return True

    left, right = normalize_address(first), normalize_address(second)
    if not left or not right:
        return False
    return fuzz.token_set_ratio(left, right) >= threshold


entity_service = EntityService()
