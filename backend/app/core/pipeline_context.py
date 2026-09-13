from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import KYCApplication
from app.models.document import Document


@dataclass
class PipelineContext:
    """Mutable state threaded through the pipeline stages.

    Stages read the fields populated by earlier stages. On a resume, completed
    stages are not re-executed; their outputs are rehydrated from the audit log
    (and the documents table) instead.
    """

    application_id: UUID
    db: AsyncSession
    application: KYCApplication

    documents: List[Document] = field(default_factory=list)
    by_type: Dict[str, List[Document]] = field(default_factory=dict)
    id_doc: Optional[Document] = None
    address_doc: Optional[Document] = None
    utility_doc: Optional[Document] = None
    selfie_doc: Optional[Document] = None
    liveness_docs: List[Document] = field(default_factory=list)

    id_path: Optional[str] = None
    address_path: Optional[str] = None
    utility_path: Optional[str] = None
    selfie_path: Optional[str] = None
    frame_paths: List[str] = field(default_factory=list)

    ocr_id: Optional[Dict[str, Any]] = None
    ocr_address: Optional[Dict[str, Any]] = None
    ocr_utility: Optional[Dict[str, Any]] = None

    face: Optional[Dict[str, Any]] = None
    liveness: Optional[Dict[str, Any]] = None

    doc_infos: List[Dict[str, Any]] = field(default_factory=list)
    roles: Optional[Dict[str, Any]] = None
    id_info: Optional[Dict[str, Any]] = None
    bill_info: Optional[Dict[str, Any]] = None
    address_info: Optional[Dict[str, Any]] = None
    entities_id: Optional[Dict[str, Any]] = None
    id_name: Optional[str] = None

    document_checks: Dict[str, Any] = field(default_factory=dict)
    mismatches: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    entity_validation: Dict[str, Any] = field(default_factory=dict)

    risk_result: Optional[Dict[str, Any]] = None
    explanation: Optional[Dict[str, Any]] = None

    timings: Dict[str, float] = field(default_factory=dict)
