"""Structured JSON logging for operational visibility.

PII must never be logged: log identifiers (application/document ids), stage
names, durations and status codes — not OCR text, entity values or tokens.
"""
import logging
import sys

from pythonjsonlogger import json as jsonlogger

from app.config import settings


def configure_logging() -> None:
    """Install a single JSON stdout handler on the root logger."""
    if not settings.LOG_JSON:
        return

    root = logging.getLogger()
    if getattr(root, "_kyc_json_configured", False):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger",
            },
        )
    )

    root.handlers = [handler]
    root.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    root._kyc_json_configured = True
