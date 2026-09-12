"""
Pipeline Orchestrator — Ingest -> Validate -> Process (AI) -> Route -> Evaluate

This is the difference between "a script that does everything" and "a system
with clear, separately runnable stages." Each stage has a single
responsibility, logs its own progress, and fails loudly and specifically
rather than silently continuing on bad data.

Run: python -m src.pipeline
"""

import csv
from pathlib import Path

from config import CONFIG
from src.classify import process_claim
from src.calibration import analyze_calibration
from src.db import get_all_claims, init_db, log_audit_event, update_claim_ai_fields
from src.evaluate import evaluate_classification
from src.governance import log_governed_event
from src.logger import get_logger
from src.routing import route_claim
from src.validation import validate_claims

logger = get_logger(__name__)


def stage_ingest() -> list[dict]:
    """Stage 1: read raw claims from CSV."""
    csv_path = Path(__file__).parent.parent / CONFIG["paths"]["claims_csv"]
    if not csv_path.exists():
        raise FileNotFoundError(f"{csv_path} not found — run `python data/generate_data.py` first.")

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    logger.info(f"[Ingest] Read {len(rows)} raw claim records from {csv_path.name}")
    return rows


def stage_validate(raw_rows: list[dict]) -> list[dict]:
    """Stage 2: validate against schema, quarantine anything malformed."""
    valid, quarantined = validate_claims(raw_rows)
    logger.info(f"[Validate] {len(valid)} valid, {len(quarantined)} quarantined")
    for q in quarantined:
        logger.warning(f"[Validate] Quarantined {q.get('claim_id', 'UNKNOWN')}: {q['_validation_error'].splitlines()[0]}")
    return valid


def stage_load(valid_rows: list[dict]):
    """Stage 3: load validated rows into the DB."""
    init_db(reset=True)
    from src.db import get_connection

    conn = get_connection()
    conn.executemany(
        """
        INSERT OR REPLACE INTO claims
            (claim_id, customer_id, policy_type, claim_amount, date_filed,
             status, claim_description, customer_name, customer_phone)
        VALUES (:claim_id, :customer_id, :policy_type, :claim_amount, :date_filed,
                :status, :claim_description, :customer_name, :customer_phone)
        """,
        valid_rows,
    )
    conn.commit()
    conn.close()
    logger.info(f"[Load] Loaded {len(valid_rows)} claims into database")


def stage_process_and_route():
    """Stage 4: run the AI pipeline (classify, summarize, RAG-ready) + hybrid routing on every claim."""
    claims = get_all_claims()
    logger.info(f"[Process] Running AI pipeline on {len(claims)} claims")

    for claim in claims:
        try:
            ai_result = process_claim(claim["claim_id"], claim["claim_description"])

            routing = route_claim(
                policy_type=ai_result["predicted_type"],
                claim_amount=claim["claim_amount"],
                urgency=ai_result["urgency"],
                confidence=ai_result["classification_confidence"],
            )

            update_claim_ai_fields(
                claim["claim_id"],
                predicted_type=ai_result["predicted_type"],
                urgency=ai_result["urgency"],
                classification_confidence=ai_result["classification_confidence"],
                summary=ai_result["summary"],
                routing_decision=routing["decision"],
            )

            log_governed_event(
                claim_id=claim["claim_id"],
                event_type="routing_decision",
                event_detail=routing["reason"],
                confidence=ai_result["classification_confidence"],
                customer_name=claim.get("customer_name"),
            )
        except Exception as e:
            # A failure on ONE claim should never take down the whole pipeline run —
            # log it, tag the claim, move on. This is the same philosophy an RPA
            # exception-handling workflow would use.
            logger.error(f"[Process] Failed on {claim['claim_id']}: {e}")
            update_claim_ai_fields(claim["claim_id"], routing_decision="Processing-Failed")
            log_governed_event(
                claim_id=claim["claim_id"],
                event_type="processing_failure",
                event_detail=f"AI pipeline failed for this claim: {e}",
                customer_name=claim.get("customer_name"),
            )

    logger.info("[Process] AI pipeline + routing complete")


def stage_evaluate():
    """Stage 5: measure accuracy against ground truth AND check whether the
    model's self-reported confidence can actually be trusted."""
    results = evaluate_classification()
    if results:
        logger.info(f"[Evaluate] Overall accuracy: {results['overall_accuracy']:.1%}")

    calibration = analyze_calibration()
    if calibration:
        logger.info(f"[Evaluate] Calibration verdict: {calibration['verdict']}")

    return {"accuracy": results, "calibration": calibration}


def run_pipeline():
    logger.info("=== Pipeline run started ===")
    raw_rows = stage_ingest()
    valid_rows = stage_validate(raw_rows)
    stage_load(valid_rows)
    stage_process_and_route()
    results = stage_evaluate()
    logger.info("=== Pipeline run complete ===")
    return results


if __name__ == "__main__":
    run_pipeline()
