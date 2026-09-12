# ClaimSense

An AI-powered claims triage system that validates, classifies, summarizes, and routes insurance claims using a hybrid rules+AI engine — with RAG-based policy Q&A, full audit logging, PII redaction, automated tests, and measured accuracy against ground truth.

Built to demonstrate two things at once: **GenAI application development** (LLM classification, prompt engineering, RAG) and **engineering rigor** (validated pipeline stages, config-driven behavior, structured logging, automated tests, containerization) — not just a notebook that happens to call an LLM.

## Problem

Insurance claims teams manually read, classify, and route every incoming claim. This is slow, inconsistent, and doesn't scale. This project simulates an AI-assisted triage layer that a claims team could sit on top of their existing systems — built the way a real system would be built, not just demoed.

## Architecture

```
data/claims.csv (raw claims)
        |
        v
  Stage 1: Ingest        src/pipeline.py :: stage_ingest
        |
        v
  Stage 2: Validate       src/validation.py -- Pydantic schema check
                           (bad data quarantined, not silently dropped or processed)
        |
        v
  Stage 3: Load            src/db.py -- SQLite: claims + audit_log tables
        |
        v
  Stage 4: GenAI Processing
     - Classification (type, urgency, confidence)   src/classify.py
     - Summarization                                 src/classify.py
     - RAG policy Q&A (chunk -> embed -> retrieve -> generate)   src/rag.py
        |
        v
  Stage 5: Hybrid Routing    src/routing.py
     rules + AI confidence -> auto-approve / escalate / request-info
        |
        v
  Governance (cross-cutting)   src/governance.py
     PII redaction before every audit log write
        |
        v
  Stage 6: Evaluate           src/evaluate.py
     accuracy vs. ground truth, per-class breakdown, routing distribution
        |
        v
  Streamlit Dashboard (app.py)
```

Every stage is independently runnable and independently testable. A failure on one claim during Stage 4 is logged and the claim is flagged — it does not crash the whole pipeline run (see `stage_process_and_route` in `src/pipeline.py`).

## Engineering practices included (and why)

| Practice | File(s) | Why it's here, not just for show |
|---|---|---|
| Config-driven behavior | `config.yaml`, `config.py` | Every threshold, model name, and path lives in one file — changing the confidence floor from 0.6 to 0.7 doesn't require touching business logic |
| Schema validation | `src/validation.py` | Bad data (negative amounts, invalid policy types, malformed descriptions) is caught and quarantined before it reaches the AI pipeline — a direct, working answer to "data integrity" |
| Structured logging | `src/logger.py` | Timestamped, leveled logs to console + file, not disappearing print statements — necessary for anything meant to run unattended |
| Automated tests | `tests/` (16 tests, all passing) | Pure-logic components (routing, PII redaction, validation) are tested with no external dependency — fast, deterministic, run on every change |
| Ground-truth evaluation | `src/evaluate.py` | The synthetic data carries a true `policy_type`; classification accuracy is measured against it, per-class, not just claimed |
| Confidence calibration analysis | `src/calibration.py` | Previously an admitted weakness ("confidence is self-reported, not calibrated") — now actually tested: claims are bucketed by stated confidence and checked against real accuracy in each bucket, producing a measured verdict (well-calibrated / overconfident / etc.) instead of an assumption |
| Deliberately ambiguous test data | `data/generate_data.py` | 10% of synthetic claims are worded to plausibly confuse the classifier (e.g. water-damage language that overlaps Home/Renters) — creates real, discussable failure modes instead of an artificially perfect classifier |
| Containerization | `Dockerfile`, `.dockerignore` | Runs identically anywhere, not just "on my machine" |
| Multi-stage pipeline | `src/pipeline.py` | Ingest -> Validate -> Load -> Process -> Route -> Evaluate are separate, single-responsibility stages, not one script |

## Tech Stack

- Python 3.10+
- SQLite (structured data + audit log)
- Pydantic (schema validation)
- Faker (synthetic claims data)
- An LLM API — OpenAI/Anthropic, configurable via `.env` and `config.yaml`
- ChromaDB (vector store for RAG)
- Streamlit (dashboard)
- pytest (automated tests)
- Docker

## Project Structure

```
ClaimSense/
├── README.md
├── requirements.txt
├── config.yaml                # all tunable values
├── config.py                  # config loader
├── .env.example
├── Dockerfile
├── .dockerignore
├── app.py                     # Streamlit dashboard (entry point)
├── data/
│   ├── generate_data.py       # synthetic claims generator (Faker)
│   ├── claims.csv             # generated output (not committed)
│   └── policy_docs/           # knowledge base for RAG (5 policy types)
├── src/
│   ├── logger.py               # structured logging setup
│   ├── validation.py           # Pydantic schema validation
│   ├── db.py                   # SQLite schema, init, CRUD helpers
│   ├── classify.py             # LLM classification + summarization
│   ├── rag.py                  # chunk / embed / retrieve / generate
│   ├── routing.py              # hybrid rules+AI routing engine
│   ├── governance.py           # PII redaction + governed audit logging
│   ├── evaluate.py             # accuracy measurement vs. ground truth
│   ├── calibration.py          # tests whether self-reported confidence is trustworthy
│   └── pipeline.py             # orchestrates all stages end to end
└── tests/
    ├── test_routing.py         # 6 tests
    ├── test_governance.py      # 5 tests
    ├── test_validation.py      # 5 tests
    └── test_calibration.py     # 5 tests
```

## Setup & Run

```bash
python -m venv venv
source venv/bin/activate       # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env           # add your LLM API key

python data/generate_data.py   # generates data/claims.csv
python src/rag.py --build      # indexes policy docs for RAG

python -m src.pipeline         # runs the full pipeline end to end, prints accuracy

streamlit run app.py           # launches the dashboard
```

Run tests: `pytest tests/ -v`

Run with Docker: `docker build -t claims-assistant . && docker run -p 8501:8501 --env-file .env claims-assistant`

## Results

Full pipeline run against real LLM output (`gpt-4o-mini`), 80 synthetic claims, 10% deliberately ambiguous:

**Overall classification accuracy: 91.2%** (73/80 correct), average self-reported confidence: 0.875

| Policy Type | n | Correct | Accuracy |
|---|---|---|---|
| Home | 13 | 13 | 100% |
| Auto | 19 | 19 | 100% |
| Health | 11 | 11 | 100% |
| Renters | 21 | 19 | 90.5% |
| Travel | 16 | 11 | 68.8% |

**Routing breakdown:** 36 Auto-Approve, 44 Escalate, 0 Request-Info

**Calibration verdict:** Well-calibrated (weighted error = 0.038) — the model's stated confidence closely tracks its actual accuracy, so it's reasonable to use it as a routing signal here.

**Discussion:** Travel is the clear weak spot (68.8%), which directly traces back to the deliberately ambiguous "rental car damage while traveling" claims in the synthetic data — wording that genuinely overlaps Auto and Travel policy language. Renters' 90.5% likewise reflects the intentional Home/Renters water-damage ambiguity. These aren't random errors; they're the classifier failing exactly where a human adjuster would also need judgment, which is the point of including ambiguous data in the first place.

## What I'd improve for production

- Batch/async LLM calls for throughput
- Caching repeated RAG queries
- If calibration analysis shows overconfidence (see `src/calibration.py`), switch routing decisions to use measured per-class accuracy from `evaluate.py` instead of the LLM's raw stated confidence
- Real OCR pipeline for scanned claim documents instead of synthetic text
- Proper secrets management instead of `.env`
- CI pipeline running `pytest` automatically on every push
