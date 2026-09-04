"""
risk_detector.py

Revenue Risk Detector for ReconcileX.
Ingests payment events and reconciliation signals to detect revenue at risk,
assign initial case metadata, and persist RecoveryCase instances.
"""

from datetime import datetime
import uuid
from typing import Any, Dict, List, Optional
import db
from models.domain import CaseStatus, CaseType, PriorityTier, RecoveryCase


class RiskDetector:
    """Detects revenue loss scenarios and registers recovery cases in DB."""

    @staticmethod
    def detect_payment_failure(payment: Dict[str, Any]) -> RecoveryCase:
        case_id = f"RC-PAY-{uuid.uuid4().hex[:8].upper()}"
        amount = payment["amount"]
        priority = PriorityTier.HIGH if amount >= 10000 else (PriorityTier.MEDIUM if amount >= 2000 else PriorityTier.LOW)

        case = RecoveryCase(
            id=case_id,
            payment_id=payment["id"],
            case_type=CaseType.PAYMENT_FAILURE,
            amount_at_risk=amount,
            status=CaseStatus.DETECTED,
            priority=priority,
            created_at=datetime.now().isoformat(),
            evidence=[
                f"Gateway payment {payment['gateway_payment_id']} status FAILED",
                f"Failure code: {payment.get('failure_code', 'GATEWAY_ERROR')}",
                f"Failure reason: {payment.get('failure_reason', 'Transaction failed')}",
            ],
        )
        db.save_recovery_case(case.model_dump())
        db.log_audit_event({
            "entity_type": "RECOVERY_CASE",
            "entity_id": case.id,
            "event_type": "DETECTED",
            "decision": "APPROVED",
            "reason": f"Payment failure detected for ₹{amount:.2f} ({payment.get('failure_code')})",
            "metadata": {"payment_id": payment["id"], "amount": amount},
        })
        return case

    @staticmethod
    def detect_webhook_loss(mismatch: Dict[str, Any]) -> RecoveryCase:
        bank = mismatch["bank"]
        merchant = mismatch["merchant"]
        case_id = f"RC-WHK-{uuid.uuid4().hex[:8].upper()}"
        amount = bank["amount"]
        gap = mismatch["time_gap_seconds"]

        case = RecoveryCase(
            id=case_id,
            payment_id=bank.get("id", bank["ref_id"]),
            case_type=CaseType.WEBHOOK_LOSS,
            amount_at_risk=amount,
            status=CaseStatus.DETECTED,
            priority=PriorityTier.HIGH,
            created_at=datetime.now().isoformat(),
            is_duplicate_suspected=mismatch.get("has_close_sibling", False),
            evidence=[
                f"Bank confirms SUCCESS for ref {bank['ref_id']} (₹{amount})",
                f"Merchant order {merchant['ref_id']} status is {merchant['status']}",
                f"Time gap: {gap:.1f} seconds between bank and merchant records",
                f"Close sibling charge detected: {mismatch.get('has_close_sibling', False)}",
            ],
        )
        db.save_recovery_case(case.model_dump())
        db.log_audit_event({
            "entity_type": "RECOVERY_CASE",
            "entity_id": case.id,
            "event_type": "DETECTED",
            "decision": "APPROVED",
            "reason": f"Webhook loss detected for ref {bank['ref_id']} (₹{amount})",
            "metadata": {"ref_id": bank["ref_id"], "amount": amount, "time_gap_seconds": gap},
        })
        return case

    @staticmethod
    def detect_subscription_failure(sub_event: Dict[str, Any]) -> RecoveryCase:
        case_id = f"RC-SUB-{uuid.uuid4().hex[:8].upper()}"
        amount = sub_event["amount"]

        case = RecoveryCase(
            id=case_id,
            payment_id=sub_event.get("payment_id", f"pay_sub_{uuid.uuid4().hex[:6]}"),
            case_type=CaseType.SUBSCRIPTION_FAILURE,
            amount_at_risk=amount,
            status=CaseStatus.DETECTED,
            priority=PriorityTier.MEDIUM,
            created_at=datetime.now().isoformat(),
            evidence=[
                f"Subscription {sub_event.get('subscription_id', 'SUB_UNKNOWN')} recurring charge failed",
                f"Attempt count: {sub_event.get('attempt_count', 1)}",
                f"Reason: {sub_event.get('reason', 'Mandate debit failure')}",
            ],
        )
        db.save_recovery_case(case.model_dump())
        db.log_audit_event({
            "entity_type": "RECOVERY_CASE",
            "entity_id": case.id,
            "event_type": "DETECTED",
            "decision": "APPROVED",
            "reason": f"Subscription failure detected for ₹{amount:.2f}",
            "metadata": sub_event,
        })
        return case

    @staticmethod
    def detect_checkout_abandonment(checkout_event: Dict[str, Any]) -> RecoveryCase:
        case_id = f"RC-ABN-{uuid.uuid4().hex[:8].upper()}"
        amount = checkout_event["amount"]

        case = RecoveryCase(
            id=case_id,
            payment_id=checkout_event.get("session_id", f"sess_{uuid.uuid4().hex[:6]}"),
            case_type=CaseType.CHECKOUT_ABANDONMENT,
            amount_at_risk=amount,
            status=CaseStatus.DETECTED,
            priority=PriorityTier.LOW,
            created_at=datetime.now().isoformat(),
            evidence=[
                f"Checkout session {checkout_event.get('session_id')} idle for {checkout_event.get('idle_minutes', 15)} mins",
                f"Cart items value: ₹{amount}",
                f"Customer ID: {checkout_event.get('customer_id', 'CUST_ANON')}",
            ],
        )
        db.save_recovery_case(case.model_dump())
        db.log_audit_event({
            "entity_type": "RECOVERY_CASE",
            "entity_id": case.id,
            "event_type": "DETECTED",
            "decision": "APPROVED",
            "reason": f"Checkout abandonment detected for ₹{amount:.2f}",
            "metadata": checkout_event,
        })
        return case

    @staticmethod
    def detect_duplicate_suspected(bank_row: Dict[str, Any]) -> RecoveryCase:
        case_id = f"RC-DUP-{uuid.uuid4().hex[:8].upper()}"
        amount = bank_row["amount"]

        case = RecoveryCase(
            id=case_id,
            payment_id=bank_row.get("id", bank_row["ref_id"]),
            case_type=CaseType.DUPLICATE_SUSPECTED,
            amount_at_risk=amount,
            status=CaseStatus.DETECTED,
            priority=PriorityTier.HIGH,
            is_duplicate_suspected=True,
            created_at=datetime.now().isoformat(),
            evidence=[
                f"Bank debit for {bank_row['ref_id']} (₹{amount}) has no matching merchant order",
                "High risk of duplicate charge or rogue debit",
            ],
        )
        db.save_recovery_case(case.model_dump())
        db.log_audit_event({
            "entity_type": "RECOVERY_CASE",
            "entity_id": case.id,
            "event_type": "DETECTED",
            "decision": "BLOCKED",
            "reason": f"Duplicate debit suspected for ref {bank_row['ref_id']} (₹{amount})",
            "metadata": bank_row,
        })
        return case
