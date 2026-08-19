"""Unit tests for the 12 program checks and privacy helpers."""
from __future__ import annotations

from mcq.privacy import (
    contains_cjk,
    contains_deidentification_placeholder,
    contains_exact_date,
    contains_linkage_identifier,
    contains_posterior_fact,
    find_forbidden_fields,
    shingle_jaccard,
)
from mcq.validation import validate_question


def _base_question(**overrides):
    q = {
        "stem": "A patient presents with chest pain and diaphoresis. "
                "Which investigation is most likely to be selected?",
        "rationale": "In the source data, this presentation is most strongly "
                     "associated with selection of the keyed investigation.",
        "options": {"A": "CT Scan", "B": "MRI Brain", "C": "General Xray",
                    "D": "Nuclear Scan"},
        "correct_option": "A",
        "correct_answer": "CT Scan",
        "condition_features": ["chest pain", "diaphoresis"],
    }
    q.update(overrides)
    return q


def _rule():
    return {
        "target_investigation_name": "CT Scan",
        "condition_display_names": ["chest pain", "diaphoresis"],
    }


def test_clean_question_passes():
    assert validate_question(_base_question(), _rule()) == []


def test_answer_leaked():
    q = _base_question(stem="A patient needs a CT Scan. Which investigation is "
                             "most likely to be selected?")
    assert "answer_leaked_in_stem" in validate_question(q, _rule())


def test_missing_semantics():
    q = _base_question(stem="A patient presents with chest pain. What is the next step?")
    assert "missing_prediction_semantics" in validate_question(q, _rule())


def test_cjk_rejected():
    q = _base_question(stem="A patient presents with chest pain. 中文 Which "
                             "investigation is most likely to be selected?")
    assert "contains_non_english_cjk_text" in validate_question(q, _rule())


def test_condition_feature_mismatch():
    q = _base_question(condition_features=["chest pain"])
    assert "condition_feature_mismatch" in validate_question(q, _rule())


def test_posterior_fact_rejected():
    q = _base_question(stem="A patient was diagnosed with pneumonia and treated "
                             "with antibiotics. Which investigation is most likely "
                             "to be selected?")
    assert "unsupported_clinical_fact" in validate_question(q, _rule())


def test_source_overlap():
    q = _base_question(
        stem="chest pain and diaphoresis with shortness of breath and nausea and "
             "vomiting and fever and cough"
    )
    src = "chest pain and diaphoresis with shortness of breath and nausea and vomiting"
    assert "source_overlap" in validate_question(q, _rule(), [src])


def test_privacy_helpers():
    assert contains_cjk("你好")
    assert not contains_cjk("hello")
    assert contains_exact_date("on 2010-01-01 the patient")
    assert not contains_exact_date("the patient presents")
    assert contains_deidentification_placeholder("[**First Name**]")
    assert contains_linkage_identifier("MRN 12345678")
    assert contains_posterior_fact("was diagnosed with pneumonia")


def test_forbidden_fields_recursive():
    payload = {"a": {"nested": [{"subject_id": "x"}]}}
    assert find_forbidden_fields(payload) == ["$.a.nested[0].subject_id"]
    assert find_forbidden_fields({"safe": 1}) == []


def test_shingle_jaccard_identity():
    assert shingle_jaccard("a b c d e", "a b c d e") == 1.0
    assert shingle_jaccard("a b c d e", "f g h i j") == 0.0
