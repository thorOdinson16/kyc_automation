import os
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pipeline import (
    get_stage_timings,
    has_completed_pipeline,
    process_kyc_pipeline,
)
from app.core.pipeline_lock import is_pipeline_locked
from app.database import get_db
from app.models.application import KYCApplication
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.explainability import Explainability
from app.models.risk_score import RiskScore
from app.services import document_verification_service
from app.services.encryption_service import encryption_service
from app.services.entity_service import entity_service
from app.services.ocr_service import ocr_service

router = APIRouter()

# Maps audit actions to a human-readable pipeline stage and its step index.
_PROGRESS_STAGES = {
    "APPLICATION_CREATED": ("Application created", 0),
    "DOCUMENT_UPLOADED": ("Uploading documents", 0),
    "LIVENESS_FRAMES_UPLOADED": ("Uploading documents", 0),
    "OCR_EXTRACTED": ("Extracting text (OCR)", 1),
    "FACE_MATCHED": ("Matching face", 2),
    "LIVENESS_CHECKED": ("Checking liveness", 3),
    "LIVENESS_FAILED": ("Checking liveness", 3),
    "LIVENESS_NOT_CAPTURED": ("Checking liveness", 3),
    "ENTITIES_EXTRACTED": ("Validating entities", 4),
    "RISK_CALCULATED": ("Scoring risk", 5),
    "EXPLANATION_GENERATED": ("Generating explanation", 6),
    "DECISION_MADE": ("Decision made", 6),
    "PIPELINE_ERROR": ("Failed", 0),
}

# When running under pytest the pipeline runs synchronously so the test can
# assert on the results without polling.
RUN_SYNC = os.getenv("PYTEST", "0") == "1"


def _doc_suffix(document: Document) -> str:
    mime = (document.mime_type or "").lower()
    return {
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(mime, ".jpg")


@router.post("/{application_id}/precheck")
async def precheck_documents(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """OCR + classify each document and suggest correct slot routing."""
    application = await db.get(KYCApplication, application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    documents = (
        await db.execute(
            select(Document)
            .where(
                Document.application_id == application_id,
                Document.document_type != "liveness",
            )
            .order_by(Document.created_at)
        )
    ).scalars().all()

    infos = []
    results = []
    for document in documents:
        text = ""
        entities = {}
        detection = {"suggested_role": None}
        path = None
        try:
            path = await encryption_service.decrypt_file(
                document.raw_file_path, suffix=_doc_suffix(document)
            )
            ocr_result = await ocr_service.extract_text(path)
            text = ocr_result.get("latin_text") or ocr_result.get("text", "")
            entities = await entity_service.extract_entities(text)
            detection = document_verification_service.classify_document(text, entities)
        except Exception as exc:  # noqa: BLE001 - report per document
            detection = {"suggested_role": None, "error": str(exc)}
        finally:
            encryption_service.remove_temp_file(path)

        infos.append(
            {
                "document_type": document.document_type,
                "text": text,
                "entities": entities,
                "document": document,
            }
        )
        results.append(
            {
                "document_id": str(document.document_id),
                "document_type": document.document_type,
                "mime_type": document.mime_type,
                "detection": detection,
                "suggested_role": detection.get("suggested_role"),
                "is_match": detection.get("suggested_role") == document.document_type,
                "text_preview": text[:200],
            }
        )

    roles = document_verification_service.resolve_roles(infos)
    required = {"id_front", "utility_bill", "address_proof"}
    matched = {role for role in required if roles.get(role)}

    return {
        "application_id": str(application_id),
        "documents": results,
        "reassignments": roles["reassignments"],
        "missing_roles": sorted(required - matched),
    }


@router.post("/{application_id}/process")
async def process_verification(
    application_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger the KYC verification pipeline.

    Idempotent: a completed application is returned as-is and a run already in
    flight is rejected with 409 rather than starting a duplicate.
    """
    if not await db.get(KYCApplication, application_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    if await has_completed_pipeline(db, application_id):
        return {
            "application_id": application_id,
            "status": "completed",
            "message": "Verification already completed",
        }

    if await is_pipeline_locked(application_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Verification is already in progress for this application",
        )

    if RUN_SYNC:
        result = await process_kyc_pipeline(application_id)
        return {
            "application_id": application_id,
            "status": result.get("status", "completed"),
            "message": "Pipeline executed synchronously (test mode)",
        }

    background_tasks.add_task(process_kyc_pipeline, application_id)
    return {
        "application_id": application_id,
        "status": "processing",
        "message": "Verification pipeline started",
    }


@router.get("/{application_id}/results")
async def get_verification_results(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return the full verification result for an application."""
    application = await db.get(KYCApplication, application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    risk_score = (
        await db.execute(
            select(RiskScore)
            .where(RiskScore.application_id == application_id)
            .order_by(RiskScore.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    explainability = (
        await db.execute(
            select(Explainability)
            .where(Explainability.application_id == application_id)
            .order_by(Explainability.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    return {
        "application_id": str(application_id),
        "status": application.status.value,
        "decision": application.status.value,
        "risk_score": risk_score.score_value if risk_score else None,
        "risk_features": risk_score.feature_map if risk_score else None,
        "explainability": explainability.shap_summary if explainability else None,
        "extracted": {
            "name": application.extracted_name,
            "date_of_birth": application.extracted_dob,
            "address": application.extracted_address,
            "id_number": application.extracted_id_number,
        },
        "entity_mismatches": application.entity_mismatches,
        "decision_at": application.decision_at,
        "stage_timings": await get_stage_timings(db, application_id),
    }


@router.get("/{application_id}/progress")
async def get_verification_progress(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Report the real pipeline stage for the Processing screen."""
    application = await db.get(KYCApplication, application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    latest = (
        await db.execute(
            select(AuditLog)
            .where(AuditLog.application_id == application_id)
            .order_by(AuditLog.timestamp.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    action = latest.action_type if latest else None
    stage, step = _PROGRESS_STAGES.get(action, ("Queued", 0))

    elapsed = 0.0
    if application.submitted_at:
        elapsed = max(
            0.0, (datetime.utcnow() - application.submitted_at).total_seconds()
        )

    stage_timings = await get_stage_timings(db, application_id)

    return {
        "application_id": str(application_id),
        "stage": stage,
        "step": step,
        "action": action,
        "status": application.status.value,
        "elapsed_seconds": round(elapsed, 1),
        "stage_timings": stage_timings,
        "total_stage_ms": round(sum(stage_timings.values()), 1),
    }
