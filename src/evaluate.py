"""
Evaluation Layer.

This directly fixes a real weakness: a claims triage system with no accuracy
numbers is a demo, not evidence of results. Since the synthetic data generator
already tags each claim with its TRUE policy_type, we can measure the
classifier's actual accuracy against ground truth — this is not optional
polish, it's what turns "I built a thing" into "I measured how well the
thing works."
"""

from src.db import get_all_claims
from src.logger import get_logger

logger = get_logger(__name__)


def evaluate_classification():
    claims = get_all_claims()
    processed = [c for c in claims if c.get("predicted_type")]

    if not processed:
        logger.warning("No processed claims to evaluate. Run the pipeline first.")
        return None

    correct = sum(1 for c in processed if c["predicted_type"] == c["policy_type"])
    accuracy = correct / len(processed)

    # Per-class breakdown — accuracy alone hides whether the model is
    # systematically worse on specific policy types (e.g. confusing
    # Renters and Home claims, which share similar vocabulary)
    per_class = {}
    for policy_type in set(c["policy_type"] for c in processed):
        class_claims = [c for c in processed if c["policy_type"] == policy_type]
        class_correct = sum(1 for c in class_claims if c["predicted_type"] == c["policy_type"])
        per_class[policy_type] = {
            "n": len(class_claims),
            "correct": class_correct,
            "accuracy": round(class_correct / len(class_claims), 3) if class_claims else None,
        }

    avg_confidence = sum(c["classification_confidence"] for c in processed) / len(processed)

    routing_breakdown = {}
    for c in processed:
        decision = c.get("routing_decision", "Unknown")
        routing_breakdown[decision] = routing_breakdown.get(decision, 0) + 1

    results = {
        "total_evaluated": len(processed),
        "overall_accuracy": round(accuracy, 3),
        "avg_confidence": round(avg_confidence, 3),
        "per_class_accuracy": per_class,
        "routing_breakdown": routing_breakdown,
    }

    logger.info(f"Evaluation results: {results}")
    return results


if __name__ == "__main__":
    results = evaluate_classification()
    if results:
        print(f"\nOverall accuracy: {results['overall_accuracy']:.1%} ({results['total_evaluated']} claims)")
        print(f"Avg classification confidence: {results['avg_confidence']:.2f}")
        print("\nPer-class accuracy:")
        for ptype, stats in results["per_class_accuracy"].items():
            print(f"  {ptype}: {stats['accuracy']:.1%} ({stats['correct']}/{stats['n']})")
        print("\nRouting breakdown:", results["routing_breakdown"])
