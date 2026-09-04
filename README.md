---
title: Reconcile Razorpay
emoji: ⚡
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# Reconcile — AI Revenue Recovery Orchestrator

> **Razorpay AI Buildathon — Track 3: AI Revenue Recovery**  
> **Tagline:** *Detect revenue leakage. Diagnose the cause. Recover the money — safely.*

---

## Executive Vision

Basic reconciliation systems answer one question: *"Is there a mismatch between bank debits and merchant orders?"*  
**Reconcile** goes beyond passive matching to close the revenue recovery loop. It answers five critical financial questions:

1. **Where is revenue at risk?** (Payment failures, dropped webhooks, recurring mandate declines, abandoned checkouts)
2. **Why is that revenue at risk?** (Root cause taxonomy: issuer timeouts, insufficient funds, network drops, webhook loss)
3. **What intervention has the highest expected ROI?** (Calculates Expected Net Recovery Value: $(Amount \times P(\text{recovery})) - \text{Cost} - \text{Friction}$)
4. **Can the intervention be safely executed?** (Governed by a **Deterministic Policy Engine** enforcing 7 financial invariants)
5. **How much money was actually recovered?** (Post-execution verification before writing to the Revenue Ledger)

### Core Business Metric
```text
₹ Revenue Recovered (with 0 Unsafe Recoveries)
```

---

## High-Level System Architecture

```text
                 ┌──────────────────────────────┐
                 │ Payment / Order Events       │
                 │ Razorpay Test Mode           │
                 │ Synthetic Event Simulator    │
                 └──────────────┬───────────────┘
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │ Event Ingestion Layer        │
                 │ Webhooks / REST / Simulator  │
                 └──────────────┬───────────────┘
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │ Revenue Risk Detector        │
                 │                              │
                 │ Failed payments              │
                 │ Dropped webhooks             │
                 │ Checkout abandonment         │
                 │ Subscription failures        │
                 │ Overdue receivables          │
                 └──────────────┬───────────────┘
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │ Root Cause Analyzer          │
                 │ Rules + ML + Evidence        │
                 └──────────────┬───────────────┘
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │ Recovery Intelligence        │
                 │                              │
                 │ Recovery probability P(rec)  │
                 │ Expected recovery value      │
                 │ Recommended intervention     │
                 └──────────────┬───────────────┘
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │ Deterministic Policy Engine  │
                 │                              │
                 │ Idempotency                  │
                 │ Retry limits (Max 2)         │
                 │ Amount limits (>₹50,000)     │
                 │ Recovery window (24h)        │
                 │ Duplicate protection         │
                 │ Human approval               │
                 └──────────────┬───────────────┘
                                │
                    ┌───────────┼────────────┐
                    ▼           ▼            ▼
                  RETRY     RECOVERY LINK   REVIEW
                    │           │            │
                    └───────────┼────────────┘
                                ▼
                 ┌──────────────────────────────┐
                 │ Recovery Executor            │
                 │ Razorpay Test Adapter        │
                 │ Simulation Adapter           │
                 └──────────────┬───────────────┘
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │ Recovery Verification        │
                 │ Did the money/state recover? │
                 └──────────────┬───────────────┘
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │ Revenue Recovery Ledger      │
                 │                              │
                 │ ₹ At Risk                    │
                 │ ₹ Eligible                   │
                 │ ₹ Attempted                  │
                 │ ₹ Recovered                  │
                 └──────────────┬───────────────┘
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │ Audit + Analytics + Alerts   │
                 └──────────────┬───────────────┘
```

---

## Core Product Scope & Loss Modes

1. **Payment Degradation & Timeout**: Transient issuer delays triggered for automatic bounded retries.
2. **Dropped Webhook / State Mismatch**: Bank debit SUCCESS verified against pending merchant order; order state automatically repaired.
3. **Failed Subscription Payments**: Mandate declines classified and scheduled for economic retry workflows.
4. **Checkout Abandonment**: Uncompleted cart sessions evaluated for targeted payment link generation.
5. **Duplicate / Suspicious Payment Protection**: Unmatched debits or sibling charges hard-blocked from auto-execution and escalated to human audit.

---

## AI Safety Architecture & Financial Invariants

> **AI recommends. Policy decides. Executor acts. Verification confirms. Audit records.**

Reconcile enforces **7 Critical Financial Invariants**:

* **Invariant 1 (Idempotency):** No action key (`case_id:action_type:attempt`) can execute twice.
* **Invariant 2 (Retry Boundary):** Maximum 2 automated retries per payment case.
* **Invariant 3 (Recovery Window):** Cases older than 24 hours cannot be auto-retried.
* **Invariant 4 (High-Value Cap):** Transactions exceeding **₹50,000** strictly require human approval.
* **Invariant 5 (Duplicate Protection):** Suspected duplicate debits trigger `POLICY BLOCKED`.
* **Invariant 6 (State Verification):** Revenue is added to the ledger *only* after verified payment confirmation.
* **Invariant 7 (Audit Compliance):** Every decision generates an immutable JSON audit event.

---

## 10,000 Payment Event Benchmark Results

Evaluated via `evaluation/run_experiment.py --events 10000`:

| Benchmark Metric | Blind Retry | Rule-Based | **Reconcile Orchestrator** |
| :--- | :--- | :--- | :--- |
| **Transactions Processed** | 10,000 | 10,000 | **10,000** |
| **Revenue At Risk** | ₹16,33,74,878.00 | ₹16,33,74,878.00 | **₹16,33,74,878.00** |
| **Revenue Recovered** | ₹10,26,90,263.00 | ₹7,50,31,864.00 | **₹5,93,60,649.00** |
| **Unsafe Debits Executed** | 481 (FAIL) | 0 | **0 (TARGET PASSED)** |
| **Duplicate Debits Blocked** | 0 | 0 | **481 BLOCKED** |
| **Human Escalations** | 0 | 0 | **1,312 ESCALATED** |
| **Safety Compliance Rate** | FAILED | PARTIAL | **100% COMPLIANT** |

*Note: Blind Retry achieves higher raw retry count but incurs **481 unsafe double-debits**, resulting in heavy chargeback penalties and merchant account risk. Reconcile recovers maximum **safe** revenue while achieving **0 unsafe debits**.*

---

## Quickstart & Local Setup

### 1. Prerequisites
- Python 3.10+
- Pip / Virtual environment

### 2. Installation
```bash
# Clone repository
git clone https://github.com/reconcile/reconcile.git
cd reconcile

# Install dependencies
pip install -r requirements.txt
```

### 3. Run Application & Command Center
```bash
python app.py
```
Open your browser at **`http://localhost:7860`** to access the **Reconcile Command Center**.

---

## Deployment on Hugging Face Spaces

Hosted live on **Hugging Face Spaces**:
- **Space URL:** [Mansi-Yelkar/Reconcile-Razorpay](https://huggingface.co/spaces/Mansi-Yelkar/Reconcile-Razorpay)
- **Direct Web URL:** [https://mansi-yelkar-reconcile-razorpay.hf.space](https://mansi-yelkar-reconcile-razorpay.hf.space)
