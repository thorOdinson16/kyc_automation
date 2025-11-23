from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.application import KYCApplication, ApplicationStatus
from app.models.user import User
from app.schemas.application import ApplicationCreate, ApplicationResponse
from uuid import UUID
from typing import List

router = APIRouter()

@router.post("/", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    application_data: ApplicationCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new KYC application"""
    
    # Create or get user
    user = User(
        name=application_data.name,
        email=application_data.email,
        phone=application_data.phone
    )
    db.add(user)
    await db.flush()
    
    # Create application
    application = KYCApplication(
        user_id=user.user_id,
        status=ApplicationStatus.PENDING
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    
    # Log action
    from app.services.audit_service import audit_service
    await audit_service.log_action(
        db,
        application.application_id,
        "APPLICATION_CREATED",
        {"user_id": str(user.user_id)}
    )
    
    return application

@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get application by ID"""
    
    from sqlalchemy import select
    
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
    
    return application

@router.get("/{application_id}/status")
async def get_application_status(
    application_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Poll application processing status"""
    
    application = await get_application(application_id, db)
    
    return {
        "application_id": application.application_id,
        "status": application.status,
        "submitted_at": application.submitted_at,
        "decision_at": application.decision_at
    }