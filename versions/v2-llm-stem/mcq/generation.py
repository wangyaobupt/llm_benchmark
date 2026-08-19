"""LLM stem + rationale generation and program-level validation (Stage 6-7).

The model returns only ``stem`` and ``rationale``; the fixed options, correct
option and answer are supplied by the program and must not change. Each output
then passes the 12 deterministic checks before becoming a candidate.
"""
from __future__ import annotations

from .client import StructuredLLMClient
from .constants import PROMPT_VERSION, RULE_VERSION, SCHEMA_VERSION
from .hashing import question_id
from .validation import validate_question
from .validators import STEM_RESPONSE_VALIDATOR


def build_generation_payload(rule: dict, options: dict, correct_option: str,
                             correct_answer: str) -> dict:
    return {
        "condition_features": list(rule["condition_display_names"]),
        "question_language": "English",
        "question_type": "real-world investigation selection prediction",
        "question_semantics": "most likely to be selected",
        "options": dict(options),
        "correct_option": correct_option,
        "correct_answer": correct_answer,
        "rule_statistics": {
            "n_x": rule["n_x"],
            "n_xy": rule["n_xy"],
            "smoothed_probability": rule["smoothed_probability"],
            "lift": rule["lift"],
        },
    }


def build_question(rule: dict, options: dict, correct_option: str,
                   correct_answer: str, stem_response: dict,
                   generator_model: str) -> dict:
    stats = {
        "n_total": rule["n_total"], "n_x": rule["n_x"], "n_y": rule["n_y"],
        "n_xy": rule["n_xy"],
        "conditional_probability": rule["conditional_probability"],
        "smoothed_probability": rule["smoothed_probability"],
        "baseline_probability": rule["baseline_probability"],
        "lift": rule["lift"], "wilson_lower": rule["wilson_lower"],
        "fisher_p": rule["fisher_p"], "fdr_q": rule["fdr_q"],
        "bootstrap_stability": rule["bootstrap_stability"],
        "probability_gap": rule["probability_gap"],
        "score_ratio": rule["score_ratio"],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "question_id": question_id(rule["rule_id"]),
        "question_type": "clinical_investigation_selection",
        "language": "en",
        "semantics": "most_likely_selected_in_rwd",
        "stem": stem_response["stem"],
        "options": dict(options),
        "correct_option": correct_option,
        "correct_answer": correct_answer,
        "rationale": stem_response["rationale"],
        "condition_features": list(rule["condition_display_names"]),
        "comparison_class": rule["comparison_class"],
        "target_investigation_id": rule["target_investigation_id"],
        "source_rule_id": rule["rule_id"],
        "statistics": stats,
        "generator_model": generator_model,
        "reviewer_model": "",
        "prompt_version": PROMPT_VERSION,
        "automatic_review_status": "pending",
        "human_review_status": "pending",
    }


def generate_questions(
    locked: list[dict],
    client: StructuredLLMClient,
    system_prompt: str,
    source_texts: dict[str, str],
    *,
    generator_model: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Generate and program-validate candidates from locked options.

    ``source_texts`` maps a joined condition string to its raw source text (used
    only for the local overlap check — never sent to the model).
    Returns ``(candidates, failures)``; failures carry the stable error codes.
    """
    model = generator_model or client.model_name
    candidates: list[dict] = []
    failures: list[dict] = []
    for item in locked:
        rule = item["rule"]
        options = item["options"]
        correct_option = item["correct_option"]
        correct_answer = item["correct_answer"]
        payload = build_generation_payload(rule, options, correct_option, correct_answer)
        stem_response, _meta = client.complete(
            task_type="generate",
            system_prompt=system_prompt,
            user_payload=payload,
            validator=STEM_RESPONSE_VALIDATOR,
        )
        question = build_question(
            rule, options, correct_option, correct_answer, stem_response, model
        )
        key = ", ".join(rule["condition_display_names"])
        src = [source_texts[key]] if key in source_texts and source_texts[key] else []
        errors = validate_question(question, rule, src)
        if errors:
            failures.append({"question_id": question["question_id"], "errors": errors})
        else:
            candidates.append(question)
    return candidates, failures
