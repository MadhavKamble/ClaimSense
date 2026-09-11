# Project Context — Claims Intelligence Assistant

This file is for Claude Code (and for you, the developer) to understand the full picture of this project before touching any code: what it is, why every design decision was made, what's already built and verified, and what's genuinely left to do. Read this fully before making changes.

---

## 1. What this project is, and why it exists

This is a portfolio project built for an on-campus placement interview at **EXL Service** (Associate Developer, Band B1, Digital Engineering track). It was designed by reverse-engineering EXL's actual job description line by line — it is not a generic "cool AI project," it's a deliberate response to specific JD requirements.

**The core idea:** an insurance company receives claims (car accidents, water damage, hospital visits, etc.). A human currently reads each one, classifies it, checks policy coverage, and decides whether to approve/escalate/request more info. This project builds an AI-assisted first pass of that workflow — not a replacement for humans, a pre-sort layer in front of them.

**Direct JD lines this maps to:**
- "Applying AI, ML, and modern data engineering techniques to solve real-world business problems" → the whole pipeline
- "prompt engineering, integrating LLM APIs... text generation, summarization" → `src/classify.py`
- "Conversational AI, NLP/NLU modelling" → the classification + RAG Q&A layer
- "translate business requirements to optimum automation solutions" → `src/routing.py` (the hybrid rules+AI engine)
- "Establishing and maintaining data governance policies, ensuring data integrity, security, and compliance" → `src/validation.py` + `src/governance.py`

**Important context on scope:** the developer building this has an MTech in Data Engineering, but a deliberate decision was made NOT to force data-engineering tooling (Airflow, Spark, Kafka) into this project, because (a) the JD doesn't ask for it, (b) the project's scale (80 synthetic claims) doesn't justify it, and (c) claiming tools you can't defend under questioning is worse than not having them. Instead, the project demonstrates **general engineering rigor** (validated pipelines, tests, config-driven design, structured logging) which is valuable regardless of role, without overclaiming a specific discipline. **Do not suggest adding Airflow/Spark/Kafka/dbt or similar heavy DE orchestration tools — this has already been explicitly considered and rejected as disproportionate to the project's scope.**

---

## 2. Architecture — the full picture

```
data/claims.csv (raw synthetic claims, 80 total, 10% deliberately ambiguous)
        │
        ▼
Stage 1: INGEST          src/pipeline.py :: stage_ingest()
        │                 reads raw CSV rows
        ▼
Stage 2: VALIDATE         src/validation.py
        │                 Pydantic schema check — bad data (negative amounts,
        │                 invalid policy types, malformed text) is quarantined
        │                 with a logged reason, never silently dropped or
        │                 silently processed
        ▼
Stage 3: LOAD              src/db.py
        │                 SQLite — two tables: `claims` (structured data +
        │                 AI output fields) and `audit_log` (every AI decision,
        │                 PII-redacted before it's ever written)
        ▼
Stage 4: GENAI PROCESSING
        │  a) Classification — src/classify.py
        │     LLM reads claim_description, returns structured JSON:
        │     predicted_type, urgency, confidence, reasoning
        │  b) Summarization — src/classify.py
        │     LLM condenses long descriptions into 1 sentence
        │  c) RAG Policy Q&A — src/rag.py
        │     chunk (5 policy docs) → embed → store in ChromaDB →
        │     retrieve top-k relevant chunks for a question →
        │     generate an answer GROUNDED in those chunks (not the
        │     model's general knowledge — this prevents hallucinated
        │     coverage terms)
        ▼
Stage 5: HYBRID ROUTING     src/routing.py
        │                 Pure deterministic logic, NOT an AI call:
        │                 - confidence < 0.6 → Request-Info
        │                 - claim_amount > per-policy-type threshold → Escalate
        │                 - urgency == High → Escalate
        │                 - otherwise → Auto-Approve
        │                 This mimics how an RPA platform (UiPath/Blue Prism)
        │                 would combine deterministic rules with an AI
        │                 confidence signal — auditable, not a black box.
        ▼
Cross-cutting: GOVERNANCE    src/governance.py
        │                 Every audit log write passes through PII redaction
        │                 first (regex-based: phone numbers, SSN-like
        │                 patterns, customer names) — audit logs should never
        │                 contain raw personal data.
        ▼
Stage 6: EVALUATE            src/evaluate.py + src/calibration.py
                          a) evaluate.py: measures classification accuracy
                             against ground truth (the synthetic data's
                             true policy_type — this is NOT cheating, it's
                             how you validate a classifier when you control
                             data generation)
                          b) calibration.py: tests whether the LLM's
                             SELF-REPORTED confidence score can be trusted —
                             buckets claims by stated confidence, checks
                             actual accuracy per bucket, flags overconfidence
                             if the gap is large. This was built specifically
                             to fix a previously-identified weakness (an LLM's
                             self-reported confidence is not a calibrated
                             probability by default — this module tests
                             whether that's actually a problem here, with data).
        │
        ▼
Streamlit Dashboard          app.py
                          3 tabs: Claims Intake (run pipeline, view results),
                          Policy Q&A (chat interface backed by RAG),
                          Metrics (volume, auto-approval rate, avg confidence)
```

---

## 3. File-by-file map

| File | Purpose | Status |
|---|---|---|
| `config.yaml` / `config.py` | Every tunable value (thresholds, model names, paths) in one place | ✅ Built, tested |
| `data/generate_data.py` | Synthetic claims generator (Faker). Produces 80 claims, 10% deliberately worded ambiguously (e.g. water-damage language overlapping Home/Renters) to create real, discussable classifier failure modes instead of artificial 100% accuracy | ✅ Built, verified working |
| `data/policy_docs/*.md` | 5 policy documents (Auto, Home, Health, Travel, Renters) — the RAG knowledge base | ✅ Written |
| `src/validation.py` | Pydantic schema — validates claims before they enter the pipeline, quarantines bad data with a logged reason | ✅ Built, tested |
| `src/db.py` | SQLite schema (`claims`, `audit_log` tables), CRUD helpers, example SQL queries for interview practice | ✅ Built, verified working |
| `src/classify.py` | LLM classification + summarization. Deliberately requests structured JSON output (not free text) so it's reliably parseable downstream | ✅ Built — **NOT yet run against a real API key** |
| `src/rag.py` | Full RAG pipeline: chunk → embed (OpenAI embeddings) → store (ChromaDB) → retrieve → generate | ✅ Built — **NOT yet run against a real API key** |
| `src/routing.py` | Hybrid rules+AI routing engine, pure Python logic, no AI call | ✅ Built, tested |
| `src/governance.py` | PII redaction (regex-based) + governed audit logging wrapper | ✅ Built, tested |
| `src/evaluate.py` | Measures classification accuracy against ground truth, per-class breakdown | ✅ Built — **NOT yet run with real classification output** |
| `src/calibration.py` | Tests whether the LLM's self-reported confidence is trustworthy (calibration analysis) | ✅ Built, tested (including a test proving it correctly catches a deliberately overconfident synthetic model) |
| `src/pipeline.py` | Orchestrates all stages end to end: Ingest → Validate → Load → Process → Route → Evaluate | ✅ Built, verified working (stages 1-3 confirmed; stages 4-6 need a real API key to execute) |
| `src/logger.py` | Structured logging (console + file), replaces print statements | ✅ Built, tested |
| `app.py` | Streamlit dashboard — 3 tabs | ✅ Built — **NOT yet run against a real API key** |
| `tests/` | 21 automated tests (routing, governance, validation, calibration) | ✅ All passing |
| `Dockerfile` / `.dockerignore` | Containerization | ✅ Built |

---

## 4. Key design decisions Claude Code should NOT casually "improve" away

These were deliberate choices made after explicit discussion — if you (Claude Code) see something that looks like it could be "cleaned up," check with the developer first, because it's probably intentional:

1. **Confidence is self-reported by the LLM, not a traditional calibrated probability.** This is a known, deliberate limitation — `calibration.py` exists specifically to TEST this empirically rather than hide it. Don't "fix" this by inventing a fake calibration method; the honest framing is the point.
2. **10% of the synthetic data is deliberately ambiguous/messy.** Don't clean this up to make the classifier look more accurate — the ambiguous claims exist on purpose to create real failure modes worth discussing in an interview.
3. **No orchestration tools (Airflow/Spark/Kafka).** Already discussed and rejected as disproportionate to project scope — see Section 1.
4. **Routing logic is deliberately NOT an AI call.** It's plain Python if/else logic combining rules with the AI's confidence score. This is intentional — the project's argument is that high-stakes automated decisions should combine deterministic, auditable rules with AI signals, not be a black box.
5. **SQLite, not PostgreSQL.** Deliberate simplicity for a demo project — documented in the README as a stated production trade-off, not an oversight.

---

## 5. What's genuinely left to do (in order)

1. **Set up `.env` with a real OpenAI (or Anthropic) API key** — copy from `.env.example`
2. **Run `python data/generate_data.py`** — regenerates the synthetic claims (already done once, but do it fresh locally)
3. **Run `python src/rag.py --build`** — indexes the 5 policy documents into ChromaDB. This is the first step that needs a real API key (for embeddings).
4. **Run `python -m src.pipeline`** — this is the big moment: the first time the classification, summarization, routing, evaluation, and calibration analysis all run against REAL LLM output instead of just being structurally tested. Expect this to surface small surprises (weird LLM outputs, edge cases) — that's normal and good, debug them live, they become interview talking points.
5. **Record the real results** — overall accuracy, per-class accuracy, calibration verdict — and fill in the README's currently-empty "## Results" section with actual numbers.
6. **Run `streamlit run app.py`** and manually click through all 3 tabs — actually ask the RAG chatbot a policy question and read the real answer.
7. **Run `pytest tests/ -v`** locally to reconfirm all 21 tests still pass in your real environment (they passed in the sandbox; confirm again locally since environments can differ).
8. **Deploy to Streamlit Community Cloud** (or similar) for a live demo link.
9. **Rehearse the 60-second verbal pitch** (see Section 6 below) out loud, multiple times.

---

## 6. Interview framing (for context — not a coding task, but Claude Code should know this if asked to help with talking points)

**60-second pitch:** *"I built a claims triage assistant that simulates how an insurance company could use AI to speed up processing. It takes a raw claim, uses an LLM to classify its type and urgency and summarize it, answers policy coverage questions using RAG — so answers are grounded in actual policy documents instead of the AI guessing — and routes the claim using a hybrid rules-plus-AI-confidence engine, similar to how RPA platforms work. Every decision gets logged to an audit trail with personal data redacted first, since that's a real compliance requirement. I also built calibration analysis to test whether the AI's confidence scores can actually be trusted, rather than assuming they can."*

**Known weak points to be ready for (own them, don't hide them):**
- RAG-as-a-pattern is common in portfolios now — the differentiator is the claims-triage framing and the routing/governance layers around it, not RAG alone
- Confidence calibration — be ready to state the real measured verdict once you've run it
- SQLite is a demo simplification, not a production choice — say so if asked

---

## 7. Constraints for whoever (human or Claude Code) works on this next

- This project was built in a sandboxed environment with no access to `api.openai.com` — all GenAI-calling code (`classify.py`, `rag.py`, `app.py`) was structurally built and verified for correct wiring/imports/logic, but has genuinely never executed against a real model. Treat first real runs as "first run," not "rerun."
- All non-AI logic (`routing.py`, `governance.py`, `validation.py`, `calibration.py`, `db.py`) is fully tested and verified working — trust this code, focus debugging effort on the AI-calling layers if something breaks.

---

## 8. Git & Commit Policy — IMPORTANT, applies every session

**Claude Code must NEVER run `git init`, `git add`, `git commit`, `git push`, or any other git command that changes repo state — not once, not even for "small" or "obvious" changes.**

The developer wants sole authorship of the commit history for credibility — every commit needs to actually come from them running the command themselves, not from an AI silently committing on their behalf.

Instead, whenever a chunk of work is complete and would normally be commit-worthy, Claude Code should:
1. Stop and summarize what changed and why
2. Suggest a clear, conventional commit message
3. Wait for the developer to review, and let THEM run `git add` / `git commit` / `git push` manually

This applies to every commit for the entire lifetime of this project, not just the first one. If Claude Code is ever unsure whether something counts as "commit-worthy," it should err on the side of stopping and asking rather than proceeding.
