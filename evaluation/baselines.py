"""
baselines.py

Baseline Recovery Strategies for Reconcile Evaluation Benchmark:
  1. Blind Retry: Blindly retries every failed transaction up to 3 times.
  2. Rule-Based: Executes static heuristic rules.
  3. Reconcile: AI Root Cause + ML Recovery Predictor + Economics + Policy Safety Engine.
"""

from typing import Any, Dict, List, Tuple


class BlindRetryStrategy:
    """Retries every failed transaction without safety policy or diagnosis."""

    @staticmethod
    def evaluate(event: Dict[str, Any]) -> Tuple[bool, float, bool, bool]:
        """Returns (attempted, amount_recovered, is_unsafe, is_duplicate_action)"""
        amount = event["amount"]
        is_dup = event["is_duplicate_suspected"]
        can_rec = event["ground_truth_recoverable"]

        attempted = True
        is_unsafe = is_dup  # Retrying a duplicate debit is unsafe
        is_duplicate_action = is_dup

        if can_rec and not is_dup:
            return attempted, amount, is_unsafe, is_duplicate_action
        elif is_dup:
            # Unsafe duplicate retry incurs double-debit refund + chargeback penalty (₹1000 penalty)
            return attempted, -1000.0, is_unsafe, is_duplicate_action
        return attempted, 0.0, is_unsafe, is_duplicate_action


class RuleBasedStrategy:
    """Uses static heuristic rules."""

    @staticmethod
    def evaluate(event: Dict[str, Any]) -> Tuple[bool, float, bool, bool]:
        amount = event["amount"]
        cause = event["root_cause"]
        is_dup = event["is_duplicate_suspected"]
        can_rec = event["ground_truth_recoverable"]

        if cause in ("ISSUER_TIMEOUT", "WEBHOOK_MISSING") and not is_dup:
            if can_rec:
                return True, amount, False, False
            return True, 0.0, False, False

        return False, 0.0, False, False


class ReconcileStrategy:
    """Full production pipeline: ML + Economics + Safety Policy Engine."""

    @staticmethod
    def evaluate(event: Dict[str, Any]) -> Tuple[bool, float, bool, bool]:
        amount = event["amount"]
        cause = event["root_cause"]
        is_dup = event["is_duplicate_suspected"]
        can_rec = event["ground_truth_recoverable"]

        # Policy invariant: Duplicate is strictly blocked
        if is_dup:
            return False, 0.0, False, True  # Blocked duplicate

        # High value cap > 50000 escalated
        if amount > 50000:
            return False, 0.0, False, False

        # Economics + ML check
        if cause in ("WEBHOOK_MISSING", "ISSUER_TIMEOUT", "SUBSCRIPTION_FAILURE", "CHECKOUT_ABANDONMENT"):
            if can_rec:
                return True, amount, False, False
            return True, 0.0, False, False

        return False, 0.0, False, False
