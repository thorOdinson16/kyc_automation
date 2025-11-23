import xgboost as xgb
import pandas as pd
from typing import Dict
from app.config import settings

FEATURE_NAMES = [
    "face_match_score",
    "liveness_score",
    "document_quality_score",
    "ocr_confidence",
    "entity_mismatch_count",
    "location_anomaly_score",
    "behavior_score",
]

class RiskService:
    def __init__(self, model_path: str):
        self.feature_names = FEATURE_NAMES
        self.model = xgb.Booster()
        self.model.load_model(model_path)

        self.low_risk_threshold = 0.3
        self.high_risk_threshold = 0.7

    async def calculate_risk_score(self, features: Dict) -> Dict:

        feature_map = {
            "face_match_score": features.get("face_similarity_score", 0.5),
            "liveness_score": features.get("liveness_confidence", 0.5),
            "document_quality_score": features.get("document_quality_score", 0.5),
            "ocr_confidence": features.get("ocr_confidence", 0.5),
            "entity_mismatch_count": features.get("entity_mismatch_count", 0),
            "location_anomaly_score": features.get("location_anomaly_score", 0.0),
            "behavior_score": features.get("behavior_score", 0.0),
        }

        df = pd.DataFrame([feature_map], columns=self.feature_names)
        dm = xgb.DMatrix(df, feature_names=self.feature_names)

        risk_score = float(self.model.predict(dm)[0])

        if risk_score < self.low_risk_threshold:
            decision = "approved"
            recommendation = "AUTO_APPROVE"
        elif risk_score < self.high_risk_threshold:
            decision = "review_required"
            recommendation = "MANUAL_REVIEW"
        else:
            decision = "review_required"
            recommendation = "HIGH_RISK_REVIEW"

        return {
            "risk_score": risk_score,
            "decision": decision,
            "recommendation": recommendation,
            "feature_map": feature_map,
        }

risk_service = RiskService(settings.XGBOOST_MODEL_PATH)