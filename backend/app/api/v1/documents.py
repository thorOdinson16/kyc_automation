import os
from typing import List
from uuid import UUID, uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_application_access, require_document_access
from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.schemas.document import DocumentReclassify
from app.services.audit_service import audit_service
from app.services.encryption_service import encryption_service
from app.services.pdf_service import pdf_service

router = APIRouter()

ALLOWED_IMAGE_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
ALLOWED_DOCUMENT_MIME = ALLOWED_IMAGE_MIME | {"application/pdf"}

VALID_DOCUMENT_TYPES = {
    "id_front",
    "id_back",
    "address_proof",
    "utility_bill",
    "selfie",
    "liveness",
}

_MIME_SUFFIX = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
}


def _detect_mime(content_type: str, content: bytes) -> str:
    """Trust the magic bytes; fall back to the declared content type."""
    if content[:5].startswith(b"%PDF"):
        return "application/pdf"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"

    declared = (content_type or "").lower().split(";")[0].strip()
    return declared or "application/octet-stream"


def _suffix_for_mime(mime: str) -> str:
    return _MIME_SUFFIX.get((mime or "").lower(), ".bin")


def _safe_filename(application_id: UUID, document_type: str, filename: str) -> str:
    base = os.path.basename(filename or "upload")
    return f"{application_id}_{document_type}_{uuid4().hex}_{base}"


async def _persist_upload(
    application_id: UUID,
    document_type: str,
    file: UploadFile,
    allowed_mime: set,
) -> Document:
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large (max 10MB)",
        )

    mime = _detect_mime(file.content_type, content)
    if mime not in allowed_mime:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {mime}. Allowed: {sorted(allowed_mime)}",
        )

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    temp_path = os.path.join(
        settings.UPLOAD_DIR,
        _safe_filename(application_id, document_type, file.filename),
    )

    async with aiofiles.open(temp_path, "wb") as handle:
        await handle.write(content)

    if mime == "application/pdf":
        try:
            temp_path = pdf_service.validate_and_sanitize(temp_path)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    encrypted_path, _ = await encryption_service.encrypt_file(temp_path)

    return Document(
        application_id=application_id,
        document_type=document_type,
        raw_file_path=encrypted_path,
        mime_type=mime,
    )


@router.post("/{application_id}/upload")
async def upload_document(
    application_id: UUID,
    document_type: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _access: dict = Depends(require_application_access),
):
    """Upload and encrypt a single document (image or PDF)."""
    document = await _persist_upload(
        application_id, document_type, file, ALLOWED_DOCUMENT_MIME
    )
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
            "mime_type": document.mime_type,
        },
    )
    await db.commit()

    return {
        "document_id": document.document_id,
        "document_type": document_type,
        "mime_type": document.mime_type,
        "status": "uploaded",
    }


@router.post("/{application_id}/upload/liveness")
async def upload_liveness_frames(
    application_id: UUID,
    frames: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    _access: dict = Depends(require_application_access),
):
    """Upload a short selfie frame sequence used for liveness detection."""
    if len(frames) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least two frames are required for liveness detection",
        )

    document_ids = []
    for frame in frames:
        document = await _persist_upload(
            application_id, "liveness", frame, ALLOWED_IMAGE_MIME
        )
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
    _access: dict = Depends(require_document_access),
):
    """Decrypt and return a document for viewing."""
    from fastapi.responses import FileResponse

    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    mime = document.mime_type or "image/jpeg"
    decrypted_path = await encryption_service.decrypt_file(
        document.raw_file_path, suffix=_suffix_for_mime(mime)
    )

    return FileResponse(
        decrypted_path,
        media_type=mime,
        filename=f"{document.document_type}{_suffix_for_mime(mime)}",
        content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.patch("/{document_id}")
async def reclassify_document(
    document_id: UUID,
    payload: DocumentReclassify,
    db: AsyncSession = Depends(get_db),
    _access: dict = Depends(require_document_access),
):
    """Move a document to a different slot (e.g. after a pre-check)."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    new_type = payload.document_type.strip().lower()
    if new_type not in VALID_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid document_type: {payload.document_type}",
        )

    previous = document.document_type
    document.document_type = new_type

    await audit_service.log_action(
        db,
        document.application_id,
        "DOCUMENT_RECLASSIFIED",
        {
            "document_id": str(document_id),
            "from": previous,
            "to": new_type,
        },
    )
    await db.commit()

    return {"document_id": str(document_id), "document_type": new_type}


@router.get("/application/{application_id}/list")
async def list_documents(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    _access: dict = Depends(require_application_access),
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
                "mime_type": document.mime_type,
                "created_at": document.created_at,
                "view_url": f"{settings.API_V1_PREFIX}/documents/{document.document_id}/view",
            }
            for document in documents
        ]
    }
