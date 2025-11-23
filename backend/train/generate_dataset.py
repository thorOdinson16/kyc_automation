import numpy as np
import pandas as pd

# Number of synthetic records
N = 1500
np.random.seed(42)

def generate_synthetic_dataset():
    df = pd.DataFrame({
        "face_match_score": np.random.uniform(0.2, 1.0, N),
        "liveness_score": np.random.uniform(0.1, 1.0, N),
        "document_quality_score": np.random.uniform(0.2, 1.0, N),
        "ocr_confidence": np.random.uniform(0.3, 1.0, N),
        "entity_mismatch_count": np.random.randint(0, 4, N),
        "location_anomaly_score": np.random.uniform(0.0, 1.0, N),
        "behavior_score": np.random.uniform(0.0, 1.0, N),
    })

    # Weighted continuous RISK SCORE
    risk_score = (
        0.25 * (1 - df["face_match_score"]) +
        0.20 * (1 - df["liveness_score"]) +
        0.15 * (1 - df["document_quality_score"]) +
        0.10 * (1 - df["ocr_confidence"]) +
        0.15 * (df["entity_mismatch_count"] / 3) +
        0.10 * (df["location_anomaly_score"]) +
        0.05 * (1 - df["behavior_score"])
    )

    # Normalize 0–1
    df["risk_score"] = (risk_score - risk_score.min()) / (risk_score.max() - risk_score.min())

    df.to_csv("../models/synthetic_risk_data.csv", index=False)
    print("Synthetic dataset saved to: backend/models/synthetic_risk_data.csv")

if __name__ == "__main__":
    generate_synthetic_dataset()