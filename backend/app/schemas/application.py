from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.models.application import ApplicationStatus


class ApplicationCreate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None


class ApplicationResponse(BaseModel):
    application_id: UUID
    user_id: UUID
    status: ApplicationStatus
    submitted_at: datetime
    decision_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DecisionOverride(BaseModel):
    decision: str
    reason: str
