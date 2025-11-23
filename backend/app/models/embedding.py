from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import uuid
from datetime import datetime
from app.database import Base

class Embedding(Base):
    __tablename__ = "embeddings"
    
    embedding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("kyc_applications.application_id"), nullable=False)
    vector = Column(Vector(512))  # 512-dimensional for FaceNet
    embedding_type = Column(String(50), nullable=False)  # face, id_photo, text_embedding
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    application = relationship("KYCApplication", back_populates="embeddings")