"""
data_generator.py

Generates two independent ledgers the way they'd actually diverge in production:

  - bank_ledger:      what actually happened to the money (source of truth)
  - merchant_ledger:  what the merchant's order system recorded

In a real stack these come from two different systems that talk to each other
over webhooks, so they drift. That drift is the whole problem this project
is about. Everything here is synthetic but the *shape* of the drift is
modeled on real failure modes:

  - webhook_drop:     bank confirms SUCCESS, merchant never got the callback,
                       so the order still shows FAILED/PENDING. This is a
                       "ghost payment" — money moved, records didn't catch up.
  - late_settlement:  bank confirms SUCCESS but late enough that the merchant
                       had already marked the order FAILED and moved on.
  - duplicate_charge: customer double-tapped pay, bank has two SUCCESS entries,
                       merchant only has one order. Looks like a mismatch but
                       is NOT free money — it needs a refund, not reconciliation.
  - genuine_decline:  bank says FAILED, merchant says FAILED. Both sides
                       agree. Nothing to reconcile here, only classic retry
                       logic applies (out of scope for this module).

Run standalone to regenerate the CSVs in ../data/.
"""

import csv
import os
import random
import uuid
from datetime import datetime, timedelta

random.seed(42)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# amounts that actually look like real order values, not round-number filler
REALISTIC_AMOUNTS = [
    149, 299, 349, 499, 599, 699, 849, 999, 1099, 1299,
    1499, 1799, 1999, 2299, 2499, 2850, 2999, 3499, 4999, 6999,
]

BANKS = ["HDFC", "ICICI", "AXIS", "SBI", "KOTAK", "YESB"]
RAILS = ["UPI", "CARD", "NETBANKING"]
DECLINE_CODES_GENUINE = [
    "INSUFFICIENT_FUNDS", "ISSUER_DECLINED", "EXPIRED_CARD", "RISK_DECLINED",
]


def _ist_now_minus(days_ago_max=3):
    base = datetime.now() - timedelta(
        days=random.randint(0, days_ago_max),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )
    return base


def _ref_id(rail):
    if rail == "UPI":
        return f"UPI{uuid.uuid4().hex[:12].upper()}"
    return f"TXN{uuid.uuid4().hex[:10].upper()}"


def generate(n_clean=140, n_ghost=22, n_late=14, n_duplicate=10,
             n_genuine_decline=30, n_borderline=9):
    """Returns (bank_rows, merchant_rows) as lists of dicts."""
    bank_rows = []
    merchant_rows = []

    def base_txn():
        rail = random.choice(RAILS)
        return {
            "ref_id": _ref_id(rail),
            "amount": random.choice(REALISTIC_AMOUNTS),
            "bank": random.choice(BANKS),
            "rail": rail,
            "ts": _ist_now_minus(),
        }

    # 1) clean matches — both sides agree, nothing to do
    for _ in range(n_clean):
        t = base_txn()
        bank_rows.append({**t, "status": "SUCCESS", "ts": t["ts"].isoformat()})
        merchant_rows.append({**t, "status": "SUCCESS", "ts": t["ts"].isoformat()})

    # 2) ghost payments — webhook drop. Bank says SUCCESS, merchant order stuck
    for _ in range(n_ghost):
        t = base_txn()
        merchant_ts = t["ts"] + timedelta(minutes=random.randint(1, 4))
        bank_rows.append({**t, "status": "SUCCESS", "ts": t["ts"].isoformat()})
        merchant_rows.append({
            **t, "status": random.choice(["FAILED", "PENDING"]),
            "ts": merchant_ts.isoformat(),
        })

    # 3) late settlement — bank SUCCESS lands much later than merchant expected
    for _ in range(n_late):
        t = base_txn()
        bank_ts = t["ts"] + timedelta(hours=random.randint(2, 9))
        bank_rows.append({**t, "status": "SUCCESS", "ts": bank_ts.isoformat()})
        merchant_rows.append({**t, "status": "FAILED", "ts": t["ts"].isoformat()})

    # 3b) borderline gap — 10 to 30 minutes. Not an obvious instant webhook
    # drop, not an obvious settlement delay either. This is the case the
    # confidence scorer earns its keep on: too ambiguous for a hand-written
    # threshold to call cleanly.
    for _ in range(n_borderline):
        t = base_txn()
        merchant_ts = t["ts"] + timedelta(minutes=random.randint(10, 29))
        bank_rows.append({**t, "status": "SUCCESS", "ts": t["ts"].isoformat()})
        merchant_rows.append({**t, "status": "FAILED", "ts": merchant_ts.isoformat()})

    # 4) duplicate charges — two bank debits, one merchant order. NOT free money.
    for _ in range(n_duplicate):
        t = base_txn()
        dup_ts = t["ts"] + timedelta(seconds=random.randint(20, 90))
        ref2 = _ref_id(t["rail"])
        bank_rows.append({**t, "status": "SUCCESS", "ts": t["ts"].isoformat()})
        bank_rows.append({
            **t, "ref_id": ref2, "status": "SUCCESS", "ts": dup_ts.isoformat(),
        })
        merchant_rows.append({**t, "status": "SUCCESS", "ts": t["ts"].isoformat()})

    # 5) genuine declines — both sides agree it failed
    for _ in range(n_genuine_decline):
        t = base_txn()
        code = random.choice(DECLINE_CODES_GENUINE)
        bank_rows.append({**t, "status": "FAILED", "decline_code": code, "ts": t["ts"].isoformat()})
        merchant_rows.append({**t, "status": "FAILED", "decline_code": code, "ts": t["ts"].isoformat()})

    random.shuffle(bank_rows)
    random.shuffle(merchant_rows)
    return bank_rows, merchant_rows


def write_csvs(bank_rows, merchant_rows):
    bank_path = os.path.join(DATA_DIR, "bank_ledger.csv")
    merchant_path = os.path.join(DATA_DIR, "merchant_ledger.csv")

    bank_fields = ["ref_id", "amount", "bank", "rail", "status", "decline_code", "ts"]
    merchant_fields = ["ref_id", "amount", "bank", "rail", "status", "decline_code", "ts"]

    with open(bank_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=bank_fields, extrasaction="ignore")
        w.writeheader()
        for r in bank_rows:
            w.writerow(r)

    with open(merchant_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=merchant_fields, extrasaction="ignore")
        w.writeheader()
        for r in merchant_rows:
            w.writerow(r)

    return bank_path, merchant_path


if __name__ == "__main__":
    bank_rows, merchant_rows = generate()
    bank_path, merchant_path = write_csvs(bank_rows, merchant_rows)
    print(f"wrote {len(bank_rows)} bank rows -> {bank_path}")
    print(f"wrote {len(merchant_rows)} merchant rows -> {merchant_path}")
