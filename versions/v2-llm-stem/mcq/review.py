"""Independent automatic review (Stage 8, design doc §12).

A separate request and prompt (isolated context) returns a structured verdict
only — the reviewer never modifies the question. Every boolean check must be
true AND recommendation must be ``accept`` (with a matching question_id) for the
question to become ``candidate_passed``; otherwise it is ``candidate_rejected``.
"""
from __future__ import annotations

from .client import StructuredLLMClient
from .validators import REVIEW_RESPONSE_VALIDATOR

BOOLEAN_KEYS = [
    "is_investigation_selection",
    "uses_rwd_prediction_semantics",
    "single_best_answer",
    "clinically_plausible",
    "safe_priority",
    "no_answer_leakage",
    "options_same_granularity",
    "statistically_supported",
    "synthetic_case",
    "english_quality",
]


def build_review_payload(question: dict) -> dict:
    return {
        "question_id": question["question_id"],
        "question_semantics": "most likely to be selected",
        "stem": question["stem"],
        "options": question["options"],
        "correct_option": question["correct_option"],
        "correct_answer": question["correct_answer"],
        "condition_features": question["condition_features"],
        "statistics": question["statistics"],
    }


def review_question(
    question: dict,
    client: StructuredLLMClient,
    system_prompt: str,
    *,
    reviewer_model: str | None = None,
) -> tuple[dict, dict]:
    payload = build_review_payload(question)
    resp, _meta = client.complete(
        task_type="review",
        system_prompt=system_prompt,
        user_payload=payload,
        validator=REVIEW_RESPONSE_VALIDATOR,
    )
    all_true = all(bool(resp.get(k)) for k in BOOLEAN_KEYS)
    passed = (
        all_true
        and resp.get("recommendation") == "accept"
        and resp.get("question_id") == question["question_id"]
    )
    reviewer = reviewer_model or client.model_name
    updated = dict(question)
    updated["reviewer_model"] = reviewer
    updated["automatic_review_status"] = (
        "candidate_passed" if passed else "candidate_rejected"
    )
    review_record = {
        "question_id": question["question_id"],
        "reviewer_model": reviewer,
        "checks": {k: bool(resp.get(k)) for k in BOOLEAN_KEYS},
        "recommendation": resp.get("recommendation"),
        "concise_reason": resp.get("concise_reason"),
        "passed": passed,
    }
    return updated, review_record


def review_questions(
    candidates: list[dict],
    client: StructuredLLMClient,
    system_prompt: str,
    *,
    reviewer_model: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Return (reviewed_questions, review_records)."""
    reviewed: list[dict] = []
    records: list[dict] = []
    for q in candidates:
        updated, record = review_question(
            q, client, system_prompt, reviewer_model=reviewer_model
        )
        reviewed.append(updated)
        records.append(record)
    return reviewed, records
