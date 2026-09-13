import asyncio
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

REQUIRED_DOCUMENTS = {
    "id_front",
    "address_proof",
    "utility_bill",
    "selfie",
}


def _suffix_for(document: Document) -> str:
    mime = (document.mime_type or "").lower()
    if mime == "application/pdf":
        return ".pdf"
    if mime == "image/png":
        return ".png"
    if mime == "image/webp":
        return ".webp"
    return ".jpg"


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

            id_path = await encryption_service.decrypt_file(
                id_doc.raw_file_path, suffix=_suffix_for(id_doc)
            )
            address_path = await encryption_service.decrypt_file(
                address_doc.raw_file_path, suffix=_suffix_for(address_doc)
            )
            utility_path = await encryption_service.decrypt_file(
                utility_doc.raw_file_path, suffix=_suffix_for(utility_doc)
            )
            selfie_path = await encryption_service.decrypt_file(
                selfie_doc.raw_file_path, suffix=_suffix_for(selfie_doc)
            )
            frame_paths = [
                await encryption_service.decrypt_file(
                    doc.raw_file_path, suffix=_suffix_for(doc)
                )
                for doc in liveness_docs
            ]

            # ---------------- OCR ----------------
            ocr_id, ocr_address, ocr_utility = await asyncio.gather(
                ocr_service.extract_text(id_path),
                ocr_service.extract_text(address_path),
                ocr_service.extract_text(utility_path),
            )

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
            if not frame_paths:
                application.status = ApplicationStatus.REVIEW_REQUIRED
                application.decision_at = datetime.utcnow()
                await db.commit()
                await audit_service.log_action(
                    db,
                    application_id,
                    "LIVENESS_NOT_CAPTURED",
                    {"reason": "No liveness frames were uploaded"},
                )
                await db.commit()
                return

            liveness = await liveness_service.detect_liveness(frame_paths)

            if not liveness["is_live"]:
                application.status = ApplicationStatus.REVIEW_REQUIRED
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

            # ---------------- Entities & document verification ----------------
            def _text_of(ocr_result):
                return ocr_result.get("latin_text") or ocr_result["text"]

            doc_infos = [
                {"document_type": id_doc.document_type, "document": id_doc, "ocr": ocr_id},
                {"document_type": address_doc.document_type, "document": address_doc, "ocr": ocr_address},
                {"document_type": utility_doc.document_type, "document": utility_doc, "ocr": ocr_utility},
            ]
            for info in doc_infos:
                info["text"] = _text_of(info["ocr"])
                info["entities"] = await entity_service.extract_entities(info["text"])

            roles = document_verification_service.resolve_roles(doc_infos)

            id_info = roles["id_front"]
            if id_info is None:
                # Keep processing so the reviewer sees a precise mismatch.
                id_info = next(
                    info for info in doc_infos if info["document_type"] == "id_front"
                )

            bill_info = roles["utility_bill"]
            address_info = roles["address_proof"]

            entities_id = id_info["entities"]
            id_name = entities_id.get("name")

            for reassignment in roles["reassignments"]:
                await audit_service.log_action(
                    db, application_id, "DOCUMENT_AUTO_ROUTED", reassignment
                )

            id_check = document_verification_service.check_id(id_info["text"], entities_id)
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

            entity_validation = {
                "name_match": bool(name_match),
                "address_match": bool(address_match),
                "mismatches": mismatches,
                "warnings": warnings,
                "document_checks": document_checks,
            }

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

            await audit_service.log_action(
                db,
                application_id,
                "ENTITIES_EXTRACTED",
                {
                    "id": entities_id,
                    "address_proof": address_info["entities"] if address_info else None,
                    "utility_bill": bill_info["entities"] if bill_info else None,
                    "validation": entity_validation,
                },
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
