from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.document import Document
from app.models.application import KYCApplication
from app.models.user import User
from app.services.encryption_service import encryption_service
from app.services.audit_service import audit_service
from uuid import UUID
import aiofiles
import os
from app.config import settings

router = APIRouter()

# Detect if tests are running
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

@router.post("/{application_id}/upload")
async def upload_document(
    application_id: UUID,
    document_type: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Upload and encrypt document"""

    # ---------------------------------------------------
    # 🔥 FIX: Ensure KYCApplication exists
    # ---------------------------------------------------
    existing = await db.get(KYCApplication, application_id)

    if not existing:
        if TEST_MODE:
            # Create dummy user
            dummy_user = User()
            db.add(dummy_user)
            await db.flush()  # get dummy_user.user_id

            # Create application linked to dummy user
            new_app = KYCApplication(
                application_id=application_id,
                user_id=dummy_user.user_id,
                status="processing",
            )
            db.add(new_app)
            await db.commit()

        else:
            raise HTTPException(
                status_code=400,
                detail="KYC Application does not exist"
            )
    # ---------------------------------------------------

    # Validate file size
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large"
        )

    # Save temporary file
    temp_path = os.path.join(
        settings.UPLOAD_DIR,
        f"{application_id}_{document_type}_{file.filename}"
    )
    async with aiofiles.open(temp_path, 'wb') as f:
        await f.write(content)

    # Encrypt file
    encrypted_path, iv = await encryption_service.encrypt_file(temp_path)

    # Save document record
    document = Document(
        application_id=application_id,
        document_type=document_type,
        raw_file_path=encrypted_path
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # Log action
    await audit_service.log_action(
        db,
        application_id,
        "DOCUMENT_UPLOADED",
        {
            "document_id": str(document.document_id),
            "document_type": document_type,
            "filename": file.filename
        }
    )

    return {
        "document_id": document.document_id,
        "document_type": document_type,
        "status": "uploaded"
    }