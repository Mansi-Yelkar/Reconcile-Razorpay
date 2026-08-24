"""
reconciliation_engine.py

Matches the bank ledger against the merchant ledger and buckets every row
into one of:

  matched            - both sides agree, nothing to do
  mismatch_candidate - bank says SUCCESS, merchant doesn't -> possible ghost
                        payment, gets handed to the confidence scorer + agent
  unmatched_bank_row - a bank debit with no corresponding merchant order at
                        all -> usually a duplicate charge, never auto-resolved

Matching key is ref_id first (exact transaction reference), which is how
real reconciliation works — you don't fuzzy-match on amount alone, that's
how you'd accidentally merge two different customers' ₹499 orders.
"""

from datetime import datetime


def _parse_ts(ts):
    return datetime.fromisoformat(ts)


def reconcile(bank_rows, merchant_rows):
    merchant_by_ref = {}
    for m in merchant_rows:
        merchant_by_ref.setdefault(m["ref_id"], []).append(m)

    # index bank rows by (amount, rail) to detect duplicate-charge patterns
    bank_by_amount_rail = {}
    for b in bank_rows:
        bank_by_amount_rail.setdefault((b["amount"], b["rail"]), []).append(b)

    matched = []
    mismatch_candidates = []
    unmatched_bank_rows = []

    for b in bank_rows:
        matches = merchant_by_ref.get(b["ref_id"])
        if not matches:
            # no merchant order for this bank debit at all
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
            # does this bank ref have a sibling bank row of the same amount+rail
            # very close in time? that's the duplicate-charge signature, not a
            # ghost payment, even though it also looks like "bank has money
            # merchant doesn't know about"
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

        # anything else (e.g. bank FAILED, merchant SUCCESS - shouldn't happen
        # but don't silently drop it) goes to unmatched for human eyes
        unmatched_bank_rows.append(b)

    return {
        "matched": matched,
        "mismatch_candidates": mismatch_candidates,
        "unmatched_bank_rows": unmatched_bank_rows,
    }
