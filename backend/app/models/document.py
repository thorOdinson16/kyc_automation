from sqlalchemy import Column, String, DateTime, ForeignKey, Float, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.database import Base

class Document(Base):
    __tablename__ = "documents"
    
    document_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("kyc_applications.application_id"), nullable=False)
    document_type = Column(String(100), nullable=False)  # ID_CARD, UTILITY_BILL, ADDRESS_PROOF, SELFIE
    raw_file_path = Column(Text, nullable=False)  # Path to encrypted file
    extracted_text = Column(JSONB, nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    application = relationship("KYCApplication", back_populates="documents")