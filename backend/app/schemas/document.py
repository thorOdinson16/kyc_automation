from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any

class DocumentResponse(BaseModel):
    document_id: UUID
    document_type: str
    raw_file_path: str
    extracted_text: Optional[Dict[str, Any]]
    ocr_confidence: Optional[float]
    created_at: datetime

    class Config:
        orm_mode = True