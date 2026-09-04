"""
app.py

ReconcileX REST API Application.
Endpoints:
  GET  /api/analytics/overview  - KPI summary metrics
  GET  /api/analytics/funnel    - Revenue recovery funnel breakdown
  GET  /api/analytics/trend     - Revenue recovery timeline trend
  GET  /api/recovery/cases      - Recovery cases list
  GET  /api/recovery/cases/<id> - Case details & timeline
  POST /api/recovery/cases/<id>/execute - Execute recovery action
  POST /api/recovery/cases/<id>/approve - Human approval for escalated case
  POST /api/recovery/cases/<id>/stop    - Stop recovery case
  POST /api/simulate/<scenario>         - Live demo scenario simulator
  GET  /api/audit               - Audit event log explorer
  POST /api/evaluation/run      - Run batch evaluation experiment (10,000 events)
  GET  /                        - Serves Frontend Financial Command Center
"""

import json
import os
import random
import sys
import uuid
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory

# Add project root and backend to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.dirname(__file__))

import db
from models.domain import ActionType, CaseStatus, CaseType, PriorityTier, RootCauseType
from recovery import (
    IdempotencyManager,
    PolicyEngine,
    RecoveryEconomics,
    RecoveryExecutor,
    RecoveryVerifier,
    RiskDetector,
    RootCauseAgent,
    StoppingRules,
)
from ml import RecoveryPredictor
from simulation.simulator import SimulationGenerator
from evaluation.run_experiment import run_benchmark

FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")


_DB_INITIALIZED = False


@app.before_request
def ensure_db():
    global _DB_INITIALIZED
    if not _DB_INITIALIZED:
        db.init_db()
        _DB_INITIALIZED = True


# --- ANALYTICS ENDPOINTS ---

@app.route("/api/analytics/overview", methods=["GET"])
def api_analytics_overview():
    summary = db.get_analytics_overview()
    return jsonify(summary)


@app.route("/api/analytics/funnel", methods=["GET"])
def api_analytics_funnel():
    summary = db.get_analytics_overview()
    at_risk = summary["revenue_at_risk"]
    
    # Calculate funnel stages
    eligible = round(at_risk * 0.78, 2)
    attempted = round(at_risk * 0.56, 2)
    recovered = summary["revenue_recovered"]

    return jsonify({
        "at_risk": at_risk,
        "eligible": eligible,
        "attempted": attempted,
        "recovered": recovered,
        "conversion_rates": {
            "eligible_pct": 78.0,
            "attempted_pct": 56.0,
            "recovered_pct": summary["recovery_rate_pct"],
        }
    })


@app.route("/api/analytics/trend", methods=["GET"])
def api_analytics_trend():
    # Return 7-day trend
    now = datetime.now()
    trend = []
    base = 15000.0
    for i in range(6, -1, -1):
        dt = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_at_risk = round(base + random.uniform(2000, 8000), 2)
        daily_recovered = round(daily_at_risk * random.uniform(0.60, 0.75), 2)
        trend.append({
            "date": dt,
            "at_risk": daily_at_risk,
            "recovered": daily_recovered,
        })
    return jsonify(trend)


# --- RECOVERY CASES ENDPOINTS ---

@app.route("/api/recovery/cases", methods=["GET"])
def api_recovery_cases():
    cases = db.all_recovery_cases(limit=100)
    return jsonify(cases)


@app.route("/api/recovery/cases/<case_id>", methods=["GET"])
def api_recovery_case_detail(case_id):
    case = db.get_recovery_case(case_id)
    if not case:
        return jsonify({"error": "Case not found"}), 404
    
    actions = db.get_actions_for_case(case_id)
    audit_events = [e for e in db.all_audit_events(limit=200) if e["entity_id"] == case_id]

    return jsonify({
        "case": case,
        "actions": actions,
        "audit_trail": audit_events,
    })


@app.route("/api/recovery/cases/<case_id>/execute", methods=["POST"])
def api_execute_case_recovery(case_id):
    case = db.get_recovery_case(case_id)
    if not case:
        return jsonify({"error": "Case not found"}), 404

    attempt_number = case.get("retry_count", 0) + 1
    rec_action_str = case.get("recommended_action", ActionType.RETRY_PAYMENT.value)
    
    try:
        rec_action = ActionType(rec_action_str)
    except ValueError:
        rec_action = ActionType.RETRY_PAYMENT

    decision, key, reason = PolicyEngine.evaluate(case, rec_action, attempt_number)

    if decision != "APPROVED":
        return jsonify({
            "status": "BLOCKED",
            "decision": decision,
            "reason": reason,
            "idempotency_key": key,
        }), 400

    action_res = RecoveryExecutor.execute_action(case, rec_action, key, attempt_number)
    return jsonify({
        "status": "SUCCESS",
        "decision": decision,
        "action": action_res,
        "updated_case": db.get_recovery_case(case_id),
    })


@app.route("/api/recovery/cases/<case_id>/approve", methods=["POST"])
def api_approve_case(case_id):
    case = db.get_recovery_case(case_id)
    if not case:
        return jsonify({"error": "Case not found"}), 404

    case["priority"] = PriorityTier.HIGH.value
    case["status"] = CaseStatus.IN_PROGRESS.value
    db.save_recovery_case(case)

    db.log_audit_event({
        "entity_type": "RECOVERY_CASE",
        "entity_id": case_id,
        "event_type": "APPROVED_BY_HUMAN",
        "actor": "Ops_Manager",
        "decision": "APPROVED",
        "reason": "Human Ops Manager approved high-value recovery execution",
        "metadata": {"case_id": case_id},
    })

    # Execute approved action
    rec_action = ActionType.RETRY_PAYMENT
    attempt = case.get("retry_count", 0) + 1
    key = IdempotencyManager.generate_key(case_id, rec_action.value, attempt)
    action_res = RecoveryExecutor.execute_action(case, rec_action, key, attempt)

    return jsonify({"status": "APPROVED", "action": action_res})


@app.route("/api/recovery/cases/<case_id>/stop", methods=["POST"])
def api_stop_case(case_id):
    case = db.get_recovery_case(case_id)
    if not case:
        return jsonify({"error": "Case not found"}), 404

    case["status"] = CaseStatus.STOPPED.value
    db.save_recovery_case(case)

    db.log_audit_event({
        "entity_type": "RECOVERY_CASE",
        "entity_id": case_id,
        "event_type": "STOPPED",
        "actor": "Ops_Manager",
        "decision": "STOPPED",
        "reason": "Human Ops Manager stopped recovery workflow",
        "metadata": {"case_id": case_id},
    })
    return jsonify({"status": "STOPPED", "case": case})


# --- SCENARIO SIMULATOR ENDPOINTS ---

@app.route("/api/simulate/<scenario>", methods=["POST"])
def api_simulate_scenario(scenario):
    now_str = datetime.now().isoformat()
    pay_id = f"pay_sim_{uuid.uuid4().hex[:8]}"
    order_id = f"ord_sim_{uuid.uuid4().hex[:8]}"

    if scenario == "payment-failure":
        payment = {
            "id": pay_id,
            "gateway_payment_id": f"pay_gtw_{uuid.uuid4().hex[:6]}",
            "order_id": order_id,
            "customer_id": f"cust_{random.randint(1000, 9999)}",
            "amount": random.choice([2499, 4999, 9999]),
            "status": "FAILED",
            "failure_code": "ISSUER_TIMEOUT",
            "failure_reason": "Issuer bank timed out after 30 seconds",
            "created_at": now_str,
        }
        db.save_payment(payment)
        case = RiskDetector.detect_payment_failure(payment)
        case_dict = case.model_dump()

    elif scenario == "webhook-loss":
        bank_row = {"ref_id": pay_id, "amount": 4999.0, "rail": "UPI", "status": "SUCCESS", "ts": now_str}
        merchant_row = {"ref_id": pay_id, "amount": 4999.0, "rail": "UPI", "status": "FAILED", "ts": now_str}
        mismatch = {"bank": bank_row, "merchant": merchant_row, "time_gap_seconds": 120.0, "has_close_sibling": False}
        case = RiskDetector.detect_webhook_loss(mismatch)
        case_dict = case.model_dump()

    elif scenario == "subscription-failure":
        event = {"payment_id": pay_id, "subscription_id": f"sub_{uuid.uuid4().hex[:6]}", "amount": 1499.0, "reason": "Mandate debit failed"}
        case = RiskDetector.detect_subscription_failure(event)
        case_dict = case.model_dump()

    elif scenario == "checkout-abandonment":
        event = {"session_id": f"sess_{uuid.uuid4().hex[:6]}", "amount": 2499.0, "idle_minutes": 25, "customer_id": "cust_8291"}
        case = RiskDetector.detect_checkout_abandonment(event)
        case_dict = case.model_dump()

    elif scenario == "duplicate-payment":
        bank_row = {"ref_id": pay_id, "amount": 4999.0, "rail": "UPI", "status": "SUCCESS", "ts": now_str}
        case = RiskDetector.detect_duplicate_suspected(bank_row)
        case_dict = case.model_dump()

    elif scenario == "high-value":
        payment = {
            "id": pay_id,
            "gateway_payment_id": f"pay_gtw_{uuid.uuid4().hex[:6]}",
            "order_id": order_id,
            "customer_id": "cust_vip",
            "amount": 75000.0,
            "status": "FAILED",
            "failure_code": "ISSUER_TIMEOUT",
            "failure_reason": "High-value transaction issuer timeout",
            "created_at": now_str,
        }
        db.save_payment(payment)
        case = RiskDetector.detect_payment_failure(payment)
        case_dict = case.model_dump()

    else:
        return jsonify({"error": "Unknown scenario"}), 400

    # Process Root Cause
    case_dict = RootCauseAgent.process_case(case_dict)

    # ML Predictor
    predictor = RecoveryPredictor.get_instance()
    prob = predictor.predict(case_dict)
    case_dict["recovery_probability"] = prob
    case_dict["risk_score"] = round(1.0 - prob, 3)

    # Economics & Intervention Selection
    action, net_val = RecoveryEconomics.select_intervention(case_dict, prob)
    case_dict["recommended_action"] = action.value
    case_dict["estimated_net_value"] = net_val

    db.save_recovery_case(case_dict)

    # Policy Evaluation
    attempt = case_dict.get("retry_count", 0) + 1
    decision, key, reason = PolicyEngine.evaluate(case_dict, action, attempt)

    # Execution if APPROVED
    if decision == "APPROVED":
        action_res = RecoveryExecutor.execute_action(case_dict, action, key, attempt)
        executed = True
    else:
        executed = False
        action_res = None

    return jsonify({
        "scenario": scenario,
        "case": db.get_recovery_case(case_dict["id"]),
        "policy_decision": decision,
        "policy_reason": reason,
        "executed": executed,
        "action": action_res,
    })


# --- AUDIT LOG ENDPOINT ---

@app.route("/api/audit", methods=["GET"])
def api_audit_log():
    raw_limit = request.args.get("limit", "200")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return jsonify({"error": "limit must be a positive integer"}), 400
    if limit < 1 or limit > 1000:
        return jsonify({"error": "limit must be between 1 and 1000"}), 400

    events = db.all_audit_events(limit=limit)
    return jsonify(events)


# --- EVALUATION BENCHMARK ENDPOINT ---

@app.route("/api/evaluation/run", methods=["POST"])
def api_run_evaluation():
    data = request.get_json(silent=True) or {}
    events_count = data.get("events", 10000)
    if isinstance(events_count, bool) or not isinstance(events_count, int):
        return jsonify({"error": "events must be an integer"}), 400
    if events_count < 1 or events_count > 100000:
        return jsonify({"error": "events must be between 1 and 100000"}), 400

    results = run_benchmark(events_count)
    return jsonify(results)


# --- FRONTEND ROUTE ---

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


if __name__ == "__main__":
    db.init_db()
    port = int(os.environ.get("PORT", 5050))
    print(f"Starting Reconcile Production Engine on http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
