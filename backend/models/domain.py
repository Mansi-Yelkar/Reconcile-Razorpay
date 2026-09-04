"""
domain.py

Domain models for ReconcileX — AI Revenue Recovery Orchestrator.
Defines data structures for Payments, Orders, Recovery Cases, Recovery Actions, and Audit Events.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PaymentStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"
    REFUNDED = "REFUNDED"


class CaseType(str, Enum):
    PAYMENT_FAILURE = "PAYMENT_FAILURE"
    WEBHOOK_LOSS = "WEBHOOK_LOSS"
    SUBSCRIPTION_FAILURE = "SUBSCRIPTION_FAILURE"
    CHECKOUT_ABANDONMENT = "CHECKOUT_ABANDONMENT"
    DUPLICATE_SUSPECTED = "DUPLICATE_SUSPECTED"


class RootCauseType(str, Enum):
    ISSUER_TIMEOUT = "ISSUER_TIMEOUT"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    NETWORK_ERROR = "NETWORK_ERROR"
    CUSTOMER_ABORTED = "CUSTOMER_ABORTED"
    WEBHOOK_MISSING = "WEBHOOK_MISSING"
    DUPLICATE_SUSPECTED = "DUPLICATE_SUSPECTED"
    SUBSCRIPTION_FAILURE = "SUBSCRIPTION_FAILURE"
    CHECKOUT_ABANDONMENT = "CHECKOUT_ABANDONMENT"
    UNKNOWN = "UNKNOWN"


class ActionType(str, Enum):
    RETRY_PAYMENT = "RETRY_PAYMENT"
    GENERATE_RECOVERY_LINK = "GENERATE_RECOVERY_LINK"
    RESTORE_PAYMENT_STATE = "RESTORE_PAYMENT_STATE"
    RETRY_SUBSCRIPTION = "RETRY_SUBSCRIPTION"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"
    STOP_RECOVERY = "STOP_RECOVERY"


class CaseStatus(str, Enum):
    DETECTED = "DETECTED"
    DIAGNOSED = "DIAGNOSED"
    IN_PROGRESS = "IN_PROGRESS"
    RECOVERED = "RECOVERED"
    BLOCKED = "BLOCKED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class PriorityTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Payment(BaseModel):
    id: str
    gateway_payment_id: str
    order_id: str
    customer_id: str
    merchant_id: str = "merchant_default"
    amount: float
    currency: str = "INR"
    method: str = "UPI"  # UPI, CARD, NETBANKING
    status: PaymentStatus
    failure_code: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: str
    updated_at: str


class Order(BaseModel):
    id: str
    customer_id: str
    amount: float
    currency: str = "INR"
    status: str = "PENDING"  # PENDING, PAID, FAILED, CANCELLED
    created_at: str


class RecoveryCase(BaseModel):
    id: str
    payment_id: str
    case_type: CaseType
    amount_at_risk: float
    risk_score: float = 0.0
    recovery_probability: float = 0.0
    estimated_net_value: float = 0.0
    root_cause: RootCauseType = RootCauseType.UNKNOWN
    recommended_action: ActionType = ActionType.ESCALATE_TO_HUMAN
    status: CaseStatus = CaseStatus.DETECTED
    priority: PriorityTier = PriorityTier.MEDIUM
    retry_count: int = 0
    max_retries: int = 2
    is_duplicate_suspected: bool = False
    evidence: List[str] = Field(default_factory=list)
    created_at: str
    resolved_at: Optional[str] = None


class RecoveryAction(BaseModel):
    id: str
    case_id: str
    action_type: ActionType
    attempt_number: int
    policy_version: str = "2.3"
    idempotency_key: str
    status: str  # EXECUTED, BLOCKED, VERIFIED, FAILED
    amount_recovered: float = 0.0
    failure_reason: Optional[str] = None
    created_at: str
    executed_at: Optional[str] = None


class AuditEvent(BaseModel):
    id: Optional[int] = None
    entity_type: str  # RECOVERY_CASE, RECOVERY_ACTION, PAYMENT
    entity_id: str
    event_type: str  # DETECTED, DIAGNOSED, POLICY_EVALUATED, EXECUTED, VERIFIED, BLOCKED, ESCALATED
    actor: str = "ReconcileX_Engine"
    decision: str  # APPROVED, BLOCKED, ESCALATED, STOPPED
    reason: str
    policy_version: str = "2.3"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
