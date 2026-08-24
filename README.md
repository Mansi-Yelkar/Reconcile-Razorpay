# Reconcile

**Track:** AI Revenue Recovery — Razorpay AI Buildathon 2026

A lot of "revenue recovery" pitches are retry bots: card got declined, try again later, done. That's a real problem, but it's not the interesting one. The interesting one is the money that isn't actually lost at all — it's just invisible.

Here's what I mean. A customer pays. The bank clears it. But the webhook that's supposed to tell the merchant's system "hey, this order is paid" gets dropped, times out, or arrives late. The merchant's dashboard says FAILED. The customer got charged. The order never got created. Someone on the ops team eventually writes this off as "lost revenue" — except the money never left. It's sitting in two ledgers that just disagree with each other.

**Reconcile** finds that gap automatically. It diffs the bank's ledger against the merchant's order ledger, scores how confident it is that a mismatch is safe to auto-close, and either fixes it, drafts it for a human, or flags it for manual review — with a full reasoning trail for every decision.

## Why this and not a retry bot

I almost built the retry bot. It's the obvious read of "revenue recovery" and I think most submissions in this track will be some version of it. But the more I thought about it, the retry-bot version doesn't actually need much intelligence — it's "if declined, wait and try again," dressed up. The reconciliation angle needs the model to actually weigh evidence (how long was the gap, is there a duplicate-looking sibling charge nearby) before deciding whether it's safe to move money-adjacent state on its own. That felt like the more honest use of "agentic" — an agent that knows when *not* to act automatically is more useful than one that always acts.

## How it works

```
bank_ledger  ─┐
              ├─▶ reconciliation_engine (match by ref_id) ─▶ confidence_scorer (logistic regression)
merchant_ledger┘                                                        │
                                                                          ▼
                                                              agent.decide() ─▶ SQLite audit log ─▶ dashboard
```

1. **`data_generator.py`** builds two ledgers the way real systems actually drift apart — clean matches, dropped-webhook ghosts, late settlements, an ambiguous 10–30 min band, duplicate charges, and genuine declines. (Details on why each category exists are in the file itself.)
2. **`reconciliation_engine.py`** matches bank rows to merchant rows by transaction reference — not by amount, since two different customers can both pay ₹499 — and buckets every row into matched / mismatch candidate / unmatched.
3. **`confidence_scorer.py`** is a small logistic regression trained on a synthetic labeled set that encodes the actual domain rule (short gap + no sibling charge = safe; long gap or a nearby same-amount charge = needs a second look). I picked logistic regression over a hand-written if/else specifically because "how confident are we" is a probability, not a boolean, and a hard cutoff doesn't degrade gracefully at the edges.
4. **`agent.py`** turns a confidence score into one of three actions — `AUTO_RECONCILE`, `DRAFT_FOR_REVIEW`, `ESCALATE` — and writes out *why* in plain language.
5. Every decision lands in **SQLite**, so the audit trail is a real, queryable table, not a log line that scrolls away.
6. The dashboard shows the two ledgers' disagreement as the actual centerpiece — not a generic "AI dashboard" with charts bolted on — plus a live "inject a dropped webhook" button so you can watch one decision happen end to end in about a second.

## Design decisions & tradeoffs (the parts I went back and forth on)

- **Matching key.** I first considered fuzzy-matching on amount + rough timestamp. Dropped it fast — with duplicate ₹499 orders in the mix, amount-only matching would merge two different customers' transactions and actually *create* false reconciliations instead of catching real ones. Switched to exact `ref_id` matching, which is how real payment reconciliation works anyway.
- **Duplicate charges vs. ghost payments.** These look identical from one angle — "bank has a SUCCESS the merchant doesn't know about" — but they need opposite treatment. A ghost payment should be closed out in the merchant's favor. A duplicate charge should go to a refund flow, not an auto-reconcile. I split them structurally: a duplicate's second charge has no matching `ref_id` on the merchant side at all, so it never even reaches the confidence scorer — it's routed straight to `unmatched_bank_rows` and always escalated. That felt safer than trusting a probability score to catch something a refund workflow should own.
- **Why the reasoning text is templated, not freely generated.** I thought about wiring this to an actual LLM call for the reasoning strings. Decided against it for the audit trail specifically — an audit log that a compliance person has to grep through six months from now needs consistent, predictable phrasing per action type, not stylistic variety. The "agentic" part is the *decision* (which action, based on which evidence) — the write-up doesn't need to sound different every time to prove that.
- **Threshold tiers (0.85 / 0.50).** Started stricter — 0.9 for auto-reconcile — but on the synthetic data that meant almost nothing ever auto-closed, which defeats the point. Loosened to 0.85 after checking what confidence scores clean webhook-drop cases were actually landing at.

## What broke while building this

The reconciliation engine originally treated *every* unmatched-ref bank row as a mismatch candidate and fed it through the confidence scorer. That meant duplicate charges — which have no time gap to reason about, since there's no merchant record to compare against — were getting a confidence score computed from garbage default values, and a few were landing in `AUTO_RECONCILE`. That's the worst possible failure mode for this project: auto-approving what might actually be a duplicate charge instead of flagging it. Fixed by splitting `unmatched_bank_rows` out of the scoring path entirely — they never touch the confidence model, they're always escalated, no exceptions.

## Running it

```bash
pip install -r requirements.txt
python backend/app.py
# open http://127.0.0.1:5050
```

The dashboard calls `/api/run` on load, which regenerates the two ledgers and re-runs the full pipeline, so every page load is a fresh scenario. Hit "inject a dropped webhook" to watch the agent resolve one new mismatch live.

## What I'd build next with more time

- Real settlement-file parsing instead of synthetic CSVs (Razorpay's actual settlement report format)
- A feedback loop where a human's review decision (confirm / reject) retrains the confidence scorer over time
- Slack webhook for the `DRAFT_FOR_REVIEW` queue instead of a dashboard-only view
