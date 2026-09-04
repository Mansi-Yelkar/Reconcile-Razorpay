"""
policy_engine.py

Deterministic Policy Engine for ReconcileX.
The AI recommends, but the Policy Engine decides. Enforces 7 financial invariants:
  1. Idempotency (no duplicate execution of same key)
  2. Retry limits (max 2 retries)
  3. Recovery window (24 hours max)
  4. Monetary threshold (> ₹50,000 requires human approval)
  5. Duplicate protection (suspected duplicates blocked)
  6. Recovery completed check
  7. Verification before ledger recording
"""

from datetime import datetime
from typing import Any, Dict, Tuple
import db
from models.domain import ActionType
from recovery.idempotency import IdempotencyManager
from recovery.stopping_rules import StoppingRules


class PolicyEngine:
    """Enforces financial safety rules and decides execution status."""

    POLICY_VERSION = "2.3"
    HIGH_VALUE_THRESHOLD = 50000.0

    @classmethod
    def evaluate(cls, case: Dict[str, Any], recommended_action: ActionType, attempt_number: int) -> Tuple[str, str, str]:
        """
        Returns (decision, idempotency_key, reasoning)
        decision: APPROVED | BLOCKED | ESCALATED | STOPPED
        """
        case_id = case["id"]
        amount = case.get("amount_at_risk", 0.0)
        idempotency_key = IdempotencyManager.generate_key(case_id, recommended_action.value, attempt_number)

        # Check Invariant 1: Idempotency
        if IdempotencyManager.is_already_executed(idempotency_key):
            reason = f"Idempotency violation: key {idempotency_key} has already been executed."
            db.log_audit_event({
                "entity_type": "RECOVERY_CASE",
                "entity_id": case_id,
                "event_type": "POLICY_EVALUATED",
                "decision": "BLOCKED",
                "reason": reason,
                "policy_version": cls.POLICY_VERSION,
                "metadata": {"idempotency_key": idempotency_key},
            })
            return "BLOCKED", idempotency_key, reason

        # Check Invariant 4: High Value Threshold
        if amount > cls.HIGH_VALUE_THRESHOLD:
            reason = f"Amount ₹{amount:,.2f} exceeds high-value threshold (₹{cls.HIGH_VALUE_THRESHOLD:,.2f}) — requires manual human approval."
            db.log_audit_event({
                "entity_type": "RECOVERY_CASE",
                "entity_id": case_id,
                "event_type": "POLICY_EVALUATED",
                "decision": "ESCALATED",
                "reason": reason,
                "policy_version": cls.POLICY_VERSION,
                "metadata": {"amount": amount, "threshold": cls.HIGH_VALUE_THRESHOLD},
            })
            return "ESCALATED", idempotency_key, reason

        # Check Stopping Rules (Invariants 2, 3, 5, 6, 7)
        should_stop, stop_reason = StoppingRules.should_stop(case, attempt_number)
        if should_stop:
            decision = "BLOCKED" if "Duplicate" in stop_reason else "STOPPED"
            db.log_audit_event({
                "entity_type": "RECOVERY_CASE",
                "entity_id": case_id,
                "event_type": "POLICY_EVALUATED",
                "decision": decision,
                "reason": f"Policy rule halt: {stop_reason}",
                "policy_version": cls.POLICY_VERSION,
                "metadata": {"stop_reason": stop_reason, "attempt_number": attempt_number},
            })
            return decision, idempotency_key, f"Halted by policy: {stop_reason}"

        # Check Invariant 4: High Value Threshold
        if amount > cls.HIGH_VALUE_THRESHOLD:
            reason = f"Amount ₹{amount:,.2f} exceeds high-value threshold (₹{cls.HIGH_VALUE_THRESHOLD:,.2f}) — requires manual human approval."
            db.log_audit_event({
                "entity_type": "RECOVERY_CASE",
                "entity_id": case_id,
                "event_type": "POLICY_EVALUATED",
                "decision": "ESCALATED",
                "reason": reason,
                "policy_version": cls.POLICY_VERSION,
                "metadata": {"amount": amount, "threshold": cls.HIGH_VALUE_THRESHOLD},
            })
            return "ESCALATED", idempotency_key, reason

        # Check Action Type Safety
        if recommended_action == ActionType.ESCALATE_TO_HUMAN:
            reason = "Recommended action is ESCALATE_TO_HUMAN."
            db.log_audit_event({
                "entity_type": "RECOVERY_CASE",
                "entity_id": case_id,
                "event_type": "POLICY_EVALUATED",
                "decision": "ESCALATED",
                "reason": reason,
                "policy_version": cls.POLICY_VERSION,
                "metadata": {},
            })
            return "ESCALATED", idempotency_key, reason

        # If all policy checks pass -> APPROVED
        reason = f"Policy checks passed for action {recommended_action.value} (Attempt #{attempt_number}, Amount ₹{amount:,.2f})."
        db.log_audit_event({
            "entity_type": "RECOVERY_CASE",
            "entity_id": case_id,
            "event_type": "POLICY_EVALUATED",
            "decision": "APPROVED",
            "reason": reason,
            "policy_version": cls.POLICY_VERSION,
            "metadata": {"idempotency_key": idempotency_key, "amount": amount},
        })
        return "APPROVED", idempotency_key, reason
