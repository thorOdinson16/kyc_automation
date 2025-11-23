from pydantic import BaseModel
from uuid import UUID
from typing import Any, Optional, Dict

class StatusResponse(BaseModel):
    application_id: UUID
    status: str
    submitted_at: Optional[str]
    decision_at: Optional[str]

class VerificationResultsResponse(BaseModel):
    application_id: UUID
    status: str
    decision: str
    risk_score: Optional[float]
    risk_features: Optional[Dict[str, Any]]
    explainability: Optional[Any]
    decision_at: Optional[str]