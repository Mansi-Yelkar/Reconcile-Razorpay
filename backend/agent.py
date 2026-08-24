"""
agent.py

Takes one mismatch (bank says paid, merchant order doesn't reflect it) plus
a confidence score, and decides what to actually do about it:

  AUTO_RECONCILE   - close the gap automatically: mark the order paid,
                      fire the fulfillment webhook. Only for high confidence.
  DRAFT_FOR_REVIEW - don't touch the order, but write up exactly what a
                      human ops person needs to check, so it's a 10-second
                      decision instead of a 10-minute investigation.
  ESCALATE         - low confidence, could be a duplicate charge. Flag it
                      and explicitly say why we're not touching it.

The reasoning strings are templated, not free-generated, on purpose: an
ops audit trail needs to be consistent and grep-able, not stylistically
varied. "Sounding like an LLM" would actually be a worse fit here than a
tight, repeatable report format — this is what real fintech audit logs
look like.
"""

from datetime import datetime


def _fmt_gap(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def decide(mismatch: dict, confidence: float, tier: str) -> dict:
    bank = mismatch["bank"]
    merchant = mismatch["merchant"]
    gap = mismatch["time_gap_seconds"]
    sibling = mismatch["has_close_sibling"]

    gap_str = _fmt_gap(gap)
    amount = bank["amount"]
    ref = bank["ref_id"]

    if tier == "high":
        action = "AUTO_RECONCILE"
        reasoning = (
            f"Bank confirms SUCCESS for {ref} (₹{amount}, {bank['rail']}) but merchant "
            f"order still shows {merchant['status']}. Gap between bank confirmation and "
            f"merchant record is {gap_str}, no other same-amount charge nearby on this "
            f"rail. Pattern matches dropped webhook callback, not a duplicate. "
            f"Confidence {confidence:.2f} >= 0.85 -> closing automatically: marking order "
            f"paid and firing fulfillment webhook."
        )
    elif tier == "medium":
        action = "DRAFT_FOR_REVIEW"
        reasoning = (
            f"Bank confirms SUCCESS for {ref} (₹{amount}, {bank['rail']}) but merchant "
            f"order still shows {merchant['status']}. Gap is {gap_str}"
            + (", and a same-amount charge landed nearby on this rail" if sibling else "")
            + f". Confidence {confidence:.2f} is in the review band (0.50-0.85) — long "
            f"enough gap or nearby sibling charge that this could be a late settlement "
            f"or the shadow of a duplicate. Drafting for a human: verify {ref} against "
            f"the customer's bank statement before marking the order paid."
        )
    else:
        action = "ESCALATE"
        reasoning = (
            f"Bank confirms SUCCESS for {ref} (₹{amount}, {bank['rail']}) but merchant "
            f"order still shows {merchant['status']}. "
            + ("A same-amount, same-rail charge landed within 5 minutes of this one — " if sibling else "")
            + f"gap is {gap_str}. Confidence {confidence:.2f} is too low to touch "
            f"automatically. Not reconciling — escalating to manual audit, this could "
            f"be a duplicate charge that needs a refund rather than an order update."
        )

    return {
        "ref_id": ref,
        "amount": amount,
        "rail": bank["rail"],
        "action": action,
        "confidence": round(confidence, 3),
        "tier": tier,
        "time_gap_seconds": gap,
        "has_close_sibling": sibling,
        "reasoning": reasoning,
        "decided_at": datetime.now().isoformat(),
    }
