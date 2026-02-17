"""Machine Learning models: XGBoost classifier + LSTM trend predictor."""

import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime

from config import ML_PARAMS, MODELS_DIR
from analysis.feature_engine import prepare_xgboost_data, prepare_lstm_data


# ══════════════════════════════════════════════════════════════════════
#  XGBoost Direction Classifier
# ══════════════════════════════════════════════════════════════════════

class XGBoostPredictor:
    """XGBoost classifier: predicts UP/DOWN/FLAT direction."""

    def __init__(self):
        self.model = None
        self.feature_names = None
        self.trained_at = None

    def train(self, df: pd.DataFrame) -> dict:
        """Train XGBoost on historical data.

        Returns training metrics dict.
        """
        from xgboost import XGBClassifier
        from sklearn.model_selection import TimeSeriesSplit
        from sklearn.metrics import accuracy_score, classification_report

        X, y, feature_names = prepare_xgboost_data(df)
        if len(X) < 100:
            return {"error": "Insufficient data (need at least 100 samples)"}

        self.feature_names = feature_names

        # Time-series split (no future leakage)
        tscv = TimeSeriesSplit(n_splits=3)
        scores = []

        for train_idx, val_idx in tscv.split(X):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

            model = XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
                use_label_encoder=False,
                eval_metric="mlogloss",
            )
            model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            preds = model.predict(X_val)
            scores.append(accuracy_score(y_val, preds))

        # Final model on all data
        self.model = XGBClassifier(
            n_estimators=200, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=1.0,
            random_state=42, use_label_encoder=False, eval_metric="mlogloss",
        )
        self.model.fit(X, y, verbose=False)
        self.trained_at = datetime.now().isoformat()

        return {
            "cv_accuracy": round(float(np.mean(scores)), 4),
            "cv_scores": [round(s, 4) for s in scores],
            "n_samples": len(X),
            "n_features": len(feature_names),
            "trained_at": self.trained_at,
        }

    def predict(self, df: pd.DataFrame) -> dict:
        """Predict direction for the latest data point.

        Returns dict with 'direction', 'probabilities', 'signal_score'.
        """
        if self.model is None:
            return {"error": "Model not trained"}

        X, _, feature_names = prepare_xgboost_data(df)
        if X.empty:
            return {"error": "Could not prepare features"}

        # Align features: ensure prediction uses the same columns as training
        X_last = X.iloc[[-1]]
        if self.feature_names:
            missing = set(self.feature_names) - set(X_last.columns)
            for col in missing:
                X_last[col] = 0.0
            X_last = X_last[self.feature_names]
        probs = self.model.predict_proba(X_last)[0]
        pred_class = self.model.predict(X_last)[0]

        # Convert to signal: -1 (DOWN) to +1 (UP)
        # probs: [DOWN, FLAT, UP]
        signal_score = probs[2] - probs[0]  # UP prob - DOWN prob

        direction_map = {0: "DOWN", 1: "FLAT", 2: "UP"}

        return {
            "direction": direction_map.get(pred_class, "FLAT"),
            "probabilities": {
                "DOWN": round(float(probs[0]), 4),
                "FLAT": round(float(probs[1]), 4),
                "UP": round(float(probs[2]), 4),
            },
            "signal_score": round(float(np.clip(signal_score, -1, 1)), 4),
            "confidence": round(float(max(probs)), 4),
        }

    def save(self, symbol: str):
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        path = MODELS_DIR / f"xgb_{symbol.replace('/', '_')}.joblib"
        joblib.dump({"model": self.model, "features": self.feature_names,
                     "trained_at": self.trained_at}, path)

    def load(self, symbol: str) -> bool:
        path = MODELS_DIR / f"xgb_{symbol.replace('/', '_')}.joblib"
        if path.exists():
            data = joblib.load(path)
            self.model = data["model"]
            self.feature_names = data["features"]
            self.trained_at = data.get("trained_at")
            return True
        return False


# ══════════════════════════════════════════════════════════════════════
#  LSTM Trend Predictor
# ══════════════════════════════════════════════════════════════════════

class LSTMPredictor:
    """LSTM network for trend prediction."""

    def __init__(self):
        self.model = None
        self.feature_names = None
        self.trained_at = None
        self._device = None

    def _build_model(self, n_features: int):
        import torch
        import torch.nn as nn

        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        class LSTMNet(nn.Module):
            def __init__(self, input_size, hidden_size=64, num_layers=2):
                super().__init__()
                self.lstm = nn.LSTM(input_size, hidden_size, num_layers,
                                    batch_first=True, dropout=0.2)
                self.fc = nn.Sequential(
                    nn.Linear(hidden_size, 32),
                    nn.ReLU(),
                    nn.Dropout(0.2),
                    nn.Linear(32, 1),
                    nn.Tanh(),  # Output in [-1, 1]
                )

            def forward(self, x):
                lstm_out, _ = self.lstm(x)
                last_hidden = lstm_out[:, -1, :]
                return self.fc(last_hidden)

        self.model = LSTMNet(n_features).to(self._device)
        return self.model

    def train(self, df: pd.DataFrame, epochs: int = 50) -> dict:
        """Train LSTM on historical data."""
        import torch
        import torch.nn as nn
        from torch.utils.data import TensorDataset, DataLoader

        X, y, feature_names = prepare_lstm_data(df)
        if len(X) < 50:
            return {"error": "Insufficient data for LSTM training"}

        self.feature_names = feature_names

        # Clip targets to [-1, 1] for tanh output
        y = np.clip(y * 10, -1, 1)  # Scale returns for better learning

        # Train/val split (time-based)
        split = int(len(X) * 0.8)
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]

        self._build_model(X.shape[2])
        device = self._device

        X_train_t = torch.FloatTensor(X_train).to(device)
        y_train_t = torch.FloatTensor(y_train).unsqueeze(1).to(device)
        X_val_t = torch.FloatTensor(X_val).to(device)
        y_val_t = torch.FloatTensor(y_val).unsqueeze(1).to(device)

        dataset = TensorDataset(X_train_t, y_train_t)
        loader = DataLoader(dataset, batch_size=32, shuffle=False)

        optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
        criterion = nn.MSELoss()
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5)

        best_val_loss = float("inf")
        train_losses = []

        self.model.train()
        for epoch in range(epochs):
            epoch_loss = 0
            for batch_X, batch_y in loader:
                optimizer.zero_grad()
                output = self.model(batch_X)
                loss = criterion(output, batch_y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()
                epoch_loss += loss.item()

            # Validation
            self.model.eval()
            with torch.no_grad():
                val_pred = self.model(X_val_t)
                val_loss = criterion(val_pred, y_val_t).item()
            self.model.train()

            scheduler.step(val_loss)
            train_losses.append(epoch_loss / len(loader))
            best_val_loss = min(best_val_loss, val_loss)

        self.trained_at = datetime.now().isoformat()

        # Compute directional accuracy on validation
        self.model.eval()
        with torch.no_grad():
            val_pred = self.model(X_val_t).cpu().numpy().flatten()
        direction_correct = np.mean(np.sign(val_pred) == np.sign(y_val))

        return {
            "val_loss": round(best_val_loss, 6),
            "direction_accuracy": round(float(direction_correct), 4),
            "n_samples": len(X),
            "n_features": X.shape[2],
            "epochs": epochs,
            "trained_at": self.trained_at,
        }

    def predict(self, df: pd.DataFrame) -> dict:
        """Predict trend for the latest window."""
        import torch

        if self.model is None:
            return {"error": "Model not trained"}

        X, _, _ = prepare_lstm_data(df)
        if len(X) == 0:
            return {"error": "Could not prepare LSTM features"}

        self.model.eval()
        device = self._device or torch.device("cpu")

        # Use last window
        X_last = torch.FloatTensor(X[-1:]).to(device)
        with torch.no_grad():
            pred = self.model(X_last).cpu().numpy().flatten()[0]

        signal_score = float(np.clip(pred, -1, 1))
        confidence = min(1.0, abs(signal_score) + 0.3)

        return {
            "signal_score": round(signal_score, 4),
            "trend": "UP" if signal_score > 0.1 else "DOWN" if signal_score < -0.1 else "FLAT",
            "confidence": round(confidence, 4),
        }

    def save(self, symbol: str):
        import torch
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        path = MODELS_DIR / f"lstm_{symbol.replace('/', '_')}.pt"
        torch.save({
            "model_state": self.model.state_dict() if self.model else None,
            "features": self.feature_names,
            "trained_at": self.trained_at,
            "n_features": len(self.feature_names) if self.feature_names else 0,
        }, path)

    def load(self, symbol: str) -> bool:
        import torch
        path = MODELS_DIR / f"lstm_{symbol.replace('/', '_')}.pt"
        if path.exists():
            data = torch.load(path, map_location="cpu", weights_only=False)
            self.feature_names = data["features"]
            self.trained_at = data.get("trained_at")
            n_features = data.get("n_features", 0)
            if n_features > 0 and data.get("model_state"):
                self._build_model(n_features)
                self.model.load_state_dict(data["model_state"])
                self.model.eval()
                return True
        return False


# ══════════════════════════════════════════════════════════════════════
#  Unified ML Signal
# ══════════════════════════════════════════════════════════════════════

def _model_is_stale(trained_at: str | None) -> bool:
    """Check if model needs retraining based on retrain_interval_days."""
    if not trained_at:
        return True
    try:
        trained_dt = datetime.fromisoformat(trained_at)
        days_since = (datetime.now() - trained_dt).days
        return days_since >= ML_PARAMS["retrain_interval_days"]
    except (ValueError, TypeError):
        return True


def compute_ml_signal(df: pd.DataFrame, symbol: str,
                      train_if_needed: bool = True) -> dict:
    """Compute combined ML signal from XGBoost and LSTM.

    Returns dict with 'score' (-1 to +1), 'confidence', and model details.
    """
    xgb = XGBoostPredictor()
    lstm = LSTMPredictor()

    xgb_result = {"signal_score": 0, "confidence": 0}
    lstm_result = {"signal_score": 0, "confidence": 0}

    # Try loading existing models; retrain if stale or missing
    xgb_loaded = xgb.load(symbol)
    needs_retrain = not xgb_loaded or _model_is_stale(xgb.trained_at)
    if needs_retrain and train_if_needed:
        train_result = xgb.train(df)
        if "error" not in train_result:
            xgb.save(symbol)
    if xgb.model:
        xgb_result = xgb.predict(df)
        if "error" in xgb_result:
            xgb_result = {"signal_score": 0, "confidence": 0}

    lstm_loaded = lstm.load(symbol)
    needs_retrain = not lstm_loaded or _model_is_stale(lstm.trained_at)
    if needs_retrain and train_if_needed:
        train_result = lstm.train(df)
        if "error" not in train_result:
            lstm.save(symbol)
    if lstm.model:
        lstm_result = lstm.predict(df)
        if "error" in lstm_result:
            lstm_result = {"signal_score": 0, "confidence": 0}

    # Weighted combination
    xgb_w = ML_PARAMS["xgboost_weight"]
    lstm_w = ML_PARAMS["lstm_weight"]

    xgb_score = xgb_result.get("signal_score", 0)
    lstm_score = lstm_result.get("signal_score", 0)

    composite = xgb_w * xgb_score + lstm_w * lstm_score

    xgb_conf = xgb_result.get("confidence", 0)
    lstm_conf = lstm_result.get("confidence", 0)
    confidence = xgb_w * xgb_conf + lstm_w * lstm_conf

    return {
        "score": round(float(np.clip(composite, -1, 1)), 4),
        "confidence": round(float(min(1.0, confidence)), 4),
        "xgboost": xgb_result,
        "lstm": lstm_result,
    }
