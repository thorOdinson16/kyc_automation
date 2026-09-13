from typing import Dict

import numpy as np
import pandas as pd
import xgboost as xgb

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


class SHAPService:
    """SHAP explanations for XGBoost risk decisions.

    XGBoost's native TreeSHAP (``pred_contribs``) is used as the primary
    explainer because it is stable across xgboost/shap version combinations;
    ``shap.TreeExplainer`` is retained as a fallback.
    """

    def __init__(self, model_path: str):
        self.feature_names = FEATURE_NAMES
        self.model = xgb.Booster()
        self.model.load_model(model_path)

    def _native_shap(self, dmatrix):
        contribs = np.array(
            self.model.predict(dmatrix, pred_contribs=True)
        ).reshape(-1)
        return contribs[:-1].astype(float), float(contribs[-1])

    def _library_shap(self, df, dmatrix):
        import shap

        explainer = shap.TreeExplainer(self.model)
        values = explainer.shap_values(df)
        if isinstance(values, list):
            values = values[0]
        values = np.array(values).flatten().astype(float)

        raw_base = explainer.expected_value
        if isinstance(raw_base, (list, np.ndarray)):
            base_value = float(np.array(raw_base).reshape(-1)[0])
        else:
            base_value = float(raw_base)

        return values, base_value

    async def generate_explanation(self, feature_dict: Dict) -> Dict:
        clean_vector = []
        for feature in self.feature_names:
            try:
                clean_vector.append(float(feature_dict.get(feature, 0.0)))
            except (TypeError, ValueError):
                clean_vector.append(0.0)

        df = pd.DataFrame([clean_vector], columns=self.feature_names)
        dmatrix = xgb.DMatrix(df, feature_names=self.feature_names)

        try:
            shap_values, base_value = self._native_shap(dmatrix)
        except Exception:
            shap_values, base_value = self._library_shap(df, dmatrix)

        impacts = []
        for name, value, impact in zip(self.feature_names, clean_vector, shap_values):
            impacts.append(
                {
                    "feature": name,
                    "value": float(value),
                    "impact": float(impact),
                    "impact_direction": "positive" if impact > 0 else "negative",
                }
            )

        impacts.sort(key=lambda item: abs(item["impact"]), reverse=True)

        positive = [item for item in impacts if item["impact"] > 0][:3]
        negative = [item for item in impacts if item["impact"] < 0][:3]

        return {
            "base_value": base_value,
            "feature_impacts": impacts,
            "top_positive_factors": positive,
            "top_negative_factors": negative,
            "explanation_text": self._text(positive, negative),
        }

    def _text(self, positive, negative) -> str:
        text = "Risk Assessment Explanation:\n\n"

        if positive:
            text += "Positive Impact Factors:\n"
            for item in positive:
                text += f"- {item['feature']}: {item['value']}\n"

        if negative:
            text += "\nNegative Impact Factors:\n"
            for item in negative:
                text += f"- {item['feature']}: {item['value']}\n"

        return text


shap_service = SHAPService(settings.XGBOOST_MODEL_PATH)
