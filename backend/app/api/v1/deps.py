"""Shared authorization dependencies.

Access to a KYC application (and therefore its documents) is granted to either
a staff member (reviewer/admin) or the applicant who owns the application via
the application-scoped token issued at creation time. Checks are always tied to
``application_id`` — for routes that only receive a ``document_id`` the document
is loaded first and its owning application is used.
"""
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import security
from app.database import get_db
from app.models.application import KYCApplication
from app.models.document import Document

STAFF_ROLES = {"reviewer", "admin"}


def _extract_token(request: Request) -> str | None:
    """Read the bearer token, falling back to a ``?token=`` query param.

    The query-param fallback exists so browser-initiated loads can authenticate;
    callers should prefer the ``Authorization`` header. Tokens in URLs may leak
    via logs, caches and ``Referer`` — see the README security section.
    """
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.query_params.get("token")


def _payload_or_401(request: Request) -> dict:
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = security.decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def _authorize(payload: dict, application_id: UUID) -> None:
    """Allow staff, or the applicant whose token is bound to this application."""
    role = payload.get("role")
    if role in STAFF_ROLES:
        return
    if role == "applicant" and payload.get("app_id") == str(application_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this application",
    )


async def require_application_access(
    application_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Guard routes that address an application directly."""
    payload = _payload_or_401(request)
    if not await db.get(KYCApplication, application_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KYC application does not exist",
        )
    _authorize(payload, application_id)
    return payload


async def require_document_access(
    document_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Guard routes that address a document; resolve its owning application."""
    payload = _payload_or_401(request)
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    _authorize(payload, document.application_id)
    return payload
