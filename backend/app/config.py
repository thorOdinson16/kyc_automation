import os
from pathlib import Path
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / (".env.test" if os.environ.get("PYTEST") else ".env")),
        extra="ignore",
    )

    # Database
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    # Security
    SECRET_KEY: str
    ENCRYPTION_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # File Storage
    UPLOAD_DIR: str
    ENCRYPTED_STORAGE_DIR: str
    MAX_UPLOAD_SIZE: int = 10485760

    # API
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # AI Models
    FACENET_MODEL_PATH: str = "./models/facenet"
    BERT_MODEL_NAME: str = "dslim/bert-base-NER"
    XGBOOST_MODEL_PATH: str = "./models/xgboost_risk.json"

    # Liveness tuning
    LIVENESS_EAR_THRESHOLD: float = 0.21
    LIVENESS_MOTION_THRESHOLD: float = 0.0015

    # OCR
    TESSERACT_CMD: Optional[str] = None
    OCR_USE_GPU: bool = True
    OCR_MAX_DIMENSION: int = 1600
    PDF_MAX_PAGES: int = 5
    PDF_RENDER_DPI: int = 150

    # TLS 1.3 (optional; enforced when both cert and key are provided)
    SSL_CERTFILE: Optional[str] = None
    SSL_KEYFILE: Optional[str] = None

    # Observability
    LOG_JSON: bool = True

    # Login rate limiting.
    #   REDIS_URL empty -> in-process limiter (local dev / single worker)
    #   REDIS_URL set   -> Redis fixed-window, shared across workers
    # On a Redis outage the limiter fails open to the in-process window and
    # stops probing Redis for REDIS_COOLDOWN_SECONDS (circuit breaker).
    REDIS_URL: str = ""
    REDIS_CONNECT_TIMEOUT: float = 0.25
    REDIS_SOCKET_TIMEOUT: float = 0.25
    REDIS_COOLDOWN_SECONDS: int = 30
    RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT: int = 5
    LOGIN_RATE_WINDOW_SECONDS: int = 60

    DEBUG: bool = False

    @field_validator("REDIS_URL", mode="before")
    @classmethod
    def _normalize_redis_url(cls, value) -> str:
        return (value or "").strip()

    @field_validator(
        "UPLOAD_DIR",
        "ENCRYPTED_STORAGE_DIR",
        "FACENET_MODEL_PATH",
        "XGBOOST_MODEL_PATH",
        mode="after",
    )
    @classmethod
    def _resolve_relative_to_backend(cls, value: str) -> str:
        path = Path(value)
        return str(path if path.is_absolute() else (BASE_DIR / path).resolve())


settings = Settings()
