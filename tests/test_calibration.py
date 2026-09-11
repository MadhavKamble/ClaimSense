"""
Tests for confidence calibration analysis. Run: pytest tests/

The most important test here isn't "does it run without crashing" — it's
"does it correctly detect a model that's overconfident," using synthetic
claims crafted so we KNOW the right answer in advance.
"""

from src.calibration import analyze_calibration_from_claims


def _claim(predicted_type, true_type, confidence):
    return {"predicted_type": predicted_type, "policy_type": true_type, "classification_confidence": confidence}


def test_perfectly_calibrated_model_has_near_zero_error():
    # Claims in the 0.9-1.0 bucket: exactly 90% correct -> stated confidence
    # matches actual accuracy almost perfectly -> low calibration error
    claims = (
        [_claim("Auto", "Auto", 0.95) for _ in range(9)]
        + [_claim("Auto", "Home", 0.95)]  # 1 wrong out of 10 = 90% actual accuracy
    )
    result = analyze_calibration_from_claims(claims)
    top_bucket = result["buckets"][0]  # 0.9-1.0 bucket
    assert top_bucket["n"] == 10
    assert abs(top_bucket["gap"]) < 0.1  # stated ~0.95, actual 0.9 -> small gap


def test_overconfident_model_is_correctly_flagged():
    # Claims the model rated 0.9+ confidence, but only 50% are actually correct.
    # This is a deliberately overconfident model — the test proves we catch it.
    claims = (
        [_claim("Auto", "Auto", 0.95) for _ in range(5)]  # correct
        + [_claim("Auto", "Home", 0.95) for _ in range(5)]  # wrong, but still rated 0.95 confident
    )
    result = analyze_calibration_from_claims(claims)
    top_bucket = result["buckets"][0]
    assert top_bucket["actual_accuracy"] == 0.5
    assert top_bucket["avg_stated_confidence"] == 0.95
    assert top_bucket["gap"] > 0.4  # big gap = overconfidence correctly detected
    assert "overconfident" in result["verdict"].lower() or "poorly calibrated" in result["verdict"].lower()


def test_empty_claims_returns_none():
    result = analyze_calibration_from_claims([])
    assert result is None


def test_unprocessed_claims_are_excluded():
    claims = [
        {"predicted_type": None, "policy_type": "Auto", "classification_confidence": None},
        _claim("Auto", "Auto", 0.9),
    ]
    result = analyze_calibration_from_claims(claims)
    total_n = sum(b["n"] for b in result["buckets"])
    assert total_n == 1  # only the processed claim counted


def test_well_calibrated_verdict_string():
    # All predictions correct, stated confidence matches accuracy exactly (1.0 vs 1.0) -> should say "well-calibrated"
    claims = [_claim("Auto", "Auto", 0.99) for _ in range(10)]
    result = analyze_calibration_from_claims(claims)
    assert "well-calibrated" in result["verdict"].lower()
