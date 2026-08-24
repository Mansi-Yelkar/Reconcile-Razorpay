"""
app.py

Flask API for Reconcile. Endpoints:

  GET  /api/run           - regenerate ledgers, run the full pipeline,
                             return a summary + every transaction outcome
  GET  /api/audit-log      - the persisted decision trail
  POST /api/inject         - live demo: inject one fresh ghost-payment
                             mismatch and watch the agent resolve it on the spot
  GET  /                   - the dashboard
"""

import os
import random
import sys
import uuid
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory

sys.path.insert(0, os.path.dirname(__file__))

import agent
import data_generator
import db
import reconciliation_engine
from confidence_scorer import get_scorer

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

# in-memory pipeline state, rebuilt on /api/run
STATE = {"bank_rows": [], "merchant_rows": [], "result": None}


def run_pipeline():
    bank_rows, merchant_rows = data_generator.generate()
    data_generator.write_csvs(bank_rows, merchant_rows)
    STATE["bank_rows"] = bank_rows
    STATE["merchant_rows"] = merchant_rows

    reconciled = reconciliation_engine.reconcile(bank_rows, merchant_rows)
    STATE["result"] = reconciled

    db.reset_db()
    scorer = get_scorer()

    decisions = []
    for mismatch in reconciled["mismatch_candidates"]:
        confidence = scorer.score(mismatch["time_gap_seconds"], mismatch["has_close_sibling"])
        tier = scorer.tier(confidence)
        decision = agent.decide(mismatch, confidence, tier)
        db.log_decision(decision)
        decisions.append(decision)

    # unmatched bank rows (likely duplicates) always go to escalation, no
    # scoring needed — there's no merchant order to reconcile against at all
    for row in reconciled["unmatched_bank_rows"]:
        decision = {
            "ref_id": row["ref_id"], "amount": row["amount"], "rail": row["rail"],
            "action": "ESCALATE", "confidence": 0.0, "tier": "low",
            "time_gap_seconds": 0, "has_close_sibling": True,
            "reasoning": (
                f"Bank shows a SUCCESS debit for {row['ref_id']} (₹{row['amount']}, "
                f"{row['rail']}) with no matching merchant order at all. This usually "
                f"means a duplicate charge on an existing order rather than a missed "
                f"one — needs a refund decision, not an order update. Escalating."
            ),
            "decided_at": datetime.now().isoformat(),
        }
        db.log_decision(decision)
        decisions.append(decision)

    found = sum(d["amount"] for d in decisions)
    auto_recovered = sum(d["amount"] for d in decisions if d["action"] == "AUTO_RECONCILE")
    review = sum(d["amount"] for d in decisions if d["action"] == "DRAFT_FOR_REVIEW")
    escalated = sum(d["amount"] for d in decisions if d["action"] == "ESCALATE")

    return {
        "summary": {
            "total_transactions": len(bank_rows),
            "matched_clean": len(reconciled["matched"]),
            "ghost_revenue_found": round(found, 2),
            "auto_recovered": round(auto_recovered, 2),
            "pending_review": round(review, 2),
            "escalated": round(escalated, 2),
        },
        "decisions": sorted(decisions, key=lambda d: d["decided_at"], reverse=True),
    }


@app.route("/api/run", methods=["GET"])
def api_run():
    return jsonify(run_pipeline())


@app.route("/api/audit-log", methods=["GET"])
def api_audit_log():
    return jsonify(db.all_decisions())


@app.route("/api/inject", methods=["POST"])
def api_inject():
    """Live demo: manufacture one fresh ghost-payment mismatch right now and
    let the agent resolve it, so a panel can watch the whole loop in ~1s."""
    amount = random.choice(data_generator.REALISTIC_AMOUNTS)
    rail = random.choice(data_generator.RAILS)
    ref = data_generator._ref_id(rail)
    bank_ts = datetime.now() - timedelta(seconds=random.randint(30, 240))
    merchant_ts = bank_ts + timedelta(seconds=random.randint(5, 30))

    bank_row = {"ref_id": ref, "amount": amount, "bank": random.choice(data_generator.BANKS),
                "rail": rail, "status": "SUCCESS", "ts": bank_ts.isoformat()}
    merchant_row = {"ref_id": ref, "amount": amount, "bank": bank_row["bank"],
                     "rail": rail, "status": "FAILED", "ts": merchant_ts.isoformat()}

    mismatch = {
        "bank": bank_row, "merchant": merchant_row,
        "time_gap_seconds": abs((bank_ts - merchant_ts).total_seconds()),
        "has_close_sibling": False,
    }
    scorer = get_scorer()
    confidence = scorer.score(mismatch["time_gap_seconds"], mismatch["has_close_sibling"])
    tier = scorer.tier(confidence)
    decision = agent.decide(mismatch, confidence, tier)
    db.log_decision(decision)
    return jsonify(decision)


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, port=5050)
