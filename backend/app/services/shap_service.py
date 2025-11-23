import shap
import xgboost as xgb
import numpy as np
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

class SHAPService:
    def __init__(self, model_path: str):
        self.feature_names = FEATURE_NAMES
        self.model = xgb.Booster()
        self.model.load_model(model_path)

    async def generate_explanation(self, feature_dict: Dict) -> Dict:

        # --- FIX 1: Always convert to float safely ---
        clean_vector = []
        for f in self.feature_names:
            val = feature_dict.get(f, 0.0)
            try:
                clean_vector.append(float(val))
            except:
                clean_vector.append(0.0)

        df = pd.DataFrame([clean_vector], columns=self.feature_names)
        dmatrix = xgb.DMatrix(df, feature_names=self.feature_names)

        explainer = shap.TreeExplainer(self.model)

        # --- FIX 2: shap_values always becomes 2D (n_features) ---
        shap_values = explainer.shap_values(df)
        if isinstance(shap_values, list):
            shap_values = shap_values[0]

        shap_values = np.array(shap_values).flatten()

        # --- FIX 3: base value may be array or scalar ---
        raw_base = explainer.expected_value
        if isinstance(raw_base, (list, np.ndarray)):
            base_value = float(raw_base[0])
        else:
            base_value = float(raw_base)

        impacts = []
        for name, value, impact in zip(self.feature_names, clean_vector, shap_values):
            impacts.append({
                "feature": name,
                "value": float(value),
                "impact": float(impact),
                "impact_direction": "positive" if impact > 0 else "negative",
            })

        impacts.sort(key=lambda x: abs(x["impact"]), reverse=True)

        pos = [i for i in impacts if i["impact"] > 0][:3]
        neg = [i for i in impacts if i["impact"] < 0][:3]

        return {
            "base_value": base_value,
            "feature_impacts": impacts,
            "top_positive_factors": pos,
            "top_negative_factors": neg,
            "explanation_text": self._text(pos, neg),
        }

    def _text(self, pos, neg):
        text = "Risk Assessment Explanation:\n\n"

        if pos:
            text += "Positive Impact Factors:\n"
            for p in pos:
                text += f"- {p['feature']}: {p['value']}\n"

        if neg:
            text += "\nNegative Impact Factors:\n"
            for n in neg:
                text += f"- {n['feature']}: {n['value']}\n"

        return text


shap_service = SHAPService(settings.XGBOOST_MODEL_PATH)