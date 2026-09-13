"""Independently runnable pipeline stages.

Each stage is idempotent: a stage whose completion has already been recorded in
the append-only audit log is skipped, and its outputs are rehydrated from the
log (or the documents table) so subsequent stages can run. Durations are written
into each completion entry's ``action_details`` under ``duration_ms``.
"""
import asyncio
import time
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import select

from app.core.pipeline_context import PipelineContext
from app.models.application import ApplicationStatus
from app.models.document import Document
from app.models.embedding import Embedding
from app.models.explainability import Explainability
from app.models.risk_score import RiskScore
from app.services import (
    audit_service,
    document_verification_service,
    encryption_service,
    entity_service,
    face_service,
    liveness_service,
    ocr_service,
    risk_service,
    shap_service,
)
from app.services.entity_service import addresses_match, names_match

REQUIRED_DOCUMENTS = {"id_front", "address_proof", "utility_bill", "selfie"}

# Ordered stage name -> audit action that marks it complete.
STAGE_COMPLETION_ACTIONS = {
    "ocr": "OCR_EXTRACTED",
    "face": "FACE_MATCHED",
    "liveness": "LIVENESS_CHECKED",
    "entities": "ENTITIES_EXTRACTED",
    "risk": "RISK_CALCULATED",
    "explainability": "EXPLANATION_GENERATED",
    "decision": "DECISION_MADE",
}

_CONTINUE = "continue"
_STOP = "stop"


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def _suffix_for(document: Document) -> str:
    mime = (document.mime_type or "").lower()
    if mime == "application/pdf":
        return ".pdf"
    if mime == "image/png":
        return ".png"
    if mime == "image/webp":
        return ".webp"
    return ".jpg"


def _text_of(ocr_result: Dict[str, Any]) -> str:
    return ocr_result.get("latin_text") or ocr_result["text"]


async def load_documents_stage(ctx: PipelineContext) -> None:
    """Load documents, validate the required set and decrypt the files."""
    db = ctx.db
    documents = (
        await db.execute(
            select(Document).where(Document.application_id == ctx.application_id)
        )
    ).scalars().all()

    ctx.documents = list(documents)
    by_type: Dict[str, list] = {}
    for document in documents:
        by_type.setdefault(document.document_type, []).append(document)
    ctx.by_type = by_type

    missing = REQUIRED_DOCUMENTS - set(by_type.keys())
    if missing:
        raise ValueError(f"Missing required documents: {sorted(missing)}")

    ctx.id_doc = by_type["id_front"][0]
    ctx.address_doc = by_type["address_proof"][0]
    ctx.utility_doc = by_type["utility_bill"][0]
    ctx.selfie_doc = by_type["selfie"][0]
    ctx.liveness_docs = by_type.get("liveness", [])

    ctx.id_path = await encryption_service.decrypt_file(
        ctx.id_doc.raw_file_path, suffix=_suffix_for(ctx.id_doc)
    )
    ctx.address_path = await encryption_service.decrypt_file(
        ctx.address_doc.raw_file_path, suffix=_suffix_for(ctx.address_doc)
    )
    ctx.utility_path = await encryption_service.decrypt_file(
        ctx.utility_doc.raw_file_path, suffix=_suffix_for(ctx.utility_doc)
    )
    ctx.selfie_path = await encryption_service.decrypt_file(
        ctx.selfie_doc.raw_file_path, suffix=_suffix_for(ctx.selfie_doc)
    )
    ctx.frame_paths = [
        await encryption_service.decrypt_file(
            document.raw_file_path, suffix=_suffix_for(document)
        )
        for document in ctx.liveness_docs
    ]


async def run_ocr_stage(ctx: PipelineContext) -> str:
    start = time.perf_counter()
    db = ctx.db

    ocr_id, ocr_address, ocr_utility = await asyncio.gather(
        ocr_service.extract_text(ctx.id_path),
        ocr_service.extract_text(ctx.address_path),
        ocr_service.extract_text(ctx.utility_path),
    )
    ctx.ocr_id, ctx.ocr_address, ctx.ocr_utility = ocr_id, ocr_address, ocr_utility

    for document, ocr_result in (
        (ctx.id_doc, ocr_id),
        (ctx.address_doc, ocr_address),
        (ctx.utility_doc, ocr_utility),
    ):
        document.extracted_text = {
            "text": ocr_result["text"],
            "ocr_engine": ocr_result["ocr_engine"],
        }
        document.ocr_confidence = ocr_result["confidence"]
    await db.commit()

    duration = _elapsed_ms(start)
    ctx.timings["ocr"] = duration
    await audit_service.log_action(
        db,
        ctx.application_id,
        "OCR_EXTRACTED",
        {
            "id_card": {"confidence": ocr_id["confidence"], "engine": ocr_id["ocr_engine"]},
            "address_proof": {"confidence": ocr_address["confidence"], "engine": ocr_address["ocr_engine"]},
            "utility_bill": {"confidence": ocr_utility["confidence"], "engine": ocr_utility["ocr_engine"]},
            "duration_ms": duration,
        },
    )
    await db.commit()
    return _CONTINUE


async def run_face_stage(ctx: PipelineContext) -> str:
    start = time.perf_counter()
    db = ctx.db

    face = await face_service.verify_faces(ctx.selfie_path, ctx.id_path)
    ctx.face = face

    db.add(
        Embedding(
            embedding_id=uuid4(),
            application_id=ctx.application_id,
            vector=[float(x) for x in face["selfie_embedding"]],
            embedding_type="face",
        )
    )
    db.add(
        Embedding(
            embedding_id=uuid4(),
            application_id=ctx.application_id,
            vector=[float(x) for x in face["id_embedding"]],
            embedding_type="id_photo",
        )
    )
    await db.commit()

    duration = _elapsed_ms(start)
    ctx.timings["face"] = duration
    await audit_service.log_action(
        db,
        ctx.application_id,
        "FACE_MATCHED",
        {
            "is_match": face["is_match"],
            "similarity": face["similarity"],
            "duration_ms": duration,
        },
    )
    await db.commit()
    return _CONTINUE


async def run_liveness_stage(ctx: PipelineContext) -> str:
    start = time.perf_counter()
    db = ctx.db
    application = ctx.application

    if not ctx.frame_paths:
        application.status = ApplicationStatus.REVIEW_REQUIRED
        application.decision_at = datetime.utcnow()
        await db.commit()
        await audit_service.log_action(
            db,
            ctx.application_id,
            "LIVENESS_NOT_CAPTURED",
            {"reason": "No liveness frames were uploaded", "duration_ms": _elapsed_ms(start)},
        )
        await db.commit()
        return _STOP

    liveness = await liveness_service.detect_liveness(ctx.frame_paths)
    ctx.liveness = liveness
    duration = _elapsed_ms(start)
    ctx.timings["liveness"] = duration

    if not liveness["is_live"]:
        application.status = ApplicationStatus.REVIEW_REQUIRED
        application.decision_at = datetime.utcnow()
        await db.commit()
        await audit_service.log_action(
            db,
            ctx.application_id,
            "LIVENESS_FAILED",
            {**liveness, "duration_ms": duration},
        )
        await db.commit()
        return _STOP

    await audit_service.log_action(
        db,
        ctx.application_id,
        "LIVENESS_CHECKED",
        {**liveness, "duration_ms": duration},
    )
    return _CONTINUE


async def run_entity_stage(ctx: PipelineContext) -> str:
    start = time.perf_counter()
    db = ctx.db
    application = ctx.application

    doc_infos = [
        {"document_type": ctx.id_doc.document_type, "document": ctx.id_doc, "ocr": ctx.ocr_id},
        {"document_type": ctx.address_doc.document_type, "document": ctx.address_doc, "ocr": ctx.ocr_address},
        {"document_type": ctx.utility_doc.document_type, "document": ctx.utility_doc, "ocr": ctx.ocr_utility},
    ]
    for info in doc_infos:
        info["text"] = _text_of(info["ocr"])
        info["entities"] = await entity_service.extract_entities(info["text"])
    ctx.doc_infos = doc_infos

    roles = document_verification_service.resolve_roles(doc_infos)
    ctx.roles = roles

    id_info = roles["id_front"]
    if id_info is None:
        # Keep processing so the reviewer sees a precise mismatch.
        id_info = next(info for info in doc_infos if info["document_type"] == "id_front")
    ctx.id_info = id_info
    ctx.bill_info = roles["utility_bill"]
    ctx.address_info = roles["address_proof"]

    entities_id = id_info["entities"]
    id_name = entities_id.get("name")
    ctx.entities_id = entities_id
    ctx.id_name = id_name

    for reassignment in roles["reassignments"]:
        await audit_service.log_action(
            db, ctx.application_id, "DOCUMENT_AUTO_ROUTED", reassignment
        )

    id_check = document_verification_service.check_id(id_info["text"], entities_id)
    bill_info = ctx.bill_info
    address_info = ctx.address_info
    bill_check = (
        document_verification_service.check_bill(
            bill_info["text"], bill_info["entities"], id_name
        )
        if bill_info
        else {
            "slot": "utility_bill",
            "detected": "missing",
            "is_bill": False,
            "is_valid": False,
            "name_match": False,
        }
    )
    address_check = (
        document_verification_service.check_address(
            address_info["text"], address_info["entities"], id_name
        )
        if address_info
        else {"slot": "address_proof", "detected": "missing", "is_valid": False}
    )

    document_checks = {
        "id_front": id_check,
        "utility_bill": bill_check,
        "address_proof": address_check,
    }
    ctx.document_checks = document_checks

    mismatches = []
    warnings = []
    if not id_check["is_valid"]:
        mismatches.append(
            f"ID document is not a recognized ID type ({id_check['detected']})"
        )
    if not bill_check["is_valid"]:
        if not bill_check.get("is_bill"):
            mismatches.append("Utility bill does not look like a bill")
        elif not bill_check.get("name_match"):
            mismatches.append("Utility bill does not contain the applicant's name")
    if not address_check["is_valid"]:
        mismatches.append(
            f"Address proof could not be verified ({address_check['detected']})"
        )

    address_name = address_info["entities"].get("name") if address_info else None
    id_address = entities_id.get("address") or (
        address_info["entities"].get("address") if address_info else None
    )
    utility_address = bill_info["entities"].get("address") if bill_info else None
    bill_address_plausible = document_verification_service.is_plausible_address(
        utility_address
    )

    name_match = names_match(id_name, address_name)
    address_match = addresses_match(id_address, utility_address)

    if id_name and address_name and not name_match:
        mismatches.append("Name mismatch between ID and address proof")
    if id_address and bill_address_plausible and not address_match:
        mismatches.append("Address mismatch between ID and utility bill")
    if not id_name:
        warnings.append("Name could not be read from the ID document")
    if not id_address:
        warnings.append("Address could not be read from the ID document")

    ctx.mismatches = mismatches
    ctx.warnings = warnings
    entity_validation = {
        "name_match": bool(name_match),
        "address_match": bool(address_match),
        "mismatches": mismatches,
        "warnings": warnings,
        "document_checks": document_checks,
    }
    ctx.entity_validation = entity_validation

    application.extracted_name = id_name
    application.extracted_dob = entities_id.get("date_of_birth") or (
        address_info["entities"].get("date_of_birth") if address_info else None
    )
    application.extracted_address = id_address
    application.extracted_id_number = entities_id.get("id_number")
    application.entity_mismatches = entity_validation

    for info in doc_infos:
        info["document"].extracted_text = {
            **(info["document"].extracted_text or {}),
            "entities": info["entities"],
        }
    for role, check in document_checks.items():
        target = roles.get(role)
        if target:
            target["document"].extracted_text = {
                **(target["document"].extracted_text or {}),
                "document_check": check,
            }
    await db.commit()

    duration = _elapsed_ms(start)
    ctx.timings["entities"] = duration
    await audit_service.log_action(
        db,
        ctx.application_id,
        "ENTITIES_EXTRACTED",
        {
            "id": entities_id,
            "address_proof": address_info["entities"] if address_info else None,
            "utility_bill": bill_info["entities"] if bill_info else None,
            "validation": entity_validation,
            "duration_ms": duration,
        },
    )
    await db.commit()
    return _CONTINUE


async def run_risk_stage(ctx: PipelineContext) -> str:
    start = time.perf_counter()
    db = ctx.db
    application = ctx.application

    duration = 0.0
    if application.submitted_at:
        duration = max(
            0.0, (datetime.utcnow() - application.submitted_at).total_seconds()
        )

    features = {
        "document_quality_score": ctx.ocr_id["confidence"],
        "ocr_confidence": (
            ctx.ocr_id["confidence"]
            + ctx.ocr_address["confidence"]
            + ctx.ocr_utility["confidence"]
        )
        / 3,
        "face_similarity_score": ctx.face["similarity"],
        "liveness_confidence": ctx.liveness["confidence"],
        "entity_mismatches": ctx.mismatches,
        "upload_duration_seconds": duration,
        "ip_country": "IN",
        "document_country": "IN",
    }

    risk_result = await risk_service.calculate_risk_score(features)
    ctx.risk_result = risk_result

    risk_row = RiskScore(
        risk_score_id=uuid4(),
        application_id=ctx.application_id,
        score_value=float(risk_result["risk_score"]),
        feature_map=risk_result["feature_map"],
    )
    db.add(risk_row)
    await db.flush()
    application.risk_score_id = risk_row.risk_score_id
    await db.commit()

    stage_duration = _elapsed_ms(start)
    ctx.timings["risk"] = stage_duration
    await audit_service.log_action(
        db,
        ctx.application_id,
        "RISK_CALCULATED",
        {**risk_result, "duration_ms": stage_duration},
    )
    return _CONTINUE


async def run_explainability_stage(ctx: PipelineContext) -> str:
    start = time.perf_counter()
    db = ctx.db

    explanation = await shap_service.generate_explanation(ctx.risk_result["feature_map"])
    ctx.explanation = explanation
    db.add(
        Explainability(
            explain_id=uuid4(),
            application_id=ctx.application_id,
            shap_summary=explanation,
        )
    )
    await db.commit()

    stage_duration = _elapsed_ms(start)
    ctx.timings["explainability"] = stage_duration
    await audit_service.log_action(
        db,
        ctx.application_id,
        "EXPLANATION_GENERATED",
        {**explanation, "duration_ms": stage_duration},
    )
    return _CONTINUE


async def run_decision_stage(ctx: PipelineContext) -> str:
    start = time.perf_counter()
    db = ctx.db
    application = ctx.application

    application.status = ApplicationStatus(ctx.risk_result["decision"])
    application.decision_at = datetime.utcnow()
    await db.commit()

    stage_duration = _elapsed_ms(start)
    ctx.timings["decision"] = stage_duration
    await audit_service.log_action(
        db,
        ctx.application_id,
        "DECISION_MADE",
        {"final_status": ctx.risk_result["decision"], "duration_ms": stage_duration},
    )
    await db.commit()
    return _CONTINUE


# --------------------------------------------------------------------------
# Rehydration: rebuild stage outputs from persisted state when a stage is
# skipped on resume (older pipeline entries predate ``duration_ms`` too).
# --------------------------------------------------------------------------

def rehydrate_ocr(ctx: PipelineContext) -> None:
    def make(document: Document) -> Dict[str, Any]:
        data = document.extracted_text or {}
        return {
            "text": data.get("text", ""),
            "confidence": document.ocr_confidence or 0.0,
            "ocr_engine": data.get("ocr_engine", "unknown"),
        }

    ctx.ocr_id = make(ctx.id_doc)
    ctx.ocr_address = make(ctx.address_doc)
    ctx.ocr_utility = make(ctx.utility_doc)


def rehydrate_face(ctx: PipelineContext, details: Dict[str, Any]) -> None:
    ctx.face = {
        "is_match": details.get("is_match"),
        "similarity": details.get("similarity"),
    }


def rehydrate_liveness(ctx: PipelineContext, details: Dict[str, Any]) -> None:
    ctx.liveness = details


def rehydrate_entities(ctx: PipelineContext, details: Dict[str, Any]) -> None:
    ctx.entities_id = details.get("id") or {}
    ctx.id_name = ctx.entities_id.get("name")
    ctx.entity_validation = details.get("validation") or {}
    ctx.mismatches = ctx.entity_validation.get("mismatches", [])


def rehydrate_risk(ctx: PipelineContext, details: Dict[str, Any]) -> None:
    ctx.risk_result = {
        "risk_score": details.get("risk_score"),
        "decision": details.get("decision"),
        "recommendation": details.get("recommendation"),
        "feature_map": details.get("feature_map"),
    }


def rehydrate_explanation(ctx: PipelineContext, details: Dict[str, Any]) -> None:
    ctx.explanation = details


REHYDRATE = {
    "ocr": lambda ctx, details: rehydrate_ocr(ctx),
    "face": rehydrate_face,
    "liveness": rehydrate_liveness,
    "entities": rehydrate_entities,
    "risk": rehydrate_risk,
    "explainability": rehydrate_explanation,
    "decision": lambda ctx, details: None,
}
