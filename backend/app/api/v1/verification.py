import os
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pipeline import process_kyc_pipeline
from app.database import get_db
from app.models.application import KYCApplication
from app.models.explainability import Explainability
from app.models.risk_score import RiskScore

router = APIRouter()

# When running under pytest the pipeline runs synchronously so the test can
# assert on the results without polling.
RUN_SYNC = os.getenv("PYTEST", "0") == "1"


@router.post("/{application_id}/process")
async def process_verification(
    application_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger the KYC verification pipeline."""
    if not await db.get(KYCApplication, application_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    if RUN_SYNC:
        await process_kyc_pipeline(application_id)
        return {
            "application_id": application_id,
            "status": "completed",
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
    }
