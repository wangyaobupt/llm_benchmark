from data_pipeline.investigation_selection.episodes import build_investigation_episodes
from data_pipeline.investigation_selection.query import (
    list_investigations_at,
    list_visible_facts,
    visibility_decision,
)
from datetime import datetime


def test_create_remains_observed_if_later_inactive() -> None:
    events = [
        {
            "event_id": "evt:create",
            "hadm_id": "h1",
            "event_kind": "imaging_ordered",
            "lifecycle_action": "create",
            "status": "Inactive",
            "preferred_name": "CT Scan",
            "content_specificity": "subtype_only",
            "event_time": "2100-01-01 08:00:00",
            "available_time": "2100-01-01 08:00:00",
            "source_table": "hosp.poe_timeline",
            "value_structured_json": (
                '{"order_type":"Radiology","order_subtype":"CT Scan","poe_id":"s1-1",'
                '"relations":{"chain_root_poe_id":"s1-1"}}'
            ),
        },
        {
            "event_id": "evt:stop",
            "hadm_id": "h1",
            "event_kind": "imaging_ordered",
            "lifecycle_action": "discontinue",
            "status": "Discontinued",
            "preferred_name": "CT Scan",
            "event_time": "2100-01-01 10:00:00",
            "available_time": "2100-01-01 10:00:00",
            "source_table": "hosp.poe_timeline",
            "value_structured_json": (
                '{"order_type":"Radiology","order_subtype":"CT Scan","poe_id":"s1-2",'
                '"relations":{"chain_root_poe_id":"s1-1"}}'
            ),
        },
    ]
    at = list_investigations_at(events, hadm_id="h1", index_time="2100-01-01 08:00:00")
    assert len(at.investigations) == 1
    assert at.investigations[0]["event_id"] == "evt:create"
    episodes = build_investigation_episodes(events)
    assert episodes.episodes[0]["was_later_cancelled"] is True
    assert episodes.episodes[0]["initial_order_time"].startswith("2100-01-01 08:00:00")


def test_cancel_does_not_delete_prior_create() -> None:
    events = [
        {
            "event_id": "evt:create",
            "hadm_id": "h1",
            "event_kind": "imaging_ordered",
            "lifecycle_action": "create",
            "preferred_name": "ECG",
            "event_time": "2100-01-01 08:00:00",
            "available_time": "2100-01-01 08:00:00",
            "source_table": "hosp.poe_timeline",
            "value_structured_json": (
                '{"order_type":"Cardiology","order_subtype":"ECG","poe_id":"s1-1",'
                '"relations":{"chain_root_poe_id":"s1-1"}}'
            ),
        },
        {
            "event_id": "evt:cancel",
            "hadm_id": "h1",
            "event_kind": "imaging_ordered",
            "lifecycle_action": "cancel",
            "preferred_name": "ECG",
            "event_time": "2100-01-01 08:20:00",
            "available_time": "2100-01-01 08:20:00",
            "source_table": "hosp.poe_timeline",
            "value_structured_json": (
                '{"order_type":"Cardiology","order_subtype":"ECG","poe_id":"s1-2",'
                '"relations":{"chain_root_poe_id":"s1-1"}}'
            ),
        },
    ]
    episodes = build_investigation_episodes(events)
    assert len(episodes.episodes) == 1
    assert "evt:create" in episodes.episodes[0]["source_event_ids"]


def test_change_without_delta_is_not_a_new_target() -> None:
    events = [
        {
            "event_id": "evt:create",
            "hadm_id": "h1",
            "event_kind": "imaging_ordered",
            "lifecycle_action": "create",
            "preferred_name": "CT Scan",
            "event_time": "2100-01-01 08:00:00",
            "available_time": "2100-01-01 08:00:00",
            "source_table": "hosp.poe_timeline",
            "value_structured_json": (
                '{"order_type":"Radiology","order_subtype":"CT Scan","poe_id":"s1-1",'
                '"relations":{"chain_root_poe_id":"s1-1"}}'
            ),
        },
        {
            "event_id": "evt:change",
            "hadm_id": "h1",
            "event_kind": "imaging_ordered",
            "lifecycle_action": "change",
            "preferred_name": "CT Scan",
            "event_time": "2100-01-01 08:05:00",
            "available_time": "2100-01-01 08:05:00",
            "source_table": "hosp.poe_timeline",
            "value_structured_json": (
                '{"order_type":"Radiology","order_subtype":"CT Scan","poe_id":"s1-2",'
                '"relations":{"chain_root_poe_id":"s1-1"}}'
            ),
        },
    ]
    at = list_investigations_at(events, hadm_id="h1", index_time="2100-01-01 08:05:00")
    assert [row["event_id"] for row in at.investigations] == []
    episodes = build_investigation_episodes(events)
    assert len(episodes.episodes) == 1
    assert "ORDER_CHANGE_NO_OBSERVABLE_DELTA" in episodes.episodes[0]["reason_codes"]


def test_unknown_available_time_is_rejected() -> None:
    visible, reason = visibility_decision(
        {
            "event_id": "e1",
            "event_kind": "laboratory_resulted",
            "event_time": "2100-01-01 07:00:00",
            "available_time": None,
            "evidence_phase": "source_event",
        },
        index_time=datetime.fromisoformat("2100-01-01 08:00:00"),
        query_start=datetime.fromisoformat("2100-01-01 04:00:00"),
    )
    assert visible is False
    assert reason == "AVAILABLE_TIME_UNKNOWN"


def test_result_recency_uses_available_time() -> None:
    facts = list_visible_facts(
        [
            {
                "event_id": "lab1",
                "hadm_id": "h1",
                "event_kind": "laboratory_resulted",
                "event_time": "2100-01-01 19:55:00",
                "available_time": "2100-01-01 20:56:00",
                "evidence_phase": "source_event",
                "preferred_name": "Troponin",
            }
        ],
        hadm_id="h1",
        index_time="2100-01-02 00:19:00",
        query_start="2100-01-01 20:19:00",
    )
    assert facts.included[0]["recency_time_semantics"] == "available_time"
    assert facts.included[0]["event_id"] == "lab1"


def test_event_time_equal_to_index_is_not_prior_evidence() -> None:
    visible, reason = visibility_decision(
        {
            "event_id": "e1",
            "event_kind": "imaging_ordered",
            "event_time": "2100-01-01 08:00:00",
            "available_time": "2100-01-01 08:00:00",
            "evidence_phase": "source_event",
        },
        index_time=datetime.fromisoformat("2100-01-01 08:00:00"),
        query_start=None,
    )
    assert visible is False
    assert reason == "EVENT_NOT_PREINDEX"


def test_bound_complaint_is_visible_at_first_wave_index() -> None:
    visible, reason = visibility_decision(
        {
            "event_id": "cc",
            "event_kind": "symptom_reported",
            "event_time": "2100-01-01 08:00:00",
            "available_time": "2100-01-01 08:00:00",
            "evidence_phase": "source_event",
            "time_policy_id": "presentation_origin_v1",
            "preferred_name": "chest pain",
        },
        index_time=datetime.fromisoformat("2100-01-01 08:00:00"),
        query_start=datetime.fromisoformat("2100-01-01 08:00:00"),
    )
    assert visible is True
    assert reason == "INCLUDED_PRESENTATION_ORIGIN"
