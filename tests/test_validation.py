"""
Tests for the Pydantic validation layer. Run: pytest tests/
"""

from src.validation import validate_claims

VALID_ROW = {
    "claim_id": "CLM00001", "customer_id": "CUST1234", "policy_type": "Auto",
    "claim_amount": 1200.0, "date_filed": "2026-08-01", "status": "Filed",
    "claim_description": "Vehicle was rear-ended at a traffic signal.",
}


def test_valid_claim_passes():
    valid, quarantined = validate_claims([VALID_ROW])
    assert len(valid) == 1
    assert len(quarantined) == 0


def test_negative_amount_is_quarantined():
    bad_row = {**VALID_ROW, "claim_id": "CLM00002", "claim_amount": -500.0}
    valid, quarantined = validate_claims([bad_row])
    assert len(valid) == 0
    assert len(quarantined) == 1


def test_invalid_policy_type_is_quarantined():
    bad_row = {**VALID_ROW, "claim_id": "CLM00003", "policy_type": "Bicycle"}
    valid, quarantined = validate_claims([bad_row])
    assert len(valid) == 0
    assert len(quarantined) == 1


def test_too_short_description_is_quarantined():
    bad_row = {**VALID_ROW, "claim_id": "CLM00004", "claim_description": "short"}
    valid, quarantined = validate_claims([bad_row])
    assert len(valid) == 0
    assert len(quarantined) == 1


def test_mixed_batch_separates_correctly():
    bad_row = {**VALID_ROW, "claim_id": "CLM00005", "claim_amount": -1}
    valid, quarantined = validate_claims([VALID_ROW, bad_row])
    assert len(valid) == 1
    assert len(quarantined) == 1
