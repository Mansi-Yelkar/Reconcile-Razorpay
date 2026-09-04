"""
root_cause_agent.py

Root Cause Diagnosis Agent for ReconcileX.
Classifies revenue loss cases into standardized taxonomy:
  - ISSUER_TIMEOUT
  - INSUFFICIENT_FUNDS
  - NETWORK_ERROR
  - CUSTOMER_ABORTED
  - WEBHOOK_MISSING
  - DUPLICATE_SUSPECTED
  - SUBSCRIPTION_FAILURE
  - CHECKOUT_ABANDONMENT
  - UNKNOWN
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import db
from models.domain import CaseType, RootCauseType


class RootCauseAgent:
    """Diagnoses root cause for recovery cases using failure metadata and rules."""

    @staticmethod
    def diagnose(case: Dict[str, Any], payment_meta: Optional[Dict[str, Any]] = None) -> Tuple[RootCauseType, float, List[str]]:
        payment_meta = payment_meta or {}
        case_type = case.get("case_type")
        evidence = list(case.get("evidence", []))
        failure_code = (payment_meta.get("failure_code") or "").upper()
        failure_reason = (payment_meta.get("failure_reason") or "").upper()

        if case.get("is_duplicate_suspected") or case_type == CaseType.DUPLICATE_SUSPECTED.value:
            cause = RootCauseType.DUPLICATE_SUSPECTED
            confidence = 0.98
            evidence.append("Confirmed duplicate charge signature or unmatched bank debit.")
            return cause, confidence, evidence

        if case_type == CaseType.WEBHOOK_LOSS.value:
            cause = RootCauseType.WEBHOOK_MISSING
            confidence = 0.95
            evidence.append("Bank ledger confirms debit SUCCESS while merchant order status remained PENDING/FAILED.")
            return cause, confidence, evidence

        if case_type == CaseType.SUBSCRIPTION_FAILURE.value:
            cause = RootCauseType.SUBSCRIPTION_FAILURE
            confidence = 0.92
            evidence.append("Recurring subscription mandate execution failed at bank/switch.")
            return cause, confidence, evidence

        if case_type == CaseType.CHECKOUT_ABANDONMENT.value:
            cause = RootCauseType.CHECKOUT_ABANDONMENT
            confidence = 0.88
            evidence.append("Session timed out after cart creation without payment initiation.")
            return cause, confidence, evidence

        # Map specific gateway codes
        if "TIMEOUT" in failure_code or "TIMEOUT" in failure_reason or "GATEWAY_TIMEOUT" in failure_code:
            cause = RootCauseType.ISSUER_TIMEOUT
            confidence = 0.94
            evidence.append("Issuer bank failed to respond within 30-second window.")
        elif "INSUFFICIENT" in failure_code or "FUNDS" in failure_reason or "BAD_REQUEST_PAYMENT_DECLINED" in failure_code:
            cause = RootCauseType.INSUFFICIENT_FUNDS
            confidence = 0.91
            evidence.append("Customer account has insufficient funds for transaction.")
        elif "CANCELLED" in failure_code or "ABORTED" in failure_reason or "USER_CANCELLED" in failure_code:
            cause = RootCauseType.CUSTOMER_ABORTED
            confidence = 0.89
            evidence.append("User manually closed or aborted authentication challenge.")
        elif "NETWORK" in failure_code or "CONNECTION" in failure_reason or "NPCI_DOWN" in failure_code:
            cause = RootCauseType.NETWORK_ERROR
            confidence = 0.90
            evidence.append("NPCI / Payment switch network drop during processing.")
        else:
            cause = RootCauseType.ISSUER_TIMEOUT if "GATEWAY" in failure_code else RootCauseType.UNKNOWN
            confidence = 0.70
            evidence.append("Failure reason unclassified; default issuer delay assumed.")

        return cause, confidence, evidence

    @classmethod
    def process_case(cls, case_dict: Dict[str, Any], payment_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        cause, conf, evidence = cls.diagnose(case_dict, payment_meta)
        case_dict["root_cause"] = cause.value
        case_dict["evidence"] = evidence
        
        # update DB
        db.save_recovery_case(case_dict)
        db.log_audit_event({
            "entity_type": "RECOVERY_CASE",
            "entity_id": case_dict["id"],
            "event_type": "DIAGNOSED",
            "decision": "APPROVED",
            "reason": f"Root cause diagnosed as {cause.value} (confidence {conf:.2f})",
            "metadata": {"root_cause": cause.value, "confidence": conf, "evidence": evidence},
        })
        return case_dict
