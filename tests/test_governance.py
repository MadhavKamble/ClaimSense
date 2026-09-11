"""
Tests for PII redaction. Run: pytest tests/
"""

from src.governance import redact_pii


def test_redacts_phone_number():
    text = "Call the customer at 555-123-4567 for follow-up."
    result = redact_pii(text)
    assert "555-123-4567" not in result
    assert "[REDACTED-PHONE]" in result


def test_redacts_ssn_like_pattern():
    text = "Customer SSN on file: 123-45-6789."
    result = redact_pii(text)
    assert "123-45-6789" not in result
    assert "[REDACTED-ID]" in result


def test_redacts_customer_name_when_provided():
    text = "John Smith called about his claim."
    result = redact_pii(text, customer_name="John Smith")
    assert "John Smith" not in result
    assert "[REDACTED-NAME]" in result


def test_leaves_non_pii_text_unchanged():
    text = "Claim CLM00042 was auto-approved due to high confidence."
    result = redact_pii(text)
    assert result == text


def test_handles_empty_string():
    assert redact_pii("") == ""
