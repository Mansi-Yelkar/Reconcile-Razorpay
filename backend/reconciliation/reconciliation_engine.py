"""
reconciliation_engine.py

Core reconciliation engine for ReconcileX.
Matches bank payment records against merchant order records and identifies inconsistencies.
Decoupled from financial execution — this module only returns detected mismatch signals.
"""

from datetime import datetime
from typing import Any, Dict, List


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def reconcile(bank_rows: List[Dict[str, Any]], merchant_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Buckets transactions into:
      - matched: bank & merchant state agree
      - mismatch_candidates: bank says SUCCESS, merchant says FAILED/PENDING
      - unmatched_bank_rows: bank debit without corresponding merchant record (duplicate charge candidate)
    """
    merchant_by_ref = {}
    for m in merchant_rows:
        merchant_by_ref.setdefault(m["ref_id"], []).append(m)

    bank_by_amount_rail = {}
    for b in bank_rows:
        bank_by_amount_rail.setdefault((b["amount"], b["rail"]), []).append(b)

    matched = []
    mismatch_candidates = []
    unmatched_bank_rows = []

    for b in bank_rows:
        matches = merchant_by_ref.get(b["ref_id"])
        if not matches:
            unmatched_bank_rows.append(b)
            continue

        m = matches[0]

        if b["status"] == "SUCCESS" and m["status"] == "SUCCESS":
            matched.append({"bank": b, "merchant": m, "reason": "both_success"})
            continue

        if b["status"] == "FAILED" and m["status"] == "FAILED":
            matched.append({"bank": b, "merchant": m, "reason": "both_failed_genuine_decline"})
            continue

        if b["status"] == "SUCCESS" and m["status"] in ("FAILED", "PENDING"):
            time_gap_seconds = abs(
                (_parse_ts(b["ts"]) - _parse_ts(m["ts"])).total_seconds()
            )
            siblings = bank_by_amount_rail.get((b["amount"], b["rail"]), [])
            has_close_sibling = any(
                s["ref_id"] != b["ref_id"]
                and abs((_parse_ts(s["ts"]) - _parse_ts(b["ts"])).total_seconds()) < 300
                for s in siblings
            )
            mismatch_candidates.append({
                "bank": b,
                "merchant": m,
                "time_gap_seconds": time_gap_seconds,
                "has_close_sibling": has_close_sibling,
            })
            continue

        unmatched_bank_rows.append(b)

    return {
        "matched": matched,
        "mismatch_candidates": mismatch_candidates,
        "unmatched_bank_rows": unmatched_bank_rows,
    }
