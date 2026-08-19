from datetime import datetime

from data_pipeline.investigation_selection.mining import build_family, condition_token
from data_pipeline.investigation_selection.presentation import split_complaint_labels, stamp_presentation_events
from data_pipeline.investigation_selection.ranking import fisher_greater


def test_condition_token_is_presentation_only() -> None:
    assert condition_token({"event_kind": "imaging_ordered", "preferred_name": "CT Scan"}) is None
    assert condition_token({"event_kind": "laboratory_resulted", "concept_id": "lab:50971", "preferred_name": "Albumin"}) is None
    assert condition_token({"event_kind": "symptom_reported", "preferred_name": "chest pain"}) == "symptom_reported:name:chest pain"
    assert condition_token({"event_kind": "symptom_reported", "preferred_name": "I"}) is None


def test_complaint_splits_into_usable_tokens() -> None:
    assert split_complaint_labels("Chest pain, Neck pain") == ["Chest pain", "Neck pain"]


def test_untimed_complaint_is_stamped_at_origin_not_invented_from_source() -> None:
    stamped = stamp_presentation_events(
        [{
            "event_kind": "symptom_reported",
            "preferred_name": "chest pain",
            "event_time": None,
            "available_time": None,
            "time_policy_id": "triage_no_time_v1",
        }],
        datetime.fromisoformat("2100-01-01 07:00:00"),
    )
    assert stamped[0]["event_time"] == "2100-01-01 07:00:00"
    assert stamped[0]["available_time"] == "2100-01-01 07:00:00"
    assert stamped[0]["time_policy_id"] == "presentation_origin_v1"


def test_fisher_greater_is_small_for_positive_association() -> None:
    assert fisher_greater(8, 2, 1, 9) < 0.05
    assert fisher_greater(1, 9, 8, 2) > 0.5


def test_family_uses_zero_target_docs_in_denominator() -> None:
    documents = [
        {"decision_id": "d1", "subject_id": "s1", "hadm_id": "h1", "candidate_class": "imaging_order:subtype", "index_time": "2100-01-01 08:00:00"},
        {"decision_id": "d2", "subject_id": "s2", "hadm_id": "h2", "candidate_class": "imaging_order:subtype", "index_time": "2100-01-01 08:00:00"},
        {"decision_id": "d3", "subject_id": "s3", "hadm_id": "h3", "candidate_class": "imaging_order:subtype", "index_time": "2100-01-01 08:00:00"},
    ]
    presentation = {
        "h1": [{"event_kind": "symptom_reported", "preferred_name": "chest pain", "available_time": "2100-01-01 04:00:00"}],
        "h2": [{"event_kind": "symptom_reported", "preferred_name": "chest pain", "available_time": "2100-01-01 04:00:00"}],
    }
    targets = [
        {"decision_id": "d1", "candidate_id": "cand:ct", "candidate_name": "CT Scan", "candidate_class": "imaging_order:subtype"},
    ]
    family = build_family(
        documents,
        [],
        targets,
        thresholds={"condition_subjects_min": 1, "candidate_subjects_min": 1},
        presentation_by_hadm=presentation,
    )
    assert len(family) == 1
    assert family[0]["condition_name"] == "chest pain"
    assert family[0]["n_total"] == 3
    assert family[0]["n_x"] == 2
    assert family[0]["n_y"] == 1
    assert family[0]["n_xy"] == 1
