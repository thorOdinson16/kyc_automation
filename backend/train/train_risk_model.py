import pandas as pd
import xgboost as xgb

def train_risk_model():
    # Load dataset
    df = pd.read_csv("../models/synthetic_risk_data.csv")

    X = df.drop("risk_score", axis=1)
    y = df["risk_score"]

    dtrain = xgb.DMatrix(X, label=y)

    params = {
        "objective": "reg:squarederror",
        "eval_metric": "rmse",
        "tree_method": "hist"
    }

    print("Training XGBoost regression model...")
    model = xgb.train(params, dtrain, num_boost_round=120)

    # Save trained model
    model.save_model("../models/xgboost_risk.json")
    print("Model saved to: backend/models/xgboost_risk.json")

if __name__ == "__main__":
    train_risk_model()