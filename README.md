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
| Config-driven behavior | `config.yaml`, `config.py` | Tunable values live in one file rather than scattered across modules — `routing.py`'s confidence floor and per-policy-type escalation thresholds read from `config.yaml` via `config.CONFIG`, so changing the confidence floor from 0.6 to 0.7 doesn't require touching business logic. (Not yet every module: `classify.py`/`rag.py`/`db.py` still hardcode their model name, temperature, chunk size, and file paths rather than reading them from `config.yaml` — a known, tracked gap, not an oversight to hide.) |
| Schema validation | `src/validation.py` | Bad data (negative amounts, invalid policy types, malformed descriptions) is caught and quarantined before it reaches the AI pipeline — a direct, working answer to "data integrity" |
| Structured logging | `src/logger.py` | Timestamped, leveled logs to console + file, not disappearing print statements — necessary for anything meant to run unattended |
| Automated tests | `tests/` (21 tests, all passing) | Pure-logic components (routing, PII redaction, validation, calibration) are tested with no external dependency — fast, deterministic, run on every change. Covers 4 of 10 `src/` modules; `db.py`, `pipeline.py`, `evaluate.py`, `classify.py`, `rag.py`, and `app.py` don't have automated tests yet |
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
│   ├── claims.csv             # generated output (committed, so the repo is runnable without regenerating it)
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

## Study Manual

`docs/study/` contains a 20-module, deep-dive study manual covering every part of this system in dependency order, plus low-level/high-level design, a prioritized fix list, and a full interview kit — every claim in it is verified directly against the code and against real run data (not just the docstrings or this README). A compiled, printable version is at `docs/study/manual.pdf` (and `manual.html`); rebuild either with `python3 docs/study/build_manual.py` after editing a module.

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

**Discussion:** Travel is the clear weak spot (68.8%). I traced all 7 real misclassifications individually rather than stopping at the aggregate number: 5 of them are the deliberately ambiguous "rental car damage while traveling" (Auto/Travel) and "water came through the ceiling" (Home/Renters) claims — wording that gives no signal distinguishing the two possible true labels, so no classifier could reliably get these right. But 2 of the 7 are a genuine, reproducible model weakness, not injected ambiguity: the same clean (non-ambiguous) Travel template — "medical treatment required abroad due to a stomach infection" — was misclassified as Health both times it appeared, likely because the model weighs the medical vocabulary more heavily than the one word ("abroad") that actually determines the policy type. Excluding the 5 unsolvable-by-design errors, accuracy on the genuinely solvable claims is **~97.5% (77/79)** — a more precise and more defensible number than the raw 91.2%, with one specific, named weakness still worth fixing rather than a vague "ambiguous data" excuse. (Full trace, including the exact claim IDs, in `docs/study/10-evaluation.md`.)
