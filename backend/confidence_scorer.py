"""
confidence_scorer.py

Not every bank/merchant mismatch should be auto-reconciled. A mismatch that
showed up 90 seconds after payment, with no other similar-amount debit
nearby, is almost certainly a dropped webhook — safe to close automatically.
A mismatch that shows up 6 hours later, or has a same-amount sibling charge
sitting right next to it, could be a late settlement or the shadow of a
duplicate charge — that needs a human to glance at it before money moves.

This is a small logistic regression, not because the problem needs a big
model, but because "how confident are we" is genuinely a probability
question and a hand-written if/else threshold doesn't degrade gracefully.
Trained on a synthetic labeled set that encodes the domain rule below, so
the model's coefficients are auditable, not a black box copied from nowhere.

Rule the training data encodes (this is the *domain knowledge*, the model
just learns to weigh it in a graded, continuous way instead of a hard cutoff):
  - time_gap_seconds < 10 min AND no close sibling charge  -> safe to auto-close
  - time_gap_seconds large (settlement delay)               -> needs a second look
  - a close sibling charge of the same amount/rail exists    -> needs a second look,
    because it might be a duplicate charge wearing a ghost-payment costume
"""

import random

import numpy as np
from sklearn.linear_model import LogisticRegression

random.seed(7)
np.random.seed(7)


def _synthetic_training_set(n=600):
    X, y = [], []
    for _ in range(n):
        has_sibling = random.random() < 0.15
        # bimodal: most gaps are short (webhook drop), some are long (late settlement)
        if random.random() < 0.75:
            gap = np.random.exponential(scale=120)  # seconds, short
        else:
            gap = np.random.exponential(scale=9000)  # seconds, long tail

        gap = min(gap, 36000)
        safe = 1
        if has_sibling:
            safe = 0
        elif gap > 1800:  # > 30 min gap, treat as needing review even w/o sibling
            safe = 0 if random.random() < 0.8 else 1
        else:
            safe = 1 if random.random() < 0.95 else 0

        X.append([gap, 1.0 if has_sibling else 0.0])
        y.append(safe)
    return np.array(X), np.array(y)


class ConfidenceScorer:
    def __init__(self):
        X, y = _synthetic_training_set()
        self.model = LogisticRegression()
        self.model.fit(X, y)

    def score(self, time_gap_seconds: float, has_close_sibling: bool) -> float:
        """Returns P(safe to auto-reconcile without human review), 0..1."""
        x = np.array([[time_gap_seconds, 1.0 if has_close_sibling else 0.0]])
        return float(self.model.predict_proba(x)[0][1])

    def tier(self, confidence: float) -> str:
        if confidence >= 0.85:
            return "high"
        if confidence >= 0.5:
            return "medium"
        return "low"


_scorer_singleton = None


def get_scorer() -> ConfidenceScorer:
    global _scorer_singleton
    if _scorer_singleton is None:
        _scorer_singleton = ConfidenceScorer()
    return _scorer_singleton
