import os
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.pipeline import process_kyc_pipeline
from uuid import UUID

router = APIRouter()

# Detect pytest automatically
IS_TEST = os.getenv("PYTEST", "0") == "1"


@router.post("/{application_id}/process")
async def process_verification(
    application_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger KYC verification pipeline.
    - In TEST: run synchronously (fixes event loop crashes)
    - In PROD: run as background task
    """

    if IS_TEST:
        # Run instantly for pytest
        await process_kyc_pipeline(application_id)
        return {
            "application_id": application_id,
            "status": "completed",
            "message": "Pipeline executed immediately (test mode)"
        }

    # Real runtime → background
    background_tasks.add_task(process_kyc_pipeline, application_id)

    return {
        "application_id": application_id,
        "status": "processing",
        "message": "Verification pipeline started"
    }


@router.get("/{application_id}/results")
async def get_verification_results(
    application_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Return full verification results using Audit Logs."""

    from sqlalchemy import select
    from app.models.application import KYCApplication
    from app.models.audit_log import AuditLog

    # Get application
    query = select(KYCApplication).where(
        KYCApplication.application_id == application_id
    )
    result = await db.execute(query)
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )

    # ---- Get LAST RISK_CALCULATED log ----
    risk_log = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.application_id == application_id,
            AuditLog.action_type == "RISK_CALCULATED"
        )
        .order_by(AuditLog.timestamp.desc())
        .limit(1)
    )
    risk_log = risk_log.scalar_one_or_none()

    # ---- Get LAST EXPLANATION_GENERATED log ----
    explain_log = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.application_id == application_id,
            AuditLog.action_type == "EXPLANATION_GENERATED"
        )
        .order_by(AuditLog.timestamp.desc())
        .limit(1)
    )
    explain_log = explain_log.scalar_one_or_none()

    # Extract values
    risk_score = None
    risk_features = None
    if risk_log:
        risk_score = risk_log.action_details.get("risk_score")
        risk_features = risk_log.action_details.get("feature_map")

    explainability = explain_log.action_details if explain_log else None

    return {
        "application_id": str(application_id),
        "status": application.status.value,
        "decision": application.status.value,
        "risk_score": risk_score,
        "risk_features": risk_features,
        "explainability": explainability,
        "decision_at": application.decision_at
    }