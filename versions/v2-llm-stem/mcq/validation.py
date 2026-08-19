"""The 12 deterministic program checks (design doc §10, logic doc §6).

A question passes only if ALL checks pass; any failure is recorded with a stable
error code and the question is dropped (never written to candidates).
"""
from __future__ import annotations

from typing import Iterable

from .constants import GENERATION_ERROR_CODES, PREDICTION_SEMANTICS_PHRASE
from .privacy import (
    contains_cjk,
    contains_deidentification_placeholder,
    contains_exact_date,
    contains_linkage_identifier,
    contains_posterior_fact,
    shingle_jaccard,
)

MIN_STEM_LENGTH = 20
MIN_RATIONALE_LENGTH = 10
MAX_SOURCE_OVERLAP = 0.55

# Registered answer synonyms (canonical -> set of synonyms). Extend via the
# investigation catalog alias groups; empty until the catalog is frozen.
SYNONYMS: dict[str, set[str]] = {}


def _answer_synonym_leaked(stem: str, answer: str) -> bool:
    answer_l = answer.casefold()
    for syn in SYNONYMS.get(answer_l, set()):
        if syn.casefold() in stem.casefold():
            return True
    # Light heuristic: a multi-word answer whose every content token (len>=4)
    # appears in the stem is treated as a synonym leak.
    tokens = [t for t in answer_l.split() if len(t) >= 4]
    if len(tokens) >= 2 and all(t in stem.casefold() for t in tokens):
        return True
    return False


def validate_question(
    question: dict,
    rule: dict,
    source_texts: Iterable[str] = (),
    *,
    min_stem_length: int = MIN_STEM_LENGTH,
    min_rationale_length: int = MIN_RATIONALE_LENGTH,
    max_source_overlap: float = MAX_SOURCE_OVERLAP,
) -> list[str]:
    """Return the list of stable error codes (empty list == passed)."""
    errors: list[str] = []
    stem = question.get("stem", "")
    rationale = question.get("rationale", "")
    options = question.get("options", {})
    correct_option = question.get("correct_option")
    correct_answer = question.get("correct_answer", "")
    condition_features = question.get("condition_features", [])

    # 1. Minimum length after strip (stem and rationale).
    if len(stem.strip()) < min_stem_length or len(rationale.strip()) < min_rationale_length:
        errors.append("empty_or_short_content")

    # 2. Prediction semantics phrase present.
    if PREDICTION_SEMANTICS_PHRASE.casefold() not in stem.casefold():
        errors.append("missing_prediction_semantics")

    # 3. No answer / synonym / option-name leakage in the stem.
    option_names = [v for v in options.values()]
    stem_l = stem.casefold()
    if correct_answer.casefold() in stem_l:
        errors.append("answer_leaked_in_stem")
    elif any(o and o.casefold() in stem_l for o in option_names):
        errors.append("answer_leaked_in_stem")
    elif _answer_synonym_leaked(stem, correct_answer):
        errors.append("answer_synonym_leaked_in_stem")

    # 4. No exact date / de-id placeholder / linkage identifier.
    if contains_exact_date(stem):
        errors.append("contains_exact_date")
    if contains_deidentification_placeholder(stem):
        errors.append("contains_deidentification_placeholder")
    if contains_linkage_identifier(stem):
        errors.append("contains_linkage_identifier")

    # 5. No CJK (English-only question).
    if contains_cjk(stem) or contains_cjk(rationale):
        errors.append("contains_non_english_cjk_text")

    # 6. No unsupported posterior clinical facts (diagnosis/results/treatment).
    if contains_posterior_fact(stem) or contains_posterior_fact(rationale):
        errors.append("unsupported_clinical_fact")

    # 7. 5-word shingle Jaccard overlap vs source text <= max.
    for src in source_texts:
        if shingle_jaccard(stem, src) > max_source_overlap:
            errors.append("source_overlap")
            break

    # 8. options exactly A-D.
    if set(options.keys()) != {"A", "B", "C", "D"}:
        errors.append("invalid_option_set")

    # 9. options non-empty and unique.
    vals = [v for v in options.values()]
    if any(not v or not v.strip() for v in vals) or len(set(v.casefold() for v in vals)) != 4:
        errors.append("invalid_option_set")

    # 10. options[correct_option] == correct_answer.
    if options.get(correct_option) != correct_answer:
        errors.append("correct_answer_mismatch")

    # 11. correct_answer == accepted rule rank-1 investigation.
    if correct_answer != rule.get("target_investigation_name"):
        errors.append("correct_answer_mismatch")

    # 12. condition_features match the source rule, order preserved.
    if condition_features != rule.get("condition_display_names"):
        errors.append("condition_feature_mismatch")

    # Deduplicate while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            ordered.append(e)
    unknown = [e for e in ordered if e not in GENERATION_ERROR_CODES]
    if unknown:
        raise ValueError(f"unknown generation error code: {unknown}")
    return ordered
