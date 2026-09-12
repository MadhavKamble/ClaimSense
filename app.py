"""
Streamlit Dashboard — Day 6 build (presentation layer).

Three tabs:
  1. Claims Intake  -> table of all claims, run AI pipeline on unprocessed ones
  2. Policy Q&A     -> chat interface backed by the RAG pipeline
  3. Metrics        -> volume, auto-routing rate, avg confidence

Note: for a full validated pipeline run with logging, use `python -m src.pipeline`
instead — this dashboard's "Run AI pipeline" button processes claims already
loaded via that pipeline (or via `python src/db.py`), it does not re-run
ingestion/validation itself.

Run: streamlit run app.py
"""

import pandas as pd
import streamlit as st

from src.db import get_all_claims, update_claim_ai_fields, init_db
from src.classify import process_claim
from src.routing import route_claim
from src.governance import log_governed_event
from src.rag import answer_policy_question

st.set_page_config(page_title="ClaimSense", layout="wide")
st.title("ClaimSense")
st.caption("AI-powered claims triage: classification, summarization, RAG policy Q&A, and hybrid automation routing.")

tab1, tab2, tab3 = st.tabs(["Claims Intake", "Policy Q&A", "Metrics"])

# --- Tab 1: Claims Intake ---
with tab1:
    st.subheader("Incoming Claims")

    claims = get_all_claims()
    if not claims:
        st.warning("No claims loaded. Run `python data/generate_data.py` then `python src/db.py` first.")
    else:
        df = pd.DataFrame(claims)

        unprocessed = df[df["predicted_type"].isna()]
        st.write(f"{len(df)} total claims — {len(unprocessed)} not yet processed by the AI pipeline.")

        if st.button(f"Run AI pipeline on {len(unprocessed)} unprocessed claims") and len(unprocessed) > 0:
            progress = st.progress(0)
            failures = []
            for i, row in enumerate(unprocessed.itertuples()):
                # Each claim is isolated in its own try/except — mirrors
                # pipeline.py's per-claim fault isolation, so one failure
                # (a rate limit, a malformed response) can't crash the whole
                # batch or leave the run stuck mid-way with no explanation.
                try:
                    # 1. Classify + summarize
                    ai_result = process_claim(row.claim_id, row.claim_description)

                    # 2. Route (hybrid rules + AI confidence)
                    routing = route_claim(
                        policy_type=ai_result["predicted_type"],
                        claim_amount=row.claim_amount,
                        urgency=ai_result["urgency"],
                        confidence=ai_result["classification_confidence"],
                    )

                    # 3. Persist AI outputs to the claim record
                    update_claim_ai_fields(
                        row.claim_id,
                        predicted_type=ai_result["predicted_type"],
                        urgency=ai_result["urgency"],
                        classification_confidence=ai_result["classification_confidence"],
                        summary=ai_result["summary"],
                        routing_decision=routing["decision"],
                    )

                    # 4. Governed audit logging (PII-redacted before it's ever written)
                    log_governed_event(
                        claim_id=row.claim_id,
                        event_type="routing_decision",
                        event_detail=routing["reason"],
                        confidence=ai_result["classification_confidence"],
                        customer_name=getattr(row, "customer_name", None),
                    )
                except Exception as e:
                    failures.append(row.claim_id)
                    update_claim_ai_fields(row.claim_id, routing_decision="Processing-Failed")
                    log_governed_event(
                        claim_id=row.claim_id,
                        event_type="processing_failure",
                        event_detail=f"AI pipeline failed for this claim: {e}",
                        customer_name=getattr(row, "customer_name", None),
                    )

                progress.progress((i + 1) / len(unprocessed))

            if failures:
                st.warning(f"Pipeline run complete — {len(failures)} claim(s) failed and were tagged Processing-Failed: {', '.join(failures)}")
            else:
                st.success("Pipeline run complete — refresh below to see results.")
            st.rerun()

        display_cols = [
            "claim_id", "policy_type", "predicted_type", "urgency",
            "classification_confidence", "claim_amount", "routing_decision", "summary",
        ]
        st.dataframe(df[display_cols], use_container_width=True)

# --- Tab 2: Policy Q&A (RAG) ---
with tab2:
    st.subheader("Ask a policy coverage question")
    st.caption("Backed by RAG over the 5 policy documents — answers are grounded in retrieved excerpts, not the model's general knowledge.")

    question = st.text_input("e.g. 'Is water damage from a burst pipe covered under my home policy?'")
    if question:
        with st.spinner("Retrieving relevant policy excerpts and generating an answer..."):
            result = answer_policy_question(question)
        st.markdown(f"**Answer:** {result['answer']}")
        st.caption(f"Sources: {', '.join(result['sources'])}")
        with st.expander("View retrieved excerpts (for transparency)"):
            for chunk in result["retrieved_chunks"]:
                st.text(chunk)
                st.divider()

# --- Tab 3: Metrics ---
with tab3:
    st.subheader("Pipeline Metrics")
    claims = get_all_claims()
    df = pd.DataFrame(claims)

    if len(df) == 0 or df["routing_decision"].isna().all():
        st.info("Run the AI pipeline in the Claims Intake tab first to see metrics.")
    else:
        processed = df[df["routing_decision"].notna()]
        col1, col2, col3 = st.columns(3)
        col1.metric("Claims processed", len(processed))
        col2.metric("Auto-approved", f"{(processed['routing_decision'] == 'Auto-Approve').mean():.0%}")
        col3.metric("Avg. confidence", f"{processed['classification_confidence'].mean():.2f}")

        st.bar_chart(processed["routing_decision"].value_counts())
