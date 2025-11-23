from transformers import AutoTokenizer, AutoModelForTokenClassification
from transformers import pipeline
import torch
from typing import Dict
import re
from datetime import datetime

class EntityService:
    def __init__(self):
        model_name = "bert-base-uncased"
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForTokenClassification.from_pretrained(
            "dslim/bert-base-NER"  # Pre-trained NER model
        )
        self.nlp = pipeline("ner", model=self.model, tokenizer=self.tokenizer)
    
    async def extract_entities(self, text: str) -> Dict:
        """Extract and validate entities using BERT"""
        
        # Run NER
        entities = self.nlp(text)
        
        # Parse entities
        extracted = {
            'name': self._extract_name(entities, text),
            'date_of_birth': self._extract_dob(text),
            'address': self._extract_address(entities, text),
            'id_number': self._extract_id_number(text)
        }
        
        # Validate and standardize
        validated = self._validate_entities(extracted)
        
        return validated
    
    def _extract_name(self, entities: list, text: str) -> str:
        """Extract person name"""
        names = [e['word'] for e in entities if e['entity'].startswith('B-PER') or e['entity'].startswith('I-PER')]
        return ' '.join(names).strip() if names else self._fallback_name_extraction(text)
    
    def _extract_dob(self, text: str) -> str:
        """Extract date of birth"""
        # Common date patterns
        patterns = [
            r'\d{2}/\d{2}/\d{4}',  # DD/MM/YYYY
            r'\d{2}-\d{2}-\d{4}',  # DD-MM-YYYY
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return self._standardize_date(match.group())
        
        return None
    
    def _extract_address(self, entities: list, text: str) -> str:
        """Extract address"""
        locations = [e['word'] for e in entities if e['entity'].startswith('B-LOC') or e['entity'].startswith('I-LOC')]
        return ' '.join(locations).strip() if locations else None
    
    def _extract_id_number(self, text: str) -> str:
        """Extract ID number (flexible pattern)"""
        # Match alphanumeric sequences that look like IDs
        pattern = r'\b[A-Z0-9]{8,15}\b'
        match = re.search(pattern, text)
        return match.group() if match else None
    
    def _standardize_date(self, date_str: str) -> str:
        """Standardize date to YYYY-MM-DD format"""
        formats = ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%m/%d/%Y']
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        return date_str
    
    def _validate_entities(self, entities: Dict) -> Dict:
        """Validate extracted entities"""
        validated = entities.copy()
        
        # Name validation
        if validated['name']:
            validated['name'] = validated['name'].title()
        
        # DOB validation
        if validated['date_of_birth']:
            try:
                dob = datetime.strptime(validated['date_of_birth'], '%Y-%m-%d')
                if dob > datetime.now():
                    validated['date_of_birth'] = None
            except:
                validated['date_of_birth'] = None
        
        return validated
    
    def _fallback_name_extraction(self, text: str) -> str:
        """Fallback name extraction using patterns"""
        # Look for "Name:" or similar patterns
        pattern = r'(?:Name|Full Name)[:\s]+([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)'
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).title() if match else None

entity_service = EntityService()