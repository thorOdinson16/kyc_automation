import asyncio
import os
import re
import shutil
from typing import Dict, List, Optional

import cv2
import easyocr
import numpy as np
import pytesseract

from app.config import settings
from app.services.pdf_service import pdf_service

_ALNUM_RE = re.compile(r"[A-Za-z0-9]")
_ASCII_RE = re.compile(r"^[\x00-\x7F]+$")

_TESSDATA_CANDIDATES = [
    os.path.expanduser(r"~\scoop\apps\tesseract\current\tessdata"),
    r"C:\Program Files\Tesseract-OCR\tessdata",
    r"C:\Program Files (x86)\Tesseract-OCR\tessdata",
]
_TESSERACT_CANDIDATES = [
    os.path.expanduser(r"~\scoop\shims\tesseract.exe"),
    os.path.expanduser(r"~\scoop\apps\tesseract\current\tesseract.exe"),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


class OCRService:
    """Dual OCR: EasyOCR (multi-pass preprocessing) + Tesseract fallback."""

    def __init__(self):
        self._reader = None
        self._tesseract_ready: Optional[bool] = None
        self.confidence_threshold = 0.5

    @property
    def reader(self):
        if self._reader is None:
            use_gpu = False
            if settings.OCR_USE_GPU:
                try:
                    import torch

                    use_gpu = bool(torch.cuda.is_available())
                except Exception:
                    use_gpu = False
            self._reader = easyocr.Reader(["en"], gpu=use_gpu, verbose=False)
        return self._reader

    # ------------------------------------------------------------------ setup
    def _configure_tesseract(self) -> bool:
        cmd = settings.TESSERACT_CMD
        if not cmd or not os.path.exists(cmd):
            cmd = shutil.which("tesseract")
        if not cmd:
            cmd = next((p for p in _TESSERACT_CANDIDATES if os.path.exists(p)), None)
        if not cmd:
            return False

        pytesseract.pytesseract.tesseract_cmd = cmd

        if not os.environ.get("TESSDATA_PREFIX"):
            for data_dir in _TESSDATA_CANDIDATES:
                if os.path.exists(os.path.join(data_dir, "eng.traineddata")):
                    os.environ["TESSDATA_PREFIX"] = data_dir
                    break
        return True

    @property
    def tesseract_available(self) -> bool:
        if self._tesseract_ready is None:
            try:
                self._tesseract_ready = self._configure_tesseract()
            except Exception:
                self._tesseract_ready = False
        return self._tesseract_ready

    # ----------------------------------------------------------- preprocessing
    @staticmethod
    def _load_image(image_path: str):
        image = cv2.imread(image_path)
        if image is None:
            return None

        height, width = image.shape[:2]
        longest = max(height, width)
        target_max = max(800, settings.OCR_MAX_DIMENSION)

        if longest < 1000:
            scale = 1000.0 / longest
            image = cv2.resize(
                image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
            )
        elif longest > target_max:
            scale = target_max / longest
            image = cv2.resize(
                image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
            )
        return image

    def _primary_variant(self, image_path: str):
        return self._load_image(image_path)

    def _extra_variants(self, image_path: str) -> List[tuple]:
        image = self._load_image(image_path)
        if image is None:
            return []

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        threshold = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )

        return [
            ("clahe", cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR)),
            ("threshold", cv2.cvtColor(threshold, cv2.COLOR_GRAY2BGR)),
        ]

    @staticmethod
    def _blocks_to_lines(blocks: List[dict]) -> List[str]:
        """Group EasyOCR blocks into reading-order lines using bbox geometry."""
        items = []
        for block in blocks:
            ys = [point[1] for point in block["bbox"]]
            xs = [point[0] for point in block["bbox"]]
            items.append(
                {
                    "text": block["text"],
                    "x": min(xs),
                    "y": (min(ys) + max(ys)) / 2,
                    "h": max(ys) - min(ys),
                }
            )

        items.sort(key=lambda item: item["y"])
        lines: List[dict] = []
        for item in items:
            for line in lines:
                tolerance = max(line["h"], item["h"], 10) * 0.6
                if abs(line["y"] - item["y"]) <= tolerance:
                    line["items"].append(item)
                    line["y"] = (line["y"] + item["y"]) / 2
                    line["h"] = max(line["h"], item["h"])
                    break
            else:
                lines.append({"y": item["y"], "h": item["h"], "items": [item]})

        lines.sort(key=lambda line: line["y"])
        result = []
        for line in lines:
            line["items"].sort(key=lambda item: item["x"])
            result.append(" ".join(item["text"] for item in line["items"]))
        return result

    @staticmethod
    def _latin_only(lines: List[str]) -> List[str]:
        kept = []
        for line in lines:
            alnum = len(_ALNUM_RE.findall(line))
            ascii_chars = len(re.findall(r"[\x00-\x7F]", line))
            total = max(len(line), 1)
            # Keep lines that are mostly ASCII/printable even if Hindi glyphs are mixed in.
            if alnum >= 2 and ascii_chars / total >= 0.5:
                kept.append(line)
        return kept

    # -------------------------------------------------------------- EasyOCR
    async def _run_variant(self, variant) -> Optional[Dict]:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, self.reader.readtext, variant)
        if not results:
            return None

        blocks = []
        confidences = []
        for bbox, text, conf in results:
            conf = float(conf)
            if not text.strip():
                continue
            blocks.append(
                {
                    "bbox": [[float(p[0]), float(p[1])] for p in bbox],
                    "text": text,
                    "confidence": conf,
                }
            )
            confidences.append(conf)

        if not blocks:
            return None

        return {
            "lines": self._blocks_to_lines(blocks),
            "raw_results": blocks,
            "confidence": float(np.mean(confidences)),
        }

    async def _easyocr_extract(self, image_path: str) -> Dict:
        empty = {
            "text": "",
            "latin_text": "",
            "lines": [],
            "raw_results": [],
            "confidence": 0.0,
        }

        primary = self._primary_variant(image_path)
        if primary is None:
            return empty

        best = await self._run_variant(primary)
        if best is not None:
            best["variant"] = "primary"

        # Only pay for extra preprocessing passes when the first one is weak.
        if best is None or best["confidence"] < self.confidence_threshold:
            for variant_name, variant in self._extra_variants(image_path):
                result = await self._run_variant(variant)
                if result and (best is None or result["confidence"] > best["confidence"]):
                    result["variant"] = variant_name
                    best = result
                if best is not None and best["confidence"] >= self.confidence_threshold:
                    break

        return best or empty

    # ------------------------------------------------------------ Tesseract
    def _tesseract_extract_sync(self, image_path: str) -> Optional[Dict]:
        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            return None

        try:
            text = pytesseract.image_to_string(image)
            data = pytesseract.image_to_data(
                image, output_type=pytesseract.Output.DICT
            )
        except Exception:
            return None

        confidences = []
        for value in data.get("conf", []):
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if value >= 0:
                confidences.append(value)

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None

        return {
            "lines": lines,
            "raw_results": [{"text": line} for line in lines],
            "confidence": (float(np.mean(confidences)) / 100.0) if confidences else 0.0,
        }

    # --------------------------------------------------------------- public
    async def extract_text(self, image_path: str, use_fallback: bool = True) -> Dict:
        if pdf_service.is_pdf(image_path):
            return await self._extract_pdf(image_path, use_fallback)

        easy = await self._easyocr_extract(image_path)
        engine = "easyocr"

        if (
            use_fallback
            and easy["confidence"] < self.confidence_threshold
            and self.tesseract_available
        ):
            loop = asyncio.get_event_loop()
            tess = await loop.run_in_executor(
                None, self._tesseract_extract_sync, image_path
            )
            easy_chars = len(_ALNUM_RE.findall(easy.get("text", "")))
            tess_chars = len(_ALNUM_RE.findall(" ".join(tess["lines"]))) if tess else 0

            if tess and (tess_chars > easy_chars * 0.8 or tess["confidence"] > easy["confidence"]):
                easy = tess
                engine = "tesseract"

        lines = easy.get("lines", [])
        return {
            "text": "\n".join(lines),
            "latin_text": "\n".join(self._latin_only(lines)),
            "lines": lines,
            "raw_results": easy.get("raw_results", []),
            "confidence": float(easy.get("confidence", 0.0)),
            "ocr_engine": engine,
        }

    async def _extract_pdf(self, pdf_path: str, use_fallback: bool = True) -> Dict:
        """Use the embedded text layer when present, else rasterize + OCR."""
        embedded = pdf_service.extract_text(pdf_path)
        if len(_ALNUM_RE.findall(embedded)) >= 40:
            lines = [line.strip() for line in embedded.splitlines() if line.strip()]
            return {
                "text": "\n".join(lines),
                "latin_text": "\n".join(self._latin_only(lines)),
                "lines": lines,
                "raw_results": [],
                "confidence": 1.0,
                "ocr_engine": "pdf",
            }

        page_paths = pdf_service.render_pages(pdf_path)
        all_lines: List[str] = []
        confidences: List[float] = []
        engine = "easyocr"

        try:
            for page_path in page_paths:
                page_result = await self.extract_text(
                    page_path, use_fallback=use_fallback
                )
                all_lines.extend(page_result.get("lines", []))
                confidences.append(page_result.get("confidence", 0.0))
                if page_result.get("ocr_engine") != "easyocr":
                    engine = page_result["ocr_engine"]
        finally:
            if page_paths:
                shutil.rmtree(os.path.dirname(page_paths[0]), ignore_errors=True)

        lines = [line for line in all_lines if line.strip()]
        confidence = float(np.mean(confidences)) if confidences else 0.0

        return {
            "text": "\n".join(lines),
            "latin_text": "\n".join(self._latin_only(lines)),
            "lines": lines,
            "raw_results": [],
            "confidence": confidence,
            "ocr_engine": engine,
        }


ocr_service = OCRService()
