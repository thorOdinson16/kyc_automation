from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.audit_service import audit_service
from uuid import UUID
from typing import List

router = APIRouter()

@router.get("/{application_id}/trail")
async def get_audit_trail(
    application_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get complete audit trail for an application"""
    
    audit_logs = await audit_service.get_application_audit_trail(
        db,
        application_id
    )
    
    return {
        "application_id": application_id,
        "audit_trail": [
            {
                "log_id": log.log_id,
                "action_type": log.action_type,
                "action_details": log.action_details,
                "timestamp": log.timestamp,
                "actor": log.actor
            }
            for log in audit_logs
        ]
    }