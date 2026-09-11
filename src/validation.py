"""
Data Validation Layer.

Why this exists: real data is never as clean as what you generated yourself.
Before any claim enters the pipeline, it should be validated against a strict
schema — wrong types, missing fields, out-of-range values should be caught
and quarantined HERE, not discovered three steps downstream when the LLM
call fails or the routing engine gets a garbage claim_amount.

This is a direct, honest answer to the JD's "ensuring data integrity" line —
not a buzzword, an actual validation gate.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator

VALID_POLICY_TYPES = {"Auto", "Home", "Health", "Travel", "Renters"}
VALID_STATUSES = {"Filed", "Under Review", "Approved", "Rejected", "Escalated"}


class ClaimRecord(BaseModel):
    claim_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    policy_type: str
    claim_amount: float = Field(gt=0, description="Claim amount must be positive")
    date_filed: date
    status: str
    claim_description: str = Field(min_length=10, description="Description too short to be meaningful")
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None

    @field_validator("policy_type")
    @classmethod
    def policy_type_must_be_valid(cls, v):
        if v not in VALID_POLICY_TYPES:
            raise ValueError(f"policy_type '{v}' not in {VALID_POLICY_TYPES}")
        return v

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v):
        if v not in VALID_STATUSES:
            raise ValueError(f"status '{v}' not in {VALID_STATUSES}")
        return v


def validate_claims(raw_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Splits raw rows into (valid, quarantined). Quarantined rows carry
    the validation error so it's clear WHY they were rejected — never
    silently drop bad data, always leave a trail."""
    valid, quarantined = [], []

    for row in raw_rows:
        try:
            validated = ClaimRecord(**row)
            valid.append(validated.model_dump(mode="json"))
        except Exception as e:
            quarantined.append({**row, "_validation_error": str(e)})

    return valid, quarantined


if __name__ == "__main__":
    # Quick manual test: one good record, one bad (negative amount), one bad (invalid policy_type)
    test_rows = [
        {
            "claim_id": "CLM00001", "customer_id": "CUST1234", "policy_type": "Auto",
            "claim_amount": 1200.0, "date_filed": "2026-08-01", "status": "Filed",
            "claim_description": "Vehicle was rear-ended at a traffic signal.",
        },
        {
            "claim_id": "CLM00002", "customer_id": "CUST5678", "policy_type": "Auto",
            "claim_amount": -500.0, "date_filed": "2026-08-01", "status": "Filed",
            "claim_description": "Invalid negative amount test.",
        },
        {
            "claim_id": "CLM00003", "customer_id": "CUST9999", "policy_type": "Bicycle",
            "claim_amount": 100.0, "date_filed": "2026-08-01", "status": "Filed",
            "claim_description": "Invalid policy type test.",
        },
    ]
    good, bad = validate_claims(test_rows)
    print(f"Valid: {len(good)}, Quarantined: {len(bad)}")
    for r in bad:
        print(" -", r["claim_id"], "->", r["_validation_error"].splitlines()[0])
