"""
stopping_rules.py

Stopping Rules Evaluator for ReconcileX.
Determines whether a recovery workflow must halt based on retry limits,
time windows, negative expected value, or duplicate flags.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Tuple


class StoppingRules:
    """Evaluates stopping conditions for recovery workflows."""

    MAX_RETRIES = 2
    MAX_RECOVERY_WINDOW_HOURS = 24

    @classmethod
    def should_stop(cls, case: Dict[str, Any], attempt_number: int) -> Tuple[bool, str]:
        # Rule 1: Already recovered
        if case.get("status") == "RECOVERED":
            return True, "Payment state already verified as RECOVERED"

        # Rule 2: Max retries exceeded
        if attempt_number > cls.MAX_RETRIES or case.get("retry_count", 0) >= cls.MAX_RETRIES:
            return True, f"Max retries limit reached ({cls.MAX_RETRIES})"

        # Rule 3: Duplicate charge suspected
        if case.get("is_duplicate_suspected") or case.get("root_cause") == "DUPLICATE_SUSPECTED":
            return True, "Duplicate charge suspected — automated recovery halted"

        # Rule 4: Recovery window expired
        created_at_str = case.get("created_at")
        if created_at_str:
            try:
                created_dt = datetime.fromisoformat(created_at_str)
                if datetime.now() - created_dt > timedelta(hours=cls.MAX_RECOVERY_WINDOW_HOURS):
                    return True, f"Recovery window expired (> {cls.MAX_RECOVERY_WINDOW_HOURS} hours)"
            except Exception:
                pass

        # Rule 5: Negative expected value
        if case.get("estimated_net_value", 0.0) <= 0 and case.get("recommended_action") not in ("RESTORE_PAYMENT_STATE", "ESCALATE_TO_HUMAN"):
            return True, "Expected net recovery value is zero or negative"

        return False, "Active"
