"""
Hybrid Routing Engine — Day 5 build. This is your RPA/hyperautomation
talking point: a deterministic rules layer combined with AI confidence,
mimicking what an RPA platform (UiPath/Blue Prism) would do when wired
up to an AI classification step.

Routing decision logic (deliberately simple and explainable — a real
claims team needs to be able to audit WHY a decision was made, not just
trust a black box):

  - confidence < 0.6                  -> Request-Info  (AI isn't sure, ask claimant for more detail)
  - claim_amount > threshold(policy)  -> Escalate       (high value, needs human sign-off regardless of confidence)
  - urgency == "High"                 -> Escalate       (safety/time-sensitive, always human-reviewed)
  - otherwise                         -> Auto-Approve

Run: python -m src.routing   (needs the project root on the path, since this
module now reads its thresholds from config.yaml via config.CONFIG)
"""

from config import CONFIG

# Amount thresholds above which a claim always gets escalated for human review,
# regardless of AI confidence. Tuned per policy type since claim sizes differ a lot.
# Read from config.yaml so changing a threshold doesn't require touching this file.
ESCALATION_THRESHOLDS = CONFIG["routing"]["escalation_thresholds"]

CONFIDENCE_FLOOR = CONFIG["routing"]["confidence_floor"]


def route_claim(policy_type: str, claim_amount: float, urgency: str, confidence: float) -> dict:
    """Returns the routing decision plus a human-readable reason —
    the reason string is what gets written to the audit log."""

    if confidence < CONFIDENCE_FLOOR:
        return {
            "decision": "Request-Info",
            "reason": f"AI classification confidence ({confidence:.2f}) below threshold ({CONFIDENCE_FLOOR}); needs clarification from claimant.",
        }

    threshold = ESCALATION_THRESHOLDS.get(policy_type, 5000)
    if claim_amount > threshold:
        return {
            "decision": "Escalate",
            "reason": f"Claim amount (${claim_amount:,.2f}) exceeds auto-approval threshold (${threshold:,.2f}) for {policy_type} claims.",
        }

    if urgency == "High":
        return {
            "decision": "Escalate",
            "reason": "Urgency flagged as High — routed to human reviewer regardless of amount/confidence.",
        }

    return {
        "decision": "Auto-Approve",
        "reason": f"Confidence ({confidence:.2f}) and claim amount within auto-approval bounds for {policy_type}.",
    }


if __name__ == "__main__":
    # Quick manual test
    print(route_claim("Auto", 1200, "Low", 0.85))    # -> Auto-Approve
    print(route_claim("Home", 20000, "Medium", 0.9))  # -> Escalate (amount)
    print(route_claim("Health", 500, "High", 0.9))    # -> Escalate (urgency)
    print(route_claim("Travel", 300, "Low", 0.4))     # -> Request-Info (low confidence)
