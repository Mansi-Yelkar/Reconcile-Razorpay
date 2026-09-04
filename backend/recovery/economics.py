"""
economics.py

Recovery Economics module for ReconcileX.
Calculates Expected Net Recovery Value:
  Net Value = (Amount * P(recovery)) - Intervention Cost - Friction Penalty
Selects the intervention with maximum positive ROI or rejects negative EV actions.
"""

from typing import Any, Dict, Tuple
from models.domain import ActionType, CaseType, RootCauseType


INTERVENTION_COSTS = {
    ActionType.RESTORE_PAYMENT_STATE: {"cost": 0.50, "friction": 0.00},
    ActionType.RETRY_PAYMENT: {"cost": 5.00, "friction": 2.00},
    ActionType.RETRY_SUBSCRIPTION: {"cost": 5.00, "friction": 1.00},
    ActionType.GENERATE_RECOVERY_LINK: {"cost": 1.50, "friction": 5.00},
    ActionType.ESCALATE_TO_HUMAN: {"cost": 25.00, "friction": 0.00},
    ActionType.STOP_RECOVERY: {"cost": 0.00, "friction": 0.00},
}


class RecoveryEconomics:
    """Calculates ROI metrics and selects economic interventions."""

    @staticmethod
    def calculate_net_value(amount: float, prob: float, action: ActionType) -> float:
        meta = INTERVENTION_COSTS.get(action, {"cost": 5.00, "friction": 2.00})
        expected_recovery = amount * prob
        net_val = expected_recovery - meta["cost"] - meta["friction"]
        return round(net_val, 2)

    @classmethod
    def select_intervention(cls, case: Dict[str, Any], prob: float) -> Tuple[ActionType, float]:
        amount = case.get("amount_at_risk", 0.0)
        cause = case.get("root_cause")
        is_dup = case.get("is_duplicate_suspected")

        if is_dup or cause == RootCauseType.DUPLICATE_SUSPECTED.value:
            return ActionType.ESCALATE_TO_HUMAN, 0.0

        if cause == RootCauseType.WEBHOOK_MISSING.value:
            action = ActionType.RESTORE_PAYMENT_STATE
            net_val = cls.calculate_net_value(amount, prob, action)
            return action, net_val

        if cause == RootCauseType.CHECKOUT_ABANDONMENT.value:
            action = ActionType.GENERATE_RECOVERY_LINK
            net_val = cls.calculate_net_value(amount, prob, action)
            return action, net_val

        if cause == RootCauseType.SUBSCRIPTION_FAILURE.value:
            action = ActionType.RETRY_SUBSCRIPTION
            net_val = cls.calculate_net_value(amount, prob, action)
            return action, net_val

        if cause in (RootCauseType.ISSUER_TIMEOUT.value, RootCauseType.NETWORK_ERROR.value):
            action = ActionType.RETRY_PAYMENT
            net_val = cls.calculate_net_value(amount, prob, action)
            if net_val <= 0:
                return ActionType.STOP_RECOVERY, net_val
            return action, net_val

        if cause == RootCauseType.INSUFFICIENT_FUNDS.value:
            action = ActionType.GENERATE_RECOVERY_LINK
            net_val = cls.calculate_net_value(amount, prob, action)
            return action, net_val

        # Default fallback
        action = ActionType.ESCALATE_TO_HUMAN
        net_val = cls.calculate_net_value(amount, prob, action)
        return action, net_val
