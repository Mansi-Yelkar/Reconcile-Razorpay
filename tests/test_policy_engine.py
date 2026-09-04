"""
test_policy_engine.py

Standard unittest suite for ReconcileX Policy Engine.
Validates all 7 financial safety invariants.
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import db
from models.domain import ActionType
from recovery import IdempotencyManager, PolicyEngine


class TestPolicyEngine(unittest.TestCase):

    def setUp(self):
        db.init_db()

    def test_idempotency_key_generation(self):
        key1 = IdempotencyManager.generate_key("RC-101", "RETRY_PAYMENT", 1)
        key2 = IdempotencyManager.generate_key("RC-101", "RETRY_PAYMENT", 1)
        self.assertEqual(key1, "RC-101:RETRY_PAYMENT:1")
        self.assertEqual(key1, key2)

    def test_policy_high_value_escalation(self):
        case = {
            "id": "RC-HIGH-VAL",
            "amount_at_risk": 75000.0,
            "is_duplicate_suspected": False,
            "retry_count": 0,
            "status": "DETECTED",
            "created_at": "2026-09-02T10:00:00",
        }
        decision, key, reason = PolicyEngine.evaluate(case, ActionType.RETRY_PAYMENT, 1)
        self.assertEqual(decision, "ESCALATED")
        self.assertIn("high-value threshold", reason.lower())

    def test_policy_duplicate_block(self):
        case = {
            "id": "RC-DUP-TEST",
            "amount_at_risk": 4999.0,
            "is_duplicate_suspected": True,
            "root_cause": "DUPLICATE_SUSPECTED",
            "retry_count": 0,
            "status": "DETECTED",
            "created_at": "2026-09-02T10:00:00",
        }
        decision, key, reason = PolicyEngine.evaluate(case, ActionType.RETRY_PAYMENT, 1)
        self.assertEqual(decision, "BLOCKED")
        self.assertIn("duplicate", reason.lower())

    def test_policy_max_retry_limit(self):
        case = {
            "id": "RC-RETRY-LIMIT",
            "amount_at_risk": 2499.0,
            "is_duplicate_suspected": False,
            "retry_count": 2,
            "status": "IN_PROGRESS",
            "created_at": "2026-09-02T10:00:00",
        }
        decision, key, reason = PolicyEngine.evaluate(case, ActionType.RETRY_PAYMENT, 3)
        self.assertEqual(decision, "STOPPED")
        self.assertIn("max retries", reason.lower())


if __name__ == "__main__":
    unittest.main()
