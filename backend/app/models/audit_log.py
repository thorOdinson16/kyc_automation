from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("kyc_applications.application_id"), nullable=False)
    action_type = Column(String(100), nullable=False)
    action_details = Column(JSONB, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    actor = Column(String(100), default="system")

    application = relationship("KYCApplication", back_populates="audit_logs")

    # Allow inserts but prevent updates
    def __setattr__(self, key, value):
        # Allow SQLAlchemy initial population
        if not hasattr(self, "_sa_instance_state"):
            return super().__setattr__(key, value)

        # If attribute already exists → block modification
        if key != "_sa_instance_state" and key in self.__dict__:
            raise AttributeError(f"AuditLog is immutable. Cannot modify {key}")

        super().__setattr__(key, value)

    __mapper_args__ = {"confirm_deleted_rows": False}