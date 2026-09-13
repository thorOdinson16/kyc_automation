import os
import tempfile
from typing import List, Optional

import pymupdf

from app.config import settings

_PDF_MAGIC = b"%PDF"


class PDFService:
    """Read and rasterize PDF documents (PyMuPDF, no external binaries)."""

    @staticmethod
    def is_pdf(path: str) -> bool:
        try:
            with open(path, "rb") as handle:
                return handle.read(5).startswith(_PDF_MAGIC)
        except OSError:
            return False

    @staticmethod
    def is_pdf_bytes(data: bytes) -> bool:
        return data[:5].startswith(_PDF_MAGIC)

    def validate_and_sanitize(self, path: str) -> str:
        """Reject unsafe PDFs and strip active content before storage.

        Raises ``ValueError`` for unreadable, encrypted, empty or oversized
        PDFs. Returns the path to a sanitized copy (the input is removed).
        """
        try:
            document = pymupdf.open(path)
        except Exception as exc:  # noqa: BLE001 - surface as a client error
            raise ValueError("Unreadable or corrupt PDF") from exc

        try:
            if document.needs_pass:
                raise ValueError("Password-protected PDFs are not supported")
            if document.page_count == 0:
                raise ValueError("PDF has no pages")
            if document.page_count > settings.PDF_MAX_PAGES:
                raise ValueError(
                    f"PDF has too many pages (max {settings.PDF_MAX_PAGES})"
                )

            # Remove JavaScript, launch actions, embedded files and annotations.
            document.scrub()
            sanitized_path = path + ".clean.pdf"
            document.save(sanitized_path, garbage=4, deflate=True)
        finally:
            document.close()

        os.remove(path)
        return sanitized_path

    @staticmethod
    def page_count(path: str, max_pages: Optional[int] = None) -> int:
        try:
            document = pymupdf.open(path)
        except Exception:
            return 0
        try:
            count = document.page_count
            return min(count, max_pages) if max_pages else count
        finally:
            document.close()

    def extract_text(self, path: str, max_pages: Optional[int] = None) -> str:
        max_pages = max_pages or settings.PDF_MAX_PAGES
        try:
            document = pymupdf.open(path)
        except Exception:
            return ""

        try:
            pages = []
            for index, page in enumerate(document):
                if index >= max_pages:
                    break
                pages.append(page.get_text("text"))
            return "\n".join(pages)
        finally:
            document.close()

    def render_pages(
        self,
        path: str,
        max_pages: Optional[int] = None,
        dpi: Optional[int] = None,
    ) -> List[str]:
        max_pages = max_pages or settings.PDF_MAX_PAGES
        dpi = dpi or settings.PDF_RENDER_DPI

        try:
            document = pymupdf.open(path)
        except Exception:
            return []

        outputs: List[str] = []
        output_dir = tempfile.mkdtemp(prefix="kyc_pdf_")
        try:
            for index, page in enumerate(document):
                if index >= max_pages:
                    break
                pixmap = page.get_pixmap(dpi=dpi)
                output_path = os.path.join(output_dir, f"page{index}.png")
                pixmap.save(output_path)
                outputs.append(output_path)
        finally:
            document.close()

        return outputs


pdf_service = PDFService()
