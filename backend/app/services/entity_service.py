import re
from datetime import datetime
from typing import Dict, Optional

from transformers import pipeline

from app.config import settings


class EntityService:
    """BERT (dslim/bert-base-NER) entity extraction and standardisation."""

    def __init__(self):
        self._nlp = None

    @property
    def nlp(self):
        # Loaded lazily to avoid a model download at import time.
        if self._nlp is None:
            self._nlp = pipeline(
                "ner",
                model=settings.BERT_MODEL_NAME,
                aggregation_strategy="simple",
            )
        return self._nlp

    async def extract_entities(self, text: str) -> Dict:
        text = text or ""
        entities = self.nlp(text) if text.strip() else []

        extracted = {
            "name": self._extract_name(entities, text),
            "date_of_birth": self._extract_dob(text),
            "address": self._extract_address(entities, text),
            "id_number": self._extract_id_number(text),
        }

        return self._validate_entities(extracted)

    def _extract_name(self, entities: list, text: str) -> Optional[str]:
        names = [
            entity["word"]
            for entity in entities
            if str(entity.get("entity_group", "")).startswith("PER")
            or str(entity.get("entity", "")).startswith(("B-PER", "I-PER"))
        ]
        joined = " ".join(names).strip()
        return joined if joined else self._fallback_name_extraction(text)

    def _extract_address(self, entities: list, text: str) -> Optional[str]:
        locations = [
            entity["word"]
            for entity in entities
            if str(entity.get("entity_group", "")).startswith("LOC")
            or str(entity.get("entity", "")).startswith(("B-LOC", "I-LOC"))
        ]
        joined = " ".join(locations).strip()
        return joined if joined else None

    def _extract_dob(self, text: str) -> Optional[str]:
        patterns = [
            r"\d{2}/\d{2}/\d{4}",
            r"\d{2}-\d{2}-\d{4}",
            r"\d{4}-\d{2}-\d{2}",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return self._standardize_date(match.group())
        return None

    def _extract_id_number(self, text: str) -> Optional[str]:
        match = re.search(r"\b[A-Z0-9]{8,15}\b", text)
        return match.group() if match else None

    def _standardize_date(self, date_str: str) -> str:
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return date_str

    def _validate_entities(self, entities: Dict) -> Dict:
        validated = entities.copy()

        if validated.get("name"):
            validated["name"] = validated["name"].title()

        if validated.get("date_of_birth"):
            try:
                dob = datetime.strptime(validated["date_of_birth"], "%Y-%m-%d")
                if dob > datetime.now():
                    validated["date_of_birth"] = None
            except ValueError:
                validated["date_of_birth"] = None

        return validated

    def _fallback_name_extraction(self, text: str) -> Optional[str]:
        pattern = r"(?:Name|Full Name)[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)"
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).title() if match else None


entity_service = EntityService()
