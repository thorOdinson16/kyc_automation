from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import require_role
from app.database import get_db
from app.models.application import ApplicationStatus, KYCApplication
from app.models.user import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationResponse,
    DecisionOverride,
)
from app.services.audit_service import audit_service

router = APIRouter()


@router.post("/", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    application_data: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new KYC application (open to applicants)."""
    user = User(
        name=application_data.name,
        email=str(application_data.email) if application_data.email else None,
        phone=application_data.phone,
    )
    db.add(user)
    await db.flush()

    application = KYCApplication(
        user_id=user.user_id,
        status=ApplicationStatus.PENDING,
    )
    db.add(application)
    await db.flush()

    await audit_service.log_action(
        db,
        application.application_id,
        "APPLICATION_CREATED",
        {"user_id": str(user.user_id)},
    )
    await db.commit()
    await db.refresh(application)

    return application


@router.get("/", response_model=List[ApplicationResponse])
async def list_all_applications(
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _reviewer: dict = Depends(require_role("reviewer", "admin")),
):
    """List all applications (reviewer/admin only)."""
    query = select(KYCApplication).order_by(KYCApplication.submitted_at.desc())
    if status_filter:
        try:
            query = query.where(
                KYCApplication.status == ApplicationStatus(status_filter.lower())
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status filter: {status_filter}",
            )

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get application by ID."""
    application = await db.get(KYCApplication, application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )
    return application


@router.get("/{application_id}/status")
async def get_application_status(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Poll application processing status."""
    application = await db.get(KYCApplication, application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    return {
        "application_id": application.application_id,
        "status": application.status,
        "submitted_at": application.submitted_at,
        "decision_at": application.decision_at,
    }


@router.post("/{application_id}/override")
async def override_decision(
    application_id: UUID,
    payload: DecisionOverride,
    db: AsyncSession = Depends(get_db),
    reviewer: dict = Depends(require_role("reviewer", "admin")),
):
    """Reviewer/admin override of an automated decision."""
    application = await db.get(KYCApplication, application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    decision = payload.decision.lower()
    if decision not in {ApplicationStatus.APPROVED.value, ApplicationStatus.REJECTED.value}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="decision must be 'approved' or 'rejected'",
        )

    application.status = ApplicationStatus(decision)
    application.decision_at = datetime.utcnow()

    await audit_service.log_action(
        db,
        application_id,
        "DECISION_OVERRIDDEN",
        {"new_status": decision, "reason": payload.reason},
        actor=reviewer.get("sub", "reviewer"),
    )
    await db.commit()

    return {"message": "Decision updated", "status": decision}
