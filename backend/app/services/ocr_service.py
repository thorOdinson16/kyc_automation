import easyocr
import pytesseract
from PIL import Image
import numpy as np
from typing import Dict
import asyncio

class OCRService:
    def __init__(self):
        self.reader = easyocr.Reader(['en'])
        self.confidence_threshold = 0.5
    
    async def extract_text(self, image_path: str, use_fallback: bool = True) -> Dict:
        """Extract text using EasyOCR with Tesseract fallback"""
        
        # Primary: EasyOCR
        result = await self._easyocr_extract(image_path)
        
        if result["confidence"] < self.confidence_threshold and use_fallback:
            # Fallback: Tesseract
            result = await self._tesseract_extract(image_path)
            result["ocr_engine"] = "tesseract"
        else:
            result["ocr_engine"] = "easyocr"
        
        return result
    
    async def _easyocr_extract(self, image_path: str) -> Dict:
        """EasyOCR extraction (JSON-safe)"""
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, self.reader.readtext, image_path)
        
        text_blocks = []
        confidences = []

        # Convert raw results into JSON-serializable format
        clean_results = []
        for (bbox, text, conf) in results:
            text_blocks.append(text)
            confidences.append(float(conf))

            clean_results.append({
                "bbox": [[float(p[0]), float(p[1])] for p in bbox],
                "text": text,
                "confidence": float(conf)
            })

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        return {
            "text": " ".join(text_blocks),
            "raw_results": clean_results,   # SAFE FOR JSONB
            "confidence": avg_confidence
        }
    
    async def _tesseract_extract(self, image_path: str) -> Dict:
        """Tesseract OCR extraction"""
        loop = asyncio.get_event_loop()
        image = await loop.run_in_executor(None, Image.open, image_path)
        text = await loop.run_in_executor(None, pytesseract.image_to_string, image)

        return {
            "text": text.strip(),
            "raw_results": {"text": text.strip()},  # SAFE
            "confidence": 0.7
        }

ocr_service = OCRService()