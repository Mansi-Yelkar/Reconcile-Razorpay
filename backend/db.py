"""
db.py

SQLite storage layer for ReconcileX — AI Revenue Recovery Orchestrator.
Manages payments, orders, recovery cases, recovery actions, audit events,
and analytics aggregation queries.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "reconcile.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    gateway_payment_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    merchant_id TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    method TEXT NOT NULL,
    status TEXT NOT NULL,
    failure_code TEXT,
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recovery_cases (
    id TEXT PRIMARY KEY,
    payment_id TEXT NOT NULL,
    case_type TEXT NOT NULL,
    amount_at_risk REAL NOT NULL,
    risk_score REAL NOT NULL,
    recovery_probability REAL NOT NULL,
    estimated_net_value REAL NOT NULL,
    root_cause TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 2,
    is_duplicate_suspected INTEGER NOT NULL DEFAULT 0,
    evidence TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS recovery_actions (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    policy_version TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL,
    amount_recovered REAL NOT NULL DEFAULT 0.0,
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    executed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_cases_payment ON recovery_cases(payment_id);
CREATE INDEX IF NOT EXISTS idx_cases_status ON recovery_cases(status);
CREATE INDEX IF NOT EXISTS idx_actions_case ON recovery_actions(case_id);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_type, entity_id);
"""


@contextmanager
def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def reset_db():
    with get_conn() as conn:
        conn.execute("DROP TABLE IF EXISTS payments")
        conn.execute("DROP TABLE IF EXISTS orders")
        conn.execute("DROP TABLE IF EXISTS recovery_cases")
        conn.execute("DROP TABLE IF EXISTS recovery_actions")
        conn.execute("DROP TABLE IF EXISTS audit_events")
        conn.executescript(SCHEMA)
        conn.commit()


# Payment Operations
def save_payment(p: Dict[str, Any]):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO payments
               (id, gateway_payment_id, order_id, customer_id, merchant_id, amount, currency, method, status, failure_code, failure_reason, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                p["id"], p["gateway_payment_id"], p["order_id"], p["customer_id"],
                p.get("merchant_id", "merchant_default"), p["amount"], p.get("currency", "INR"),
                p.get("method", "UPI"), p["status"], p.get("failure_code"),
                p.get("failure_reason"), p["created_at"], p.get("updated_at", p["created_at"])
            )
        )
        conn.commit()


def get_payment(payment_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        return dict(row) if row else None


# Order Operations
def save_order(o: Dict[str, Any]):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO orders (id, customer_id, amount, currency, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (o["id"], o["customer_id"], o["amount"], o.get("currency", "INR"), o["status"], o["created_at"])
        )
        conn.commit()


def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return dict(row) if row else None


# Recovery Case Operations
def save_recovery_case(c: Dict[str, Any]):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO recovery_cases
               (id, payment_id, case_type, amount_at_risk, risk_score, recovery_probability, estimated_net_value, root_cause, recommended_action, status, priority, retry_count, max_retries, is_duplicate_suspected, evidence, created_at, resolved_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                c["id"], c["payment_id"], c["case_type"], c["amount_at_risk"],
                c.get("risk_score", 0.0), c.get("recovery_probability", 0.0),
                c.get("estimated_net_value", 0.0), c.get("root_cause", "UNKNOWN"),
                c.get("recommended_action", "ESCALATE_TO_HUMAN"), c.get("status", "DETECTED"),
                c.get("priority", "MEDIUM"), c.get("retry_count", 0), c.get("max_retries", 2),
                1 if c.get("is_duplicate_suspected") else 0,
                json.dumps(c.get("evidence", [])), c["created_at"], c.get("resolved_at")
            )
        )
        conn.commit()


def get_recovery_case(case_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM recovery_cases WHERE id = ?", (case_id,)).fetchone()
        if not row:
            return None
        res = dict(row)
        res["evidence"] = json.loads(res["evidence"])
        res["is_duplicate_suspected"] = bool(res["is_duplicate_suspected"])
        return res


def all_recovery_cases(limit: int = 200) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM recovery_cases ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["evidence"] = json.loads(d["evidence"])
            d["is_duplicate_suspected"] = bool(d["is_duplicate_suspected"])
            result.append(d)
        return result


# Recovery Action Operations
def save_recovery_action(a: Dict[str, Any]):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO recovery_actions
               (id, case_id, action_type, attempt_number, policy_version, idempotency_key, status, amount_recovered, failure_reason, created_at, executed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                a["id"], a["case_id"], a["action_type"], a["attempt_number"],
                a.get("policy_version", "2.3"), a["idempotency_key"], a["status"],
                a.get("amount_recovered", 0.0), a.get("failure_reason"),
                a["created_at"], a.get("executed_at")
            )
        )
        conn.commit()


def get_action_by_idempotency(key: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM recovery_actions WHERE idempotency_key = ?", (key,)).fetchone()
        return dict(row) if row else None


def get_actions_for_case(case_id: str) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM recovery_actions WHERE case_id = ? ORDER BY attempt_number ASC", (case_id,)).fetchall()
        return [dict(r) for r in rows]


# Audit Event Operations
def log_audit_event(event: Dict[str, Any]):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO audit_events
               (entity_type, entity_id, event_type, actor, decision, reason, policy_version, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event["entity_type"], event["entity_id"], event["event_type"],
                event.get("actor", "Reconcile_Engine"), event["decision"], event["reason"],
                event.get("policy_version", "2.3"), json.dumps(event.get("metadata", {})),
                event.get("created_at", datetime.now().isoformat())
            )
        )
        conn.commit()


def all_audit_events(limit: int = 200) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["metadata"] = json.loads(d["metadata"])
            res.append(d)
        return res


# Analytics Operations
def get_analytics_overview() -> Dict[str, Any]:
    with get_conn() as conn:
        total_cases = conn.execute("SELECT COUNT(*) FROM recovery_cases").fetchone()[0]
        at_risk = conn.execute("SELECT SUM(amount_at_risk) FROM recovery_cases").fetchone()[0] or 0.0
        recovered = conn.execute("SELECT SUM(amount_recovered) FROM recovery_actions WHERE status = 'VERIFIED'").fetchone()[0] or 0.0
        active_cases = conn.execute("SELECT COUNT(*) FROM recovery_cases WHERE status IN ('DETECTED', 'DIAGNOSED', 'IN_PROGRESS')").fetchone()[0]
        blocked_actions = conn.execute("SELECT COUNT(*) FROM audit_events WHERE decision = 'BLOCKED'").fetchone()[0]
        
        recovery_rate = (recovered / at_risk * 100.0) if at_risk > 0 else 0.0

        return {
            "revenue_at_risk": round(at_risk, 2),
            "revenue_recovered": round(recovered, 2),
            "recovery_rate_pct": round(recovery_rate, 2),
            "total_cases": total_cases,
            "active_cases": active_cases,
            "blocked_actions": blocked_actions,
        }
