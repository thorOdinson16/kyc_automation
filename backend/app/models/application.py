from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from enum import Enum
from app.database import Base

class ApplicationStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    APPROVED = "approved"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"

class KYCApplication(Base):
    __tablename__ = "kyc_applications"
    
    application_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    status = Column(SQLEnum(ApplicationStatus), default=ApplicationStatus.PENDING)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    decision_at = Column(DateTime, nullable=True)
    risk_score_id = Column(UUID(as_uuid=True), nullable=True)
    
    extracted_name = Column(String(255), nullable=True)
    extracted_dob = Column(String(50), nullable=True)
    extracted_address = Column(Text, nullable=True)
    extracted_id_number = Column(String(100), nullable=True)
    entity_mismatches = Column(JSONB, nullable=True)

    # Relationships
    user = relationship("User", back_populates="applications")
    documents = relationship("Document", back_populates="application")
    embeddings = relationship("Embedding", back_populates="application")
    risk_score = relationship("RiskScore", back_populates="application")
    explainability = relationship("Explainability", back_populates="application")
    audit_logs = relationship("AuditLog", back_populates="application")

class DocumentType(str, Enum):
    ID_FRONT = "id_front"
    ID_BACK = "id_back"
    ADDRESS_PROOF = "address_proof"
    UTILITY_BILL = "utility_bill"
    SELFIE = "selfie"