"""
idempotency.py

Idempotency Manager for ReconcileX.
Generates unique idempotency keys for recovery actions and prevents duplicate execution.
"""

from typing import Optional
import db


class IdempotencyManager:
    """Manages unique action keys to enforce single-execution invariant."""

    @staticmethod
    def generate_key(case_id: str, action_type: str, attempt_number: int) -> str:
        return f"{case_id}:{action_type}:{attempt_number}"

    @classmethod
    def is_already_executed(cls, idempotency_key: str) -> bool:
        existing = db.get_action_by_idempotency(idempotency_key)
        return existing is not None and existing.get("status") in ("EXECUTED", "VERIFIED")
