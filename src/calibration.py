"""
Confidence Calibration Analysis.

This directly fixes the previously-documented weakness: "the classification
confidence score is self-reported by the LLM, not a calibrated probability."

Instead of just admitting that and moving on, we TEST it. A well-calibrated
confidence score should mean: among all claims where the model said "0.9
confidence," roughly 90% should actually be correct. If claims the model
rated 0.9 are only correct 60% of the time, the model is systematically
overconfident — and now we have a measured number that says so, instead of
an assumption either way.

This is the standard technique used to evaluate any classifier's confidence
scores (calibration curves / reliability diagrams), applied here to an LLM's
self-reported confidence instead of a traditional model's softmax output.
"""

from src.db import get_all_claims
from src.logger import get_logger

logger = get_logger(__name__)

# Confidence buckets — standard calibration analysis bucketing
BUCKETS = [
    (0.9, 1.01, "0.9-1.0 (very confident)"),
    (0.7, 0.9, "0.7-0.9 (confident)"),
    (0.5, 0.7, "0.5-0.7 (uncertain)"),
    (0.0, 0.5, "0.0-0.5 (low confidence)"),
]


def analyze_calibration_from_claims(claims: list[dict]):
    """Pure function — takes a list of claim dicts, no DB dependency. This is
    what makes it unit-testable without spinning up a database or mocking one."""
    processed = [c for c in claims if c.get("predicted_type") and c.get("classification_confidence") is not None]

    if not processed:
        return None

    results = []
    for low, high, label in BUCKETS:
        bucket_claims = [
            c for c in processed
            if low <= c["classification_confidence"] < high
        ]
        if not bucket_claims:
            results.append({"bucket": label, "n": 0, "avg_stated_confidence": None, "actual_accuracy": None, "gap": None})
            continue

        correct = sum(1 for c in bucket_claims if c["predicted_type"] == c["policy_type"])
        actual_accuracy = correct / len(bucket_claims)
        avg_stated_confidence = sum(c["classification_confidence"] for c in bucket_claims) / len(bucket_claims)
        gap = avg_stated_confidence - actual_accuracy  # positive = overconfident, negative = underconfident

        results.append({
            "bucket": label,
            "n": len(bucket_claims),
            "avg_stated_confidence": round(avg_stated_confidence, 3),
            "actual_accuracy": round(actual_accuracy, 3),
            "gap": round(gap, 3),
        })

    total_n = sum(r["n"] for r in results)
    if total_n > 0:
        weighted_error = sum(abs(r["gap"]) * r["n"] for r in results if r["gap"] is not None) / total_n
    else:
        weighted_error = None

    verdict = _interpret(results, weighted_error)

    return {"buckets": results, "weighted_calibration_error": round(weighted_error, 3) if weighted_error is not None else None, "verdict": verdict}


def analyze_calibration():
    """Wrapper used by the app/pipeline — fetches claims from the DB, then
    delegates to the pure function above."""
    claims = get_all_claims()
    result = analyze_calibration_from_claims(claims)
    if result is None:
        logger.warning("No processed claims to analyze. Run the pipeline first.")
        return None
    logger.info(f"Calibration analysis: weighted error = {result['weighted_calibration_error']}")
    return result


def _interpret(results: list[dict], weighted_error: float | None) -> str:
    if weighted_error is None:
        return "Not enough data to assess calibration."
    if weighted_error < 0.05:
        return "Well-calibrated: stated confidence closely tracks actual accuracy."
    if weighted_error < 0.15:
        return "Moderately calibrated: some gap between stated confidence and actual accuracy — usable as a rough signal, not a precise probability."

    overconfident_buckets = [r for r in results if r["gap"] and r["gap"] > 0.1]
    direction = "overconfident" if overconfident_buckets else "underconfident"
    return f"Poorly calibrated ({direction}): stated confidence should NOT be trusted as a real probability — treat as a coarse signal only, and consider using actual per-class accuracy (from evaluate.py) instead for routing decisions."


if __name__ == "__main__":
    results = analyze_calibration()
    if results:
        print("\nConfidence Calibration Report")
        print("=" * 70)
        print(f"{'Bucket':<28}{'N':<6}{'Stated Conf.':<15}{'Actual Acc.':<14}{'Gap':<8}")
        for r in results["buckets"]:
            if r["n"] == 0:
                print(f"{r['bucket']:<28}{'0':<6}{'--':<15}{'--':<14}{'--':<8}")
            else:
                print(f"{r['bucket']:<28}{r['n']:<6}{r['avg_stated_confidence']:<15}{r['actual_accuracy']:<14}{r['gap']:<8}")
        print("=" * 70)
        print(f"Weighted calibration error: {results['weighted_calibration_error']}")
        print(f"Verdict: {results['verdict']}")
