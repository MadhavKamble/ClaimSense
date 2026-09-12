"""
Governance Layer — Day 6 build.

Almost no other fresher candidate will have this section, since it maps to
a JD line that's easy to skip: "Establishing and maintaining data governance
policies, ensuring data integrity, security, and compliance with regulations."

Two responsibilities:
  1. redact_pii()      -> strips names/phone numbers before anything is written
                           to the audit log (audit logs are often over-shared
                           internally, so they should never contain raw PII)
  2. audit-friendly wrapper around db.log_audit_event() that enforces redaction
     BEFORE the write happens, not as an afterthought.
"""

import re

from src.db import log_audit_event

# Simple regex-based redaction. In interviews, be upfront that this is a
# fast/cheap first pass — a production system would likely combine this with
# an LLM-based or NER-based PII detector to catch names/patterns that regex
# misses (e.g. names embedded mid-sentence in free text).
PHONE_PATTERN = re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
SSN_LIKE_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def redact_pii(text: str, customer_name: str | None = None) -> str:
    """Redacts phone numbers, SSN-like patterns, and (if provided) the known
    customer name from a string before it's safe to log or display."""
    if not text:
        return text

    redacted = PHONE_PATTERN.sub("[REDACTED-PHONE]", text)
    redacted = SSN_LIKE_PATTERN.sub("[REDACTED-ID]", redacted)

    if customer_name:
        # Redact the literal name if it appears in free text (e.g. claim descriptions
        # that mention the claimant's name directly). Word boundaries (\b) keep this
        # from matching the name as a substring of an unrelated word (e.g. redacting
        # "Ann" inside "Annual" and corrupting it into "[REDACTED-NAME]ual").
        redacted = re.sub(r"\b" + re.escape(customer_name) + r"\b", "[REDACTED-NAME]", redacted, flags=re.IGNORECASE)

    return redacted


def log_governed_event(
    claim_id: str,
    event_type: str,
    event_detail: str,
    confidence: float | None = None,
    customer_name: str | None = None,
):
    """The ONLY function the rest of the app should call to write audit events —
    guarantees redaction happens before anything touches the database."""
    safe_detail = redact_pii(event_detail, customer_name=customer_name)
    log_audit_event(claim_id, event_type, safe_detail, confidence)


if __name__ == "__main__":
    # Run from project root as: python -m src.governance
    sample = "Customer John Smith called from 555-123-4567 regarding claim CLM00042, SSN on file 123-45-6789."
    print(redact_pii(sample, customer_name="John Smith"))
    # -> "Customer [REDACTED-NAME] called from [REDACTED-PHONE] regarding claim CLM00042, [REDACTED-ID] on file [REDACTED-ID]."
