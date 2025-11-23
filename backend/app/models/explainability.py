from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.database import Base

class Explainability(Base):
    __tablename__ = "explainability"
    
    explain_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("kyc_applications.application_id"), nullable=False)
    shap_summary = Column(JSONB, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    application = relationship("KYCApplication", back_populates="explainability", uselist=False)