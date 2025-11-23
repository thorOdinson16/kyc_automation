from sqlalchemy import Column, DateTime, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.database import Base

class RiskScore(Base):
    __tablename__ = "risk_scores"
    
    risk_score_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("kyc_applications.application_id"), nullable=False)
    score_value = Column(Float, nullable=False)
    feature_map = Column(JSONB, nullable=False)  # All features used for scoring
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    application = relationship("KYCApplication", back_populates="risk_score", uselist=False)