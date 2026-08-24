"""
db.py

Tiny SQLite wrapper for the audit trail. Kept deliberately simple — a
single table, no ORM — because the whole point of an audit log is that
you (or a panel interviewer) can open it in any SQLite browser and read
it directly, no framework required.
"""

import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "reconcile.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_id TEXT NOT NULL,
    amount REAL NOT NULL,
    rail TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence REAL NOT NULL,
    tier TEXT NOT NULL,
    time_gap_seconds REAL NOT NULL,
    has_close_sibling INTEGER NOT NULL,
    reasoning TEXT NOT NULL,
    decided_at TEXT NOT NULL
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(SCHEMA)
        conn.commit()


def reset_db():
    with get_conn() as conn:
        conn.execute("DROP TABLE IF EXISTS audit_log")
        conn.execute(SCHEMA)
        conn.commit()


def log_decision(decision: dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO audit_log
               (ref_id, amount, rail, action, confidence, tier,
                time_gap_seconds, has_close_sibling, reasoning, decided_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decision["ref_id"], decision["amount"], decision["rail"],
                decision["action"], decision["confidence"], decision["tier"],
                decision["time_gap_seconds"], int(decision["has_close_sibling"]),
                decision["reasoning"], decision["decided_at"],
            ),
        )
        conn.commit()


def all_decisions():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]
