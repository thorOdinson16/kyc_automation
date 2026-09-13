import json
import logging

from app.core import logging_config


def test_configure_logging_emits_json(monkeypatch, capsys):
    monkeypatch.setattr(logging_config.settings, "LOG_JSON", True)

    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    root.handlers = []
    if hasattr(root, "_kyc_json_configured"):
        delattr(root, "_kyc_json_configured")

    try:
        logging_config.configure_logging()
        logging.getLogger("test.kyc").info(
            "ping", extra={"application_id": "abc", "duration_ms": 1.5}
        )

        payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert payload["message"] == "ping"
        assert payload["application_id"] == "abc"
        assert payload["duration_ms"] == 1.5
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)
        if hasattr(root, "_kyc_json_configured"):
            delattr(root, "_kyc_json_configured")
