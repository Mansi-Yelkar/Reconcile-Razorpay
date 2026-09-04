"""
simulator.py

Synthetic Revenue Recovery Simulator for ReconcileX.
Generates 10,000+ payment events across failure modes:
  - PAYMENT_FAILURE (Issuer timeout, Insufficient funds, Network drop)
  - WEBHOOK_LOSS (Dropped webhooks, state mismatch)
  - SUBSCRIPTION_FAILURE (Mandate debits)
  - CHECKOUT_ABANDONMENT (Idle carts)
  - DUPLICATE_SUSPECTED (Double debits, sibling transactions)
Annotates ground truth recoverability to allow accurate evaluation.
"""

from datetime import datetime, timedelta
import random
import uuid
from typing import Any, Dict, List

random.seed(42)

REALISTIC_AMOUNTS = [199, 499, 999, 1499, 2499, 4999, 9999, 14999, 24999, 49999, 75000]
RAILS = ["UPI", "CARD", "NETBANKING"]
FAILURE_MODES = [
    ("PAYMENT_FAILURE", "ISSUER_TIMEOUT", 0.40),
    ("PAYMENT_FAILURE", "INSUFFICIENT_FUNDS", 0.20),
    ("WEBHOOK_LOSS", "WEBHOOK_MISSING", 0.15),
    ("SUBSCRIPTION_FAILURE", "SUBSCRIPTION_FAILURE", 0.10),
    ("CHECKOUT_ABANDONMENT", "CHECKOUT_ABANDONMENT", 0.10),
    ("DUPLICATE_SUSPECTED", "DUPLICATE_SUSPECTED", 0.05),
]


class SimulationGenerator:
    """Generates synthetic dataset of payment events with ground truth outcomes."""

    @staticmethod
    def generate_events(n: int = 10000) -> List[Dict[str, Any]]:
        events = []
        base_time = datetime.now() - timedelta(days=7)

        for i in range(n):
            mode, cause, weight = random.choices(FAILURE_MODES, weights=[m[2] for m in FAILURE_MODES])[0]
            amount = random.choice(REALISTIC_AMOUNTS)
            rail = random.choice(RAILS)
            created_at = base_time + timedelta(seconds=i * 60 + random.randint(0, 45))

            pay_id = f"pay_sim_{uuid.uuid4().hex[:8]}"
            order_id = f"ord_sim_{uuid.uuid4().hex[:8]}"
            cust_id = f"cust_{random.randint(1000, 9999)}"

            # Annotate ground truth recoverability
            ground_truth_recoverable = False
            if cause in ("WEBHOOK_MISSING", "ISSUER_TIMEOUT", "SUBSCRIPTION_FAILURE"):
                ground_truth_recoverable = random.random() < 0.85
            elif cause == "CHECKOUT_ABANDONMENT":
                ground_truth_recoverable = random.random() < 0.60
            elif cause == "INSUFFICIENT_FUNDS":
                ground_truth_recoverable = random.random() < 0.10
            elif cause == "DUPLICATE_SUSPECTED":
                ground_truth_recoverable = False

            events.append({
                "id": pay_id,
                "gateway_payment_id": pay_id,
                "order_id": order_id,
                "customer_id": cust_id,
                "amount": amount,
                "rail": rail,
                "case_type": mode,
                "root_cause": cause,
                "failure_code": cause,
                "failure_reason": f"Synthetic simulation event for {cause}",
                "is_duplicate_suspected": (cause == "DUPLICATE_SUSPECTED"),
                "ground_truth_recoverable": ground_truth_recoverable,
                "created_at": created_at.isoformat(),
                "time_gap_seconds": random.randint(10, 3600),
            })
        return events
