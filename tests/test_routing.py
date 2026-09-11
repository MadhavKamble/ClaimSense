"""
Tests for the hybrid routing engine.

These test pure business logic with no external dependency (no API calls,
no database) — fast, deterministic, exactly the kind of test that should
run on every commit. Run: pytest tests/
"""

from src.routing import route_claim


def test_low_confidence_requests_info():
    result = route_claim("Auto", 1000, "Low", confidence=0.4)
    assert result["decision"] == "Request-Info"


def test_high_amount_escalates_even_with_high_confidence():
    result = route_claim("Home", 20000, "Medium", confidence=0.95)
    assert result["decision"] == "Escalate"
    assert "exceeds auto-approval threshold" in result["reason"]


def test_high_urgency_always_escalates():
    result = route_claim("Health", 100, "High", confidence=0.99)
    assert result["decision"] == "Escalate"
    assert "Urgency flagged as High" in result["reason"]


def test_normal_claim_auto_approves():
    result = route_claim("Travel", 500, "Low", confidence=0.9)
    assert result["decision"] == "Auto-Approve"


def test_unknown_policy_type_uses_default_threshold():
    # Should not crash on an unseen policy_type — falls back to the default threshold
    result = route_claim("SomeNewPolicyType", 4000, "Low", confidence=0.9)
    assert result["decision"] == "Auto-Approve"  # below default $5000 threshold


def test_confidence_floor_takes_priority_over_everything_else():
    # Even a low-amount, low-urgency claim should still get flagged if confidence is too low
    result = route_claim("Travel", 100, "Low", confidence=0.1)
    assert result["decision"] == "Request-Info"
