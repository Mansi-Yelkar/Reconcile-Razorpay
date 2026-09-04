"""
risk_model.py

ML Recovery Probability Predictor for ReconcileX.
Estimates P(successful recovery) based on transaction amount, payment method,
root cause, failure code, retry count, and time gap.
Supports Logistic Regression baseline, Random Forest, and Gradient Boosting models.
"""

import random
from typing import Any, Dict, Tuple
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression

random.seed(42)
np.random.seed(42)


def _generate_synthetic_training_data(n: int = 1200):
    """
    Features:
      0: amount (scaled)
      1: method_code (0: UPI, 1: CARD, 2: NETBANKING)
      2: cause_code (0: ISSUER_TIMEOUT, 1: WEBHOOK_MISSING, 2: SUB_FAIL, 3: ABN, 4: INSUFFICIENT, 5: DUP)
      3: retry_count (0, 1, 2)
      4: time_gap_minutes
    """
    X, y = [], []
    for _ in range(n):
        amount = random.uniform(100, 50000)
        method = random.choice([0, 1, 2])
        cause = random.choice([0, 1, 2, 3, 4, 5])
        retries = random.choice([0, 1, 2])
        gap_mins = float(np.random.exponential(scale=30))

        p = 0.85
        if cause == 1:  # WEBHOOK_MISSING
            p = 0.98
        elif cause == 0:  # ISSUER_TIMEOUT
            p = 0.82 - (retries * 0.25)
        elif cause == 2:  # SUBSCRIPTION_FAILURE
            p = 0.75 - (retries * 0.20)
        elif cause == 3:  # CHECKOUT_ABANDONMENT
            p = 0.55 - (gap_mins * 0.005)
        elif cause == 4:  # INSUFFICIENT_FUNDS
            p = 0.15
        elif cause == 5:  # DUPLICATE_SUSPECTED
            p = 0.01

        p = max(0.01, min(0.99, p))
        label = 1 if random.random() < p else 0

        X.append([amount / 50000.0, method, cause, retries, min(gap_mins / 120.0, 1.0)])
        y.append(label)

    return np.array(X), np.array(y)


class RecoveryPredictor:
    """Predicts P(successful recovery) using trained sklearn models."""

    _instance = None

    def __init__(self):
        X, y = _generate_synthetic_training_data()
        
        self.logistic_model = LogisticRegression()
        self.logistic_model.fit(X, y)

        self.rf_model = RandomForestClassifier(n_estimators=50, random_state=42)
        self.rf_model.fit(X, y)

        self.gb_model = GradientBoostingClassifier(n_estimators=50, random_state=42)
        self.gb_model.fit(X, y)

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = RecoveryPredictor()
        return cls._instance

    def _encode_case(self, case: Dict[str, Any]) -> np.ndarray:
        amount = case.get("amount_at_risk", 1000.0) / 50000.0
        method_map = {"UPI": 0, "CARD": 1, "NETBANKING": 2}
        method = method_map.get(case.get("method", "UPI"), 0)

        cause_str = str(case.get("root_cause", "UNKNOWN"))
        cause_map = {
            "ISSUER_TIMEOUT": 0,
            "WEBHOOK_MISSING": 1,
            "SUBSCRIPTION_FAILURE": 2,
            "CHECKOUT_ABANDONMENT": 3,
            "INSUFFICIENT_FUNDS": 4,
            "DUPLICATE_SUSPECTED": 5,
        }
        cause = cause_map.get(cause_str, 0)
        retries = case.get("retry_count", 0)
        gap_mins = case.get("time_gap_seconds", 60.0) / 60.0

        return np.array([[amount, method, cause, retries, min(gap_mins / 120.0, 1.0)]])

    def predict(self, case: Dict[str, Any], model_type: str = "gradient_boosting") -> float:
        """Returns P(recovery) between 0.0 and 1.0."""
        x = self._encode_case(case)
        if model_type == "logistic":
            prob = float(self.logistic_model.predict_proba(x)[0][1])
        elif model_type == "random_forest":
            prob = float(self.rf_model.predict_proba(x)[0][1])
        else:
            prob = float(self.gb_model.predict_proba(x)[0][1])

        # Enforce safety override for duplicates
        if case.get("is_duplicate_suspected") or case.get("root_cause") == "DUPLICATE_SUSPECTED":
            return 0.0

        return round(prob, 3)
