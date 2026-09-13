"""Thin KYC pipeline orchestrator.

Stage implementations live in :mod:`app.core.pipeline_stages`. The orchestrator
only decides *which* stages to run: completed stages (recorded in the
append-only audit log) are skipped and rehydrated, so a retry after a partial
failure resumes from the first incomplete stage instead of restarting.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from app.core.pipeline_context import PipelineContext
from app.core.pipeline_lock import advisory_lock
from app.core.pipeline_stages import (
    REHYDRATE,
    STAGE_COMPLETION_ACTIONS,
    load_documents_stage,
    run_decision_stage,
    run_entity_stage,
    run_explainability_stage,
    run_face_stage,
    run_liveness_stage,
    run_ocr_stage,
    run_risk_stage,
)
from app.database import AsyncSessionLocal
from app.models.application import ApplicationStatus, KYCApplication
from app.models.audit_log import AuditLog
from app.services import audit_service, encryption_service

# Ordered execution plan: stage name -> callable.
STAGE_ORDER = [
    ("ocr", run_ocr_stage),
    ("face", run_face_stage),
    ("liveness", run_liveness_stage),
    ("entities", run_entity_stage),
    ("risk", run_risk_stage),
    ("explainability", run_explainability_stage),
    ("decision", run_decision_stage),
]

_COMPLETION_ACTIONS = set(STAGE_COMPLETION_ACTIONS.values())
_STAGE_BY_ACTION = {action: name for name, action in STAGE_COMPLETION_ACTIONS.items()}


async def _load_audit_state(db, application_id: UUID):
    """Return (completed_actions, latest_details_by_action) from the audit log."""
    logs = (
        await db.execute(
            select(AuditLog)
            .where(AuditLog.application_id == application_id)
            .order_by(AuditLog.timestamp)
        )
    ).scalars().all()

    completed = set()
    details = {}
    for log in logs:
        if log.action_type in _COMPLETION_ACTIONS:
            completed.add(log.action_type)
            details[log.action_type] = log.action_details or {}
    return completed, details


async def get_stage_timings(db, application_id: UUID) -> dict:
    """Per-stage durations (ms) recorded in the audit trail, when available."""
    _, details = await _load_audit_state(db, application_id)
    timings = {}
    for action, action_details in details.items():
        if "duration_ms" in action_details:
            timings[_STAGE_BY_ACTION[action]] = action_details["duration_ms"]
    return timings


async def has_completed_pipeline(db, application_id: UUID) -> bool:
    """True when a decision has already been recorded for the application."""
    log = (
        await db.execute(
            select(AuditLog)
            .where(
                AuditLog.application_id == application_id,
                AuditLog.action_type == "DECISION_MADE",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return log is not None


async def _mark_failed(db, application_id: UUID, error: str) -> None:
    """Record a failed pipeline run without leaving the app stuck in PROCESSING."""
    await db.rollback()
    application = await db.get(KYCApplication, application_id)
    if application:
        application.status = ApplicationStatus.REVIEW_REQUIRED
        application.decision_at = datetime.utcnow()
        await db.commit()

    await audit_service.log_action(
        db, application_id, "PIPELINE_ERROR", {"error": error}
    )
    await db.commit()


async def process_kyc_pipeline(application_id: UUID) -> dict:
    """Run (or resume) the KYC pipeline.

    Returns a small status dict, e.g. ``{"status": "completed", ...}``,
    ``{"status": "already_completed"}`` or ``{"status": "already_running"}`` so
    callers can detect no-op retries and concurrent triggers.
    """
    async with advisory_lock(application_id) as acquired:
        if not acquired:
            return {"status": "already_running"}

        async with AsyncSessionLocal() as db:
            ctx = None
            try:
                application = await db.get(KYCApplication, application_id)
                if not application:
                    return {"status": "missing"}

                completed_actions, details = await _load_audit_state(db, application_id)

                # A finished run is a no-op; the existing result stands.
                if "DECISION_MADE" in completed_actions:
                    return {"status": "already_completed"}

                application.status = ApplicationStatus.PROCESSING
                await db.commit()

                ctx = PipelineContext(
                    application_id=application_id, db=db, application=application
                )
                await load_documents_stage(ctx)

                resumed_from = None
                for stage_name, stage_fn in STAGE_ORDER:
                    action = STAGE_COMPLETION_ACTIONS[stage_name]
                    if action in completed_actions:
                        REHYDRATE[stage_name](ctx, details.get(action, {}))
                        continue
                    if resumed_from is None:
                        resumed_from = stage_name
                    result = await stage_fn(ctx)
                    if result == "stop":
                        return {"status": "stopped", "resumed_from": resumed_from}

                return {
                    "status": "completed",
                    "resumed_from": resumed_from,
                    "timings": ctx.timings,
                }

            except Exception as exc:  # noqa: BLE001 - record and surface via status
                await _mark_failed(db, application_id, str(exc))
                return {"status": "failed", "error": str(exc)}
            finally:
                # Decrypted plaintext copies are PII: always remove them.
                if ctx is not None:
                    for path in ctx.temp_files:
                        encryption_service.remove_temp_file(path)
