from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.application import ApplicationStatus, KYCApplication
from app.models.document import Document
from app.models.embedding import Embedding
from app.models.explainability import Explainability
from app.models.risk_score import RiskScore
from app.services import (
    audit_service,
    encryption_service,
    entity_service,
    face_service,
    liveness_service,
    ocr_service,
    risk_service,
    shap_service,
)

REQUIRED_DOCUMENTS = {
    "id_front",
    "address_proof",
    "utility_bill",
    "selfie",
}


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


async def process_kyc_pipeline(application_id: UUID):
    """Full KYC pipeline: OCR -> face -> liveness -> entities -> risk -> SHAP."""

    async with AsyncSessionLocal() as db:
        try:
            application = await db.get(KYCApplication, application_id)
            if not application:
                return

            application.status = ApplicationStatus.PROCESSING
            await db.commit()

            documents = (
                await db.execute(
                    select(Document).where(Document.application_id == application_id)
                )
            ).scalars().all()

            by_type = {}
            for document in documents:
                by_type.setdefault(document.document_type, []).append(document)

            missing = REQUIRED_DOCUMENTS - set(by_type.keys())
            if missing:
                raise ValueError(f"Missing required documents: {sorted(missing)}")

            id_doc = by_type["id_front"][0]
            address_doc = by_type["address_proof"][0]
            utility_doc = by_type["utility_bill"][0]
            selfie_doc = by_type["selfie"][0]
            liveness_docs = by_type.get("liveness", [])

            id_path = await encryption_service.decrypt_file(id_doc.raw_file_path)
            address_path = await encryption_service.decrypt_file(address_doc.raw_file_path)
            utility_path = await encryption_service.decrypt_file(utility_doc.raw_file_path)
            selfie_path = await encryption_service.decrypt_file(selfie_doc.raw_file_path)
            frame_paths = [
                await encryption_service.decrypt_file(doc.raw_file_path)
                for doc in liveness_docs
            ]

            # ---------------- OCR ----------------
            ocr_id = await ocr_service.extract_text(id_path)
            ocr_address = await ocr_service.extract_text(address_path)
            ocr_utility = await ocr_service.extract_text(utility_path)

            for document, ocr_result in (
                (id_doc, ocr_id),
                (address_doc, ocr_address),
                (utility_doc, ocr_utility),
            ):
                document.extracted_text = {
                    "text": ocr_result["text"],
                    "ocr_engine": ocr_result["ocr_engine"],
                }
                document.ocr_confidence = ocr_result["confidence"]
            await db.commit()

            await audit_service.log_action(
                db,
                application_id,
                "OCR_EXTRACTED",
                {
                    "id_card": {"confidence": ocr_id["confidence"], "engine": ocr_id["ocr_engine"]},
                    "address_proof": {"confidence": ocr_address["confidence"], "engine": ocr_address["ocr_engine"]},
                    "utility_bill": {"confidence": ocr_utility["confidence"], "engine": ocr_utility["ocr_engine"]},
                },
            )

            # ---------------- Face match ----------------
            face = await face_service.verify_faces(selfie_path, id_path)

            db.add(
                Embedding(
                    embedding_id=uuid4(),
                    application_id=application_id,
                    vector=[float(x) for x in face["selfie_embedding"]],
                    embedding_type="face",
                )
            )
            db.add(
                Embedding(
                    embedding_id=uuid4(),
                    application_id=application_id,
                    vector=[float(x) for x in face["id_embedding"]],
                    embedding_type="id_photo",
                )
            )
            await db.commit()

            await audit_service.log_action(
                db,
                application_id,
                "FACE_MATCHED",
                {"is_match": face["is_match"], "similarity": face["similarity"]},
            )

            # ---------------- Liveness ----------------
            liveness = await liveness_service.detect_liveness(frame_paths)

            if not liveness["is_live"]:
                application.status = ApplicationStatus.REJECTED
                application.decision_at = datetime.utcnow()
                await db.commit()
                await audit_service.log_action(
                    db, application_id, "LIVENESS_FAILED", liveness
                )
                await db.commit()
                return

            await audit_service.log_action(
                db, application_id, "LIVENESS_CHECKED", liveness
            )

            # ---------------- Entities ----------------
            entities = await entity_service.extract_entities(ocr_id["text"])

            id_name = (entities.get("name") or "").lower()
            address_text = (ocr_address.get("text") or "").lower()
            utility_text = (ocr_utility.get("text") or "").lower()

            name_match = bool(id_name) and id_name in address_text
            address_value = (entities.get("address") or "").lower()
            address_match = bool(address_value) and address_value in utility_text

            mismatches = []
            if not name_match:
                mismatches.append("Name mismatch between ID and address proof")
            if not address_match:
                mismatches.append("Address mismatch between ID and utility bill")

            entity_validation = {
                "name_match": name_match,
                "address_match": address_match,
                "mismatches": mismatches,
            }

            application.extracted_name = entities.get("name")
            application.extracted_dob = entities.get("date_of_birth")
            application.extracted_address = entities.get("address")
            application.extracted_id_number = entities.get("id_number")
            application.entity_mismatches = entity_validation
            await db.commit()

            await audit_service.log_action(
                db,
                application_id,
                "ENTITIES_EXTRACTED",
                {"entities": entities, "validation": entity_validation},
            )

            # ---------------- Risk score ----------------
            duration = 0.0
            if application.submitted_at:
                duration = max(
                    0.0, (datetime.utcnow() - application.submitted_at).total_seconds()
                )

            features = {
                "document_quality_score": ocr_id["confidence"],
                "ocr_confidence": (
                    ocr_id["confidence"]
                    + ocr_address["confidence"]
                    + ocr_utility["confidence"]
                )
                / 3,
                "face_similarity_score": face["similarity"],
                "liveness_confidence": liveness["confidence"],
                "entity_mismatches": mismatches,
                "upload_duration_seconds": duration,
                "ip_country": "IN",
                "document_country": "IN",
            }

            risk_result = await risk_service.calculate_risk_score(features)

            risk_row = RiskScore(
                risk_score_id=uuid4(),
                application_id=application_id,
                score_value=float(risk_result["risk_score"]),
                feature_map=risk_result["feature_map"],
            )
            db.add(risk_row)
            await db.flush()
            application.risk_score_id = risk_row.risk_score_id
            await db.commit()

            await audit_service.log_action(
                db, application_id, "RISK_CALCULATED", risk_result
            )

            # ---------------- SHAP explainability ----------------
            explanation = await shap_service.generate_explanation(
                risk_result["feature_map"]
            )
            db.add(
                Explainability(
                    explain_id=uuid4(),
                    application_id=application_id,
                    shap_summary=explanation,
                )
            )
            await db.commit()

            await audit_service.log_action(
                db, application_id, "EXPLANATION_GENERATED", explanation
            )

            # ---------------- Final decision ----------------
            application.status = ApplicationStatus(risk_result["decision"])
            application.decision_at = datetime.utcnow()
            await db.commit()

            await audit_service.log_action(
                db,
                application_id,
                "DECISION_MADE",
                {"final_status": risk_result["decision"]},
            )
            await db.commit()

        except Exception as exc:  # noqa: BLE001 - record and surface via status
            await _mark_failed(db, application_id, str(exc))
