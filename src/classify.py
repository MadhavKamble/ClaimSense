"""
GenAI Layer — Day 4 build.

Two LLM-powered functions:
  1. classify_claim()   -> structured JSON: predicted_type, urgency, confidence
  2. summarize_claim()  -> 1-2 line plain-English summary

Design notes for your interview pitch:
- We ask for STRUCTURED JSON output (not free text) so it can be reliably
  parsed and stored in SQL — this is a deliberate prompt engineering choice,
  not an accident. Mention this explicitly if asked "how did you make the
  LLM output usable downstream."
- Confidence score is self-reported by the model via the prompt. Flag clearly
  in interviews that this is a heuristic, not a calibrated probability —
  a good production version would validate this against labeled data.
"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

VALID_TYPES = ["Auto", "Home", "Health", "Travel", "Renters"]

CLASSIFY_SYSTEM_PROMPT = f"""You are a claims triage assistant for an insurance company.
Given a claim description, classify it and return ONLY valid JSON with this exact shape:

{{
  "predicted_type": one of {VALID_TYPES},
  "urgency": one of ["Low", "Medium", "High"],
  "confidence": a number between 0 and 1 representing how confident you are,
  "reasoning": a one-sentence explanation of why
}}

Urgency guide:
- High: injury involved, immediate safety risk, or time-sensitive (e.g. uninhabitable home, hospitalization)
- Medium: property damage requiring prompt attention but no immediate danger
- Low: minor/cosmetic damage, no urgency

Return ONLY the JSON object, no other text."""

SUMMARIZE_SYSTEM_PROMPT = """You are summarizing insurance claim descriptions for a claims
adjuster who needs to scan many claims quickly. Produce a single concise sentence
(max 25 words) capturing what happened and what's being claimed. No preamble, just the sentence."""


def classify_claim(claim_description: str) -> dict:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
            {"role": "user", "content": claim_description},
        ],
        temperature=0,  # deterministic-ish output for a classification task
        response_format={"type": "json_object"},
    )
    result = json.loads(response.choices[0].message.content)

    # Defensive validation — never trust raw LLM output blindly downstream.
    # This is worth mentioning in interviews as a hallucination-mitigation step.
    if result.get("predicted_type") not in VALID_TYPES:
        result["predicted_type"] = "Unclassified"
        result["confidence"] = 0.0

    return result


def summarize_claim(claim_description: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
            {"role": "user", "content": claim_description},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def process_claim(claim_id: str, claim_description: str) -> dict:
    """Convenience wrapper used by app.py — runs both steps and returns a dict
    ready to pass into db.update_claim_ai_fields()."""
    classification = classify_claim(claim_description)
    summary = summarize_claim(claim_description)

    return {
        "predicted_type": classification["predicted_type"],
        "urgency": classification["urgency"],
        "classification_confidence": classification["confidence"],
        "summary": summary,
    }


if __name__ == "__main__":
    # Quick manual test — run `python src/classify.py` after setting your API key
    sample = (
        "Car was broken into overnight, stereo system and personal belongings "
        "stolen from downtown parking lot. Filed police report #482913."
    )
    print("Classification:", classify_claim(sample))
    print("Summary:", summarize_claim(sample))
