from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from typing import Optional

class ApplicationCreate(BaseModel):
    name: Optional[str]
    email: Optional[EmailStr]
    phone: Optional[str]

class ApplicationResponse(BaseModel):
    application_id: UUID
    user_id: UUID
    status: str
    submitted_at: datetime
    decision_at: Optional[datetime]

    class Config:
        orm_mode = True
