import asyncio
from typing import Dict

import easyocr
import numpy as np
import pytesseract
from PIL import Image


class OCRService:
    """Dual OCR: EasyOCR primary, Tesseract fallback for low confidence."""

    def __init__(self):
        self._reader = None
        self.confidence_threshold = 0.5

    @property
    def reader(self):
        # Loaded lazily so app startup does not download/initialise models.
        if self._reader is None:
            self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        return self._reader

    async def extract_text(self, image_path: str, use_fallback: bool = True) -> Dict:
        result = await self._easyocr_extract(image_path)

        if result["confidence"] < self.confidence_threshold and use_fallback:
            fallback = await self._tesseract_extract(image_path)
            if fallback is not None:
                fallback["ocr_engine"] = "tesseract"
                return fallback

        result["ocr_engine"] = "easyocr"
        return result

    async def _easyocr_extract(self, image_path: str) -> Dict:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, self.reader.readtext, image_path)

        text_blocks = []
        confidences = []
        clean_results = []

        for bbox, text, conf in results:
            text_blocks.append(text)
            confidences.append(float(conf))
            clean_results.append(
                {
                    "bbox": [[float(point[0]), float(point[1])] for point in bbox],
                    "text": text,
                    "confidence": float(conf),
                }
            )

        avg_confidence = float(np.mean(confidences)) if confidences else 0.0

        return {
            "text": " ".join(text_blocks),
            "raw_results": clean_results,
            "confidence": avg_confidence,
        }

    async def _tesseract_extract(self, image_path: str):
        """Tesseract fallback. Returns None when Tesseract is unavailable."""
        loop = asyncio.get_event_loop()

        def _run():
            try:
                image = Image.open(image_path)
                return pytesseract.image_to_string(image)
            except Exception:
                return None

        text = await loop.run_in_executor(None, _run)
        if text is None:
            return None

        return {
            "text": text.strip(),
            "raw_results": {"text": text.strip()},
            "confidence": 0.7,
        }


ocr_service = OCRService()
