import os
from typing import List
from uuid import UUID, uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.application import KYCApplication
from app.models.document import Document
from app.services.audit_service import audit_service
from app.services.encryption_service import encryption_service

router = APIRouter()


def _safe_filename(application_id: UUID, document_type: str, filename: str) -> str:
    base = os.path.basename(filename or "upload")
    return f"{application_id}_{document_type}_{uuid4().hex}_{base}"


async def _persist_upload(application_id: UUID, document_type: str, file: UploadFile) -> Document:
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large",
        )

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    temp_path = os.path.join(
        settings.UPLOAD_DIR,
        _safe_filename(application_id, document_type, file.filename),
    )

    async with aiofiles.open(temp_path, "wb") as handle:
        await handle.write(content)

    encrypted_path, _ = await encryption_service.encrypt_file(temp_path)

    return Document(
        application_id=application_id,
        document_type=document_type,
        raw_file_path=encrypted_path,
    )


async def _require_application(db: AsyncSession, application_id: UUID) -> None:
    if not await db.get(KYCApplication, application_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KYC application does not exist",
        )


@router.post("/{application_id}/upload")
async def upload_document(
    application_id: UUID,
    document_type: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload and encrypt a single document."""
    await _require_application(db, application_id)

    document = await _persist_upload(application_id, document_type, file)
    db.add(document)
    await db.commit()
    await db.refresh(document)

    await audit_service.log_action(
        db,
        application_id,
        "DOCUMENT_UPLOADED",
        {
            "document_id": str(document.document_id),
            "document_type": document_type,
            "filename": os.path.basename(file.filename or ""),
        },
    )
    await db.commit()

    return {
        "document_id": document.document_id,
        "document_type": document_type,
        "status": "uploaded",
    }


@router.post("/{application_id}/upload/liveness")
async def upload_liveness_frames(
    application_id: UUID,
    frames: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a short selfie frame sequence used for liveness detection."""
    await _require_application(db, application_id)

    if len(frames) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least two frames are required for liveness detection",
        )

    document_ids = []
    for frame in frames:
        document = await _persist_upload(application_id, "liveness", frame)
        db.add(document)
        await db.flush()
        document_ids.append(str(document.document_id))

    await db.commit()

    await audit_service.log_action(
        db,
        application_id,
        "LIVENESS_FRAMES_UPLOADED",
        {"frame_count": len(document_ids)},
    )
    await db.commit()

    return {"status": "uploaded", "frame_count": len(document_ids)}


@router.get("/{document_id}/view")
async def view_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Decrypt and return a document for viewing."""
    from fastapi.responses import FileResponse

    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    decrypted_path = await encryption_service.decrypt_file(document.raw_file_path)

    return FileResponse(
        decrypted_path,
        media_type="image/jpeg",
        filename=f"{document.document_type}.jpg",
    )


@router.get("/application/{application_id}/list")
async def list_documents(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all documents for an application."""
    documents = (
        await db.execute(
            select(Document)
            .where(Document.application_id == application_id)
            .order_by(Document.created_at)
        )
    ).scalars().all()

    return {
        "documents": [
            {
                "document_id": str(document.document_id),
                "document_type": document.document_type,
                "created_at": document.created_at,
                "view_url": f"{settings.API_V1_PREFIX}/documents/{document.document_id}/view",
            }
            for document in documents
        ]
    }
