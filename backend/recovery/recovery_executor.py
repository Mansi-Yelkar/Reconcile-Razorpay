"""
recovery_executor.py

Recovery Executor for ReconcileX.
Executes approved interventions via Adapter pattern:
  - SimulationAdapter (for benchmark simulations and synthetic scenarios)
  - RazorpayTestAdapter (for Razorpay Test Mode API integration)
"""

from datetime import datetime
import random
import uuid
from typing import Any, Dict, Tuple
import db
from models.domain import ActionType, CaseStatus
from recovery.verification import RecoveryVerifier


class SimulationAdapter:
    """Simulates gateway responses for bounded recovery actions."""

    @staticmethod
    def execute(action_type: str, case: Dict[str, Any]) -> Tuple[bool, float, str]:
        prob = case.get("recovery_probability", 0.75)
        amount = case.get("amount_at_risk", 0.0)

        if action_type == ActionType.RESTORE_PAYMENT_STATE.value:
            # Webhook loss repair always succeeds if payment was already verified on bank side
            return True, amount, "Merchant order state successfully reconciled with bank ledger"

        if action_type == ActionType.RETRY_PAYMENT.value:
            success = random.random() < prob
            if success:
                return True, amount, "Payment retry succeeded at gateway"
            return False, 0.0, "Payment retry failed at gateway (Issuer decline)"

        if action_type == ActionType.RETRY_SUBSCRIPTION.value:
            success = random.random() < (prob * 0.9)
            if success:
                return True, amount, "Recurring mandate payment debited successfully"
            return False, 0.0, "Recurring mandate debit declined by bank"

        if action_type == ActionType.GENERATE_RECOVERY_LINK.value:
            # Generates active payment link; simulation assumes 70% customer completion
            success = random.random() < 0.70
            if success:
                return True, amount, "Customer completed payment via recovery link"
            return False, 0.0, "Recovery payment link expired without customer payment"

        return False, 0.0, "Unsupported action type"


class RazorpayTestAdapter:
    """Integration adapter for Razorpay Test Mode API."""

    @staticmethod
    def execute(action_type: str, case: Dict[str, Any]) -> Tuple[bool, float, str]:
        # Razorpay Test Mode stub fallback to SimulationAdapter for sandbox run
        return SimulationAdapter.execute(action_type, case)


class RecoveryExecutor:
    """Orchestrates action execution, verification, and audit logging."""

    @classmethod
    def execute_action(cls, case: Dict[str, Any], action_type: ActionType, idempotency_key: str, attempt_number: int, adapter_type: str = "simulation") -> Dict[str, Any]:
        action_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"
        now_str = datetime.now().isoformat()

        adapter = RazorpayTestAdapter if adapter_type == "razorpay" else SimulationAdapter
        success, amount_rec, msg = adapter.execute(action_type.value, case)

        status = "EXECUTED" if success else "FAILED"

        action_dict = {
            "id": action_id,
            "case_id": case["id"],
            "action_type": action_type.value,
            "attempt_number": attempt_number,
            "policy_version": "2.3",
            "idempotency_key": idempotency_key,
            "status": status,
            "amount_recovered": 0.0,  # Unverified initially
            "failure_reason": None if success else msg,
            "created_at": now_str,
            "executed_at": now_str,
        }
        db.save_recovery_action(action_dict)

        db.log_audit_event({
            "entity_type": "RECOVERY_ACTION",
            "entity_id": action_id,
            "event_type": "EXECUTED",
            "decision": "APPROVED" if success else "FAILED",
            "reason": f"Executed {action_type.value}: {msg}",
            "metadata": {"case_id": case["id"], "success": success, "msg": msg},
        })

        # Phase 8: Post-Execution Verification
        if success:
            verified, ver_amount, ver_msg = RecoveryVerifier.verify(case, action_dict)
            if verified:
                action_dict["status"] = "VERIFIED"
                action_dict["amount_recovered"] = ver_amount
                db.save_recovery_action(action_dict)

                case["status"] = CaseStatus.RECOVERED.value
                case["resolved_at"] = datetime.now().isoformat()
                db.save_recovery_case(case)

                db.log_audit_event({
                    "entity_type": "RECOVERY_CASE",
                    "entity_id": case["id"],
                    "event_type": "VERIFIED",
                    "decision": "APPROVED",
                    "reason": f"Revenue recovery VERIFIED for ₹{ver_amount:,.2f}: {ver_msg}",
                    "metadata": {"amount_recovered": ver_amount},
                })
            else:
                case["status"] = CaseStatus.FAILED.value
                db.save_recovery_case(case)
        else:
            case["retry_count"] = case.get("retry_count", 0) + 1
            if case["retry_count"] >= case.get("max_retries", 2):
                case["status"] = CaseStatus.STOPPED.value
            else:
                case["status"] = CaseStatus.IN_PROGRESS.value
            db.save_recovery_case(case)

        return action_dict
