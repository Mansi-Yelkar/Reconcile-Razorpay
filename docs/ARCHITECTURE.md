# Architecture — Reconcile

## Problem framing

Failed-payment recovery usually means "retry the charge." This project targets a narrower but higher-leverage problem inside the same track: transactions the bank ledger shows as **successful** that the merchant's own system shows as **failed**, because the two systems disagree rather than because the payment genuinely failed. That disagreement is silent — nobody's alerted, it just accumulates as written-off revenue.

## Components

| Component | File | Responsibility |
|---|---|---|
| Ledger generator | `backend/data_generator.py` | Produces two independent, realistic ledgers (bank + merchant) with modeled drift patterns |
| Reconciliation engine | `backend/reconciliation_engine.py` | Matches rows by transaction reference, classifies each pair as matched / mismatch candidate / unmatched |
| Confidence scorer | `backend/confidence_scorer.py` | Logistic regression estimating P(safe to auto-resolve) from time-gap and duplicate-sibling features |
| Decision agent | `backend/agent.py` | Maps a confidence tier to one of three actions and writes a plain-language justification |
| Audit store | `backend/db.py` | SQLite table logging every decision, timestamped and queryable |
| API | `backend/app.py` | Flask endpoints: run the pipeline, fetch the audit log, inject a live demo case |
| Dashboard | `frontend/` | Displays the mismatch table, per-decision reasoning, and summary stats |

## Decision flow

```
bank row × merchant row (same ref_id)
        │
        ▼
   status agreement?
        │
   ┌────┴────┐
  yes        no  →  time_gap_seconds, has_close_sibling
   │                        │
matched                confidence_scorer.score()
(no action)                 │
                    ┌────────┼────────┐
                  ≥0.85    0.50–0.85   <0.50
                    │          │          │
             AUTO_RECONCILE  DRAFT    ESCALATE
                            FOR_REVIEW
```

Bank rows with **no matching merchant reference at all** (the duplicate-charge signature) never enter the confidence scorer — they're structurally routed straight to `ESCALATE`, since a probability score isn't an appropriate gate for something that likely needs a refund decision rather than a ledger update.

## Data model

`audit_log` (SQLite):

```
id, ref_id, amount, rail, action, confidence, tier,
time_gap_seconds, has_close_sibling, reasoning, decided_at
```

Every row in this table is a complete, standalone justification for a decision — enough to answer "why did the system do this" without needing to re-run the pipeline.

## Why logistic regression, specifically

The decision this model makes is binary in outcome (auto-resolve or don't) but the honest input is continuous (how confident are we, based on how unusual this pattern is). A hand-coded threshold on `time_gap_seconds` alone was the first version and it broke on the borderline 10–30 minute band — some of those are genuinely dropped webhooks that took a while to notice, some are early signs of a duplicate. A model that outputs a probability, trained on labeled synthetic cases that encode the actual domain rule, handles that ambiguity gracefully instead of picking an arbitrary cutoff.

## Scaling notes (out of scope for the buildathon build, noted for completeness)

- Real deployments would match against a settlement file rather than a live ledger, and would need idempotency guards so a webhook retry doesn't get double-counted as a new mismatch.
- The confidence scorer's synthetic training labels should eventually be replaced with actual outcomes from `DRAFT_FOR_REVIEW` human decisions — a feedback loop, not a fixed model.
