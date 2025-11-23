from sqlalchemy import select, update
from datetime import datetime
from uuid import UUID, uuid4

from app.database import AsyncSessionLocal
from app.models.document import Document
from app.models.application import KYCApplication, ApplicationStatus
from app.models.risk_score import RiskScore
from app.models.explainability import Explainability
from app.models.embedding import Embedding

from app.services import (
    ocr_service,
    face_service,
    liveness_service,
    entity_service,
    risk_service,
    shap_service,
    encryption_service,
    audit_service
)


async def process_kyc_pipeline(application_id: UUID):
    """Full real KYC pipeline (no mocks)."""

    async with AsyncSessionLocal() as db:
        try:
            # --------------------------
            # 1. Mark application as PROCESSING
            # --------------------------
            await db.execute(
                update(KYCApplication)
                .where(KYCApplication.application_id == application_id)
                .values(status=ApplicationStatus.PROCESSING)
            )
            await db.commit()

            # --------------------------
            # 2. Fetch uploaded documents
            # --------------------------
            docs = (await db.execute(
                select(Document).where(Document.application_id == application_id)
            )).scalars().all()

            id_doc = next((d for d in docs if d.document_type == "id_front"), None)
            selfie_doc = next((d for d in docs if d.document_type == "selfie"), None)

            if not id_doc or not selfie_doc:
                raise ValueError("Missing required ID or selfie")

            # --------------------------
            # 3. Decrypt files
            # --------------------------
            id_card_path = await encryption_service.decrypt_file(id_doc.raw_file_path)
            selfie_path = await encryption_service.decrypt_file(selfie_doc.raw_file_path)

            # --------------------------
            # 4. OCR Extraction
            # --------------------------
            ocr_result = await ocr_service.extract_text(id_card_path)

            await audit_service.log_action(
                db, application_id, "OCR_EXTRACTED", ocr_result
            )

            # --------------------------
            # 5. Face Match
            # --------------------------
            is_match, similarity = await face_service.verify_faces(
                selfie_path, id_card_path
            )

            await audit_service.log_action(
                db,
                application_id,
                "FACE_MATCHED",
                {"is_match": is_match, "similarity": similarity}
            )

            # --------------------------
            # 6. Liveness Detection
            # --------------------------
            liveness_result = await liveness_service.detect_liveness(selfie_path)

            await audit_service.log_action(
                db,
                application_id,
                "LIVENESS_CHECKED",
                liveness_result
            )

            # --------------------------
            # 7. Entity Extraction
            # --------------------------
            entities = await entity_service.extract_entities(ocr_result["text"])

            await audit_service.log_action(
                db, application_id, "ENTITIES_EXTRACTED", entities
            )

            # --------------------------
            # 8. Risk Score
            # --------------------------
            features = {
                "document_quality_score": ocr_result["confidence"],
                "face_similarity_score": similarity,
                "liveness_confidence": liveness_result.get("confidence", 0.5)
            }

            risk_result = await risk_service.calculate_risk_score(features)

            await audit_service.log_action(
                db,
                application_id,
                "RISK_CALCULATED",
                risk_result
            )

            # --------------------------
            # 9. SHAP Explanation
            # --------------------------
            explanation = await shap_service.generate_explanation(features)

            await audit_service.log_action(
                db,
                application_id,
                "EXPLANATION_GENERATED",
                explanation
            )

            # ----------------------------------------------------
            # >>> SAVE RISK_SCORE, EXPLAINABILITY, EMBEDDING <<<
            # ----------------------------------------------------

            # 1. RISK SCORE
            risk_row = RiskScore(
                risk_score_id=uuid4(),
                application_id=application_id,
                score_value=float(risk_result["risk_score"]),
                feature_map=risk_result["feature_map"],   # ← FIXED
            )
            db.add(risk_row)
            await db.commit()

            # 2. EXPLAINABILITY
            exp_row = Explainability(
                explain_id=uuid4(),
                application_id=application_id,
                shap_summary=explanation,
            )
            db.add(exp_row)
            await db.commit()

            # 3. OPTIONAL FACE EMBEDDING
            if "face_embedding" in risk_result:
                embed_row = Embedding(
                    embedding_id=uuid4(),
                    application_id=application_id,
                    vector=risk_result["face_embedding"],
                    embedding_type="face",
                )
                db.add(embed_row)
                await db.commit()

            # --------------------------
            # 10. Final Status Update
            # --------------------------
            await db.execute(
                update(KYCApplication)
                .where(KYCApplication.application_id == application_id)
                .values(
                    status=risk_result["decision"],
                    decision_at=datetime.utcnow().replace(tzinfo=None)
                )
            )
            await db.commit()

            await audit_service.log_action(
                db,
                application_id,
                "DECISION_MADE",
                {"final_status": risk_result["decision"]}
            )

        except Exception as e:
            await audit_service.log_action(
                db, application_id, "PIPELINE_ERROR", {"error": str(e)}
            )
            raise