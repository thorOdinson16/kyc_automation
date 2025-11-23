import os
from pydantic_settings import BaseSettings
from typing import List

print("PYTEST =", os.environ.get("PYTEST"))

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    DATABASE_URL_SYNC: str
    
    # Security
    SECRET_KEY: str
    ENCRYPTION_KEY: str
    ALGORITHM: str = "HS256"
    
    # File Storage
    UPLOAD_DIR: str
    ENCRYPTED_STORAGE_DIR: str
    MAX_UPLOAD_SIZE: int = 10485760
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]
    
    # AI Models
    FACENET_MODEL_PATH: str
    BERT_MODEL_NAME: str
    XGBOOST_MODEL_PATH: str
    
    class Config:
        env_file = "backend/.env.test" if os.environ.get("PYTEST") else ".env"

settings = Settings()