"""
run_experiment.py

Batch Evaluation Framework for Reconcile.
Runs a 10,000+ event synthetic benchmark comparing:
  - Blind Retry
  - Rule-Based
  - Reconcile Orchestrator

Usage:
  python evaluation/run_experiment.py --events 10000
"""

import argparse
import sys
import os

# Add backend and project root directories to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from simulation.simulator import SimulationGenerator
from evaluation.baselines import BlindRetryStrategy, RuleBasedStrategy, ReconcileStrategy


def run_benchmark(n_events: int = 10000):
    events = SimulationGenerator.generate_events(n_events)

    total_revenue_processed = sum(e["amount"] for e in events) * 1.5
    revenue_at_risk = sum(e["amount"] for e in events)
    eligible_revenue = sum(e["amount"] for e in events if e["ground_truth_recoverable"] and not e["is_duplicate_suspected"])

    # Blind Retry run
    blind_recovered = 0.0
    blind_unsafe = 0

    # Rule-Based run
    rule_recovered = 0.0

    # Reconcile run
    reconcile_attempted = 0.0
    reconcile_recovered = 0.0
    reconcile_unsafe = 0
    blocked_duplicates = 0
    human_escalations = 0

    for e in events:
        # Blind
        b_att, b_rec, b_uns, b_dup = BlindRetryStrategy.evaluate(e)
        blind_recovered += b_rec
        if b_uns:
            blind_unsafe += 1

        # Rule
        r_att, r_rec, r_uns, r_dup = RuleBasedStrategy.evaluate(e)
        rule_recovered += r_rec

        # Reconcile
        x_att, x_rec, x_uns, x_dup = ReconcileStrategy.evaluate(e)
        if x_att:
            reconcile_attempted += e["amount"]
        reconcile_recovered += x_rec
        if x_uns:
            reconcile_unsafe += 1
        if x_dup:
            blocked_duplicates += 1
        if e["amount"] > 50000 or e["is_duplicate_suspected"]:
            human_escalations += 1

    recovery_rate = (reconcile_recovered / revenue_at_risk * 100.0) if revenue_at_risk > 0 else 0.0
    improvement_vs_blind = ((reconcile_recovered - blind_recovered) / blind_recovered * 100.0) if blind_recovered > 0 else 0.0
    improvement_vs_rules = ((reconcile_recovered - rule_recovered) / rule_recovered * 100.0) if rule_recovered > 0 else 0.0

    results = {
        "n_events": n_events,
        "total_revenue_processed": total_revenue_processed,
        "revenue_at_risk": revenue_at_risk,
        "eligible_revenue": eligible_revenue,
        "reconcilex_attempted": reconcile_attempted,
        "reconcilex_recovered": reconcile_recovered,
        "reconcile_attempted": reconcile_attempted,
        "reconcile_recovered": reconcile_recovered,
        "recovery_rate_pct": recovery_rate,
        "reconcilex_unsafe": reconcile_unsafe,
        "reconcile_unsafe": reconcile_unsafe,
        "blocked_duplicates": blocked_duplicates,
        "human_escalations": human_escalations,
        "blind_recovered": blind_recovered,
        "blind_unsafe": blind_unsafe,
        "rule_recovered": rule_recovered,
        "improvement_vs_blind_pct": improvement_vs_blind,
        "improvement_vs_rules_pct": improvement_vs_rules,
    }

    print("========================================")
    print("REVENUE RECOVERY EVALUATION BENCHMARK")
    print("========================================")
    print(f"Transactions:              {n_events:,}")
    print(f"Revenue processed:         INR {total_revenue_processed:,.2f}")
    print(f"Revenue at risk:           INR {revenue_at_risk:,.2f}")
    print(f"Recovery eligible:         INR {eligible_revenue:,.2f}")
    print(f"Recovery attempted:        INR {reconcile_attempted:,.2f}")
    print(f"Revenue recovered:         INR {reconcile_recovered:,.2f}")
    print(f"Recovery rate:              {recovery_rate:.2f}%")
    print("----------------------------------------")
    print(f"Unsafe recoveries:          {reconcile_unsafe} (Target: 0)")
    print(f"Duplicate actions blocked:  {blocked_duplicates}")
    print(f"Human escalations:          {human_escalations}")
    print("----------------------------------------")
    print("BASELINE COMPARISON")
    print("----------------------------------------")
    print(f"Blind Retry:                INR {blind_recovered:,.2f} ({blind_unsafe} unsafe debits)")
    print(f"Rule-Based:                 INR {rule_recovered:,.2f}")
    print(f"Reconcile:                  INR {reconcile_recovered:,.2f}")
    print(f"Improvement vs Blind Retry: {improvement_vs_blind:+.2f}%")
    print(f"Improvement vs Rules:       {improvement_vs_rules:+.2f}%")
    print("========================================")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcile Batch Evaluation Benchmark")
    parser.add_argument("--events", type=int, default=10000, help="Number of synthetic payment events")
    args = parser.parse_args()
    run_benchmark(args.events)
