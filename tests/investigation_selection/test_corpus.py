from datetime import datetime

from data_pipeline.investigation_selection.corpus import (
    build_admission_corpus,
    encounter_origin,
    enumerate_first_wave_decisions,
    enumerate_order_decisions,
    enumerate_result_proxy_decision,
)


def _order(event_id: str, time: str, *, subtype: str = "CT Scan") -> dict:
    return {
        "event_id": event_id,
        "subject_id": "s1",
        "hadm_id": "h1",
        "event_kind": "imaging_ordered",
        "lifecycle_action": "create",
        "preferred_name": subtype,
        "content_specificity": "subtype_only",
        "event_time": time,
        "available_time": time,
        "evidence_phase": "source_event",
        "source_table": "hosp.poe_timeline",
        "time_resolution_status": "resolved",
        "value_structured_json": (
            '{"order_type":"Radiology","order_subtype":"%s","poe_id":"%s",'
            '"relations":{"chain_root_poe_id":"%s"}}' % (subtype, event_id, event_id)
        ),
    }


def _imaging_report(event_id: str, charttime: str, storetime: str, *exam_names: str, note_id: str = "n1") -> dict:
    details = []
    for index, name in enumerate(exam_names, start=1):
        details.append(
            '{"field_name":"exam_name","field_ordinal":"%s","field_value":"%s","note_id":"%s"}'
            % (index, name, note_id)
        )
    return {
        "event_id": event_id,
        "subject_id": "s1",
        "hadm_id": "h1",
        "event_kind": "imaging_reported",
        "preferred_name": "RR",
        "source_label": "RR",
        "event_time": charttime,
        "available_time": storetime,
        "evidence_phase": "source_event",
        "source_table": "note.radiology",
        "time_resolution_status": "resolved",
        "content_specificity": "entity_specific",
        "value_structured_json": '{"note_id":"%s","details":[%s]}' % (note_id, ",".join(details)),
    }


def _lab_result(event_id: str, charttime: str, storetime: str, name: str, specimen: str) -> dict:
    return {
        "event_id": event_id,
        "subject_id": "s1",
        "hadm_id": "h1",
        "event_kind": "laboratory_resulted",
        "preferred_name": name,
        "source_label": name,
        "event_time": charttime,
        "available_time": storetime,
        "evidence_phase": "source_event",
        "source_table": "hosp.labevents",
        "time_resolution_status": "resolved",
        "concept_id": f"lab:{name}",
        "raw_record_json": '{"specimen_id":"%s","charttime":"%s","storetime":"%s"}' % (specimen, charttime, storetime),
    }


def test_first_wave_uses_result_names_not_poe_subtypes() -> None:
    events = [
        _order("ct1", "2100-01-01 08:00:00"),
        _order("xr1", "2100-01-01 08:10:00", subtype="General Xray"),
        _lab_result("k1", "2100-01-01 08:05:00", "2100-01-01 09:00:00", "Potassium", "sp1"),
        _lab_result("t1", "2100-01-01 08:05:00", "2100-01-01 09:10:00", "Troponin T", "sp1"),
        _imaging_report(
            "rr1",
            "2100-01-01 08:12:00",
            "2100-01-01 10:00:00",
            "CT CHEST W/O CONTRAST",
            "CT ABD & PELVIS W/O CONTRAST",
        ),
        {
            "event_id": "sx",
            "subject_id": "s1",
            "hadm_id": "h1",
            "event_kind": "symptom_reported",
            "event_time": "2100-01-01 07:00:00",
            "available_time": "2100-01-01 07:00:00",
            "evidence_phase": "source_event",
            "preferred_name": "chest pain",
            "time_resolution_status": "resolved",
        },
    ]
    result = build_admission_corpus(events, hadm_id="h1", split_role="development")
    fact_names = {(row["fact_type"], row["investigation_name"]) for row in result["facts"]}
    assert ("order", "CT Scan") in fact_names
    assert ("reported", "CT CHEST W/O CONTRAST") in fact_names
    assert ("resulted", "Potassium") in fact_names
    tracks = {row["track_id"] for row in result["documents"]}
    assert "imaging_order" not in tracks
    assert "generic_lab_order" not in tracks
    names = {row["candidate_name"] for row in result["targets"]}
    assert "CT Scan" not in names
    assert "General Xray" not in names
    assert "Lab" not in names
    assert "Potassium" in names
    assert "Troponin T" in names
    assert "CT CHEST W/O CONTRAST" in names
    assert "CT ABD & PELVIS W/O CONTRAST" in names
    assert all(row["index_time"].startswith("2100-01-01 08:05:00") for row in result["documents"])
    evidence_ids = {row["event_id"] for row in result["evidence"]}
    assert "sx" in evidence_ids
    assert "ct1" not in evidence_ids
    assert "rr1" not in evidence_ids


def test_result_proxy_uses_storetime_after_query_window() -> None:
    origin = datetime.fromisoformat("2100-01-01 00:00:00")
    episodes = [
        {
            "episode_id": "ep:k",
            "track_id": "lab_result_proxy",
            "available_time": "2100-01-01 06:00:00",
            "eligibility": "eligible_investigation",
        },
        {
            "episode_id": "ep:too-early",
            "track_id": "lab_result_proxy",
            "available_time": "2100-01-01 03:00:00",
            "eligibility": "eligible_investigation",
        },
    ]
    nodes = enumerate_result_proxy_decision(episodes, origin=origin, query_hours=4, target_hours=24)
    assert nodes[0]["index_time"] == datetime.fromisoformat("2100-01-01 04:00:00")
    assert nodes[0]["target_episode_ids"] == ["ep:k"]


def test_origin_prefers_symptom_time() -> None:
    origin = encounter_origin([
        {"event_kind": "laboratory_resulted", "event_time": "2100-01-01 01:00:00", "time_resolution_status": "resolved"},
        {"event_kind": "symptom_reported", "event_time": "2100-01-01 08:00:00", "time_resolution_status": "resolved"},
    ])
    assert origin == datetime.fromisoformat("2100-01-01 08:00:00")


def test_order_decisions_do_not_merge_different_specificity() -> None:
    episodes = [
        {"episode_id": "a", "track_id": "imaging_order", "candidate_specificity": "subtype", "eligibility": "eligible_investigation", "initial_order_time": "2100-01-01 08:00:00"},
        {"episode_id": "b", "track_id": "clinical_order", "candidate_specificity": "subtype", "eligibility": "eligible_investigation", "initial_order_time": "2100-01-01 08:05:00"},
    ]
    nodes = enumerate_order_decisions(episodes, burst_minutes=15)
    assert len(nodes) == 2


def test_first_wave_freezes_at_earliest_result_charttime() -> None:
    episodes = [
        {"episode_id": "cxr-order", "track_id": "imaging_order", "candidate_specificity": "subtype", "eligibility": "eligible_investigation", "initial_order_time": "2100-01-01 07:50:00", "occurrence_time": "2100-01-01 07:50:00"},
        {"episode_id": "chest-ct", "track_id": "imaging_result_proxy", "candidate_specificity": "entity", "eligibility": "eligible_investigation", "occurrence_time": "2100-01-01 08:12:00", "initial_order_time": "2100-01-01 08:12:00"},
        {"episode_id": "k", "track_id": "lab_result_proxy", "candidate_specificity": "entity", "eligibility": "eligible_investigation", "occurrence_time": "2100-01-01 08:00:00", "initial_order_time": "2100-01-01 08:00:00"},
        {"episode_id": "late-lab", "track_id": "lab_result_proxy", "candidate_specificity": "entity", "eligibility": "eligible_investigation", "occurrence_time": "2100-01-01 18:00:00", "initial_order_time": "2100-01-01 18:00:00"},
    ]
    nodes = enumerate_first_wave_decisions(episodes, burst_minutes=15)
    assert {row["track_id"] for row in nodes} == {"lab_result_proxy", "imaging_result_proxy"}
    assert all(row["index_time"] == datetime.fromisoformat("2100-01-01 08:00:00") for row in nodes)
    by_track = {row["track_id"]: row for row in nodes}
    assert by_track["lab_result_proxy"]["target_episode_ids"] == ["k"]
    assert by_track["imaging_result_proxy"]["target_episode_ids"] == ["chest-ct"]


def test_first_wave_hides_later_orders_and_keeps_untimed_complaint() -> None:
    events = [
        {
            "event_id": "cc",
            "subject_id": "s1",
            "hadm_id": "h1",
            "event_kind": "symptom_reported",
            "preferred_name": "chest pain",
            "event_time": None,
            "available_time": None,
            "evidence_phase": "source_event",
            "time_policy_id": "triage_no_time_v1",
            "time_resolution_status": "unavailable",
            "source_table": "ed.triage",
        },
        {
            "event_id": "vital",
            "subject_id": "s1",
            "hadm_id": "h1",
            "event_kind": "vital_measured",
            "preferred_name": "heart rate",
            "event_time": "2100-01-01 07:00:00",
            "available_time": "2100-01-01 07:00:00",
            "evidence_phase": "source_event",
            "time_resolution_status": "resolved",
            "source_table": "ed.vitalsign",
        },
        _lab_result("k1", "2100-01-01 08:00:00", "2100-01-01 09:00:00", "Potassium", "sp1"),
        _order("echo1", "2100-01-01 12:00:00", subtype="Echo"),
        _lab_result("late-k", "2100-01-01 14:00:00", "2100-01-01 15:00:00", "Sodium", "sp2"),
        _imaging_report("late-ct", "2100-01-01 16:00:00", "2100-01-01 17:00:00", "CT CHEST W/O CONTRAST"),
    ]
    result = build_admission_corpus(events, hadm_id="h1", split_role="development")
    labs = [row for row in result["documents"] if row["track_id"] == "lab_result_proxy"]
    assert len(labs) == 1
    assert labs[0]["index_time"].startswith("2100-01-01 08:00:00")
    assert labs[0]["decision_stage"] == "first_wave"
    assert labs[0]["query_start"].startswith("2100-01-01 07:00:00")
    names = {row["candidate_name"] for row in result["targets"]}
    assert "Potassium" in names
    assert "Sodium" not in names
    assert "CT CHEST W/O CONTRAST" not in names
    assert "Echo" not in names
    evidence = [row for row in result["evidence"] if row["decision_id"] == labs[0]["decision_id"]]
    assert any(row["preferred_name"] == "chest pain" for row in evidence)
    assert all(row["event_id"] not in {"echo1", "late-k", "late-ct", "k1"} for row in evidence)


def test_complaint_stays_visible_when_origin_is_after_first_investigation() -> None:
    events = [
        {
            "event_id": "cc",
            "subject_id": "s1",
            "hadm_id": "h1",
            "event_kind": "symptom_reported",
            "preferred_name": "dyspnea",
            "event_time": None,
            "available_time": None,
            "evidence_phase": "source_event",
            "time_policy_id": "triage_no_time_v1",
            "source_table": "ed.triage",
        },
        {
            "event_id": "vital",
            "subject_id": "s1",
            "hadm_id": "h1",
            "event_kind": "vital_measured",
            "preferred_name": "heart rate",
            "event_time": "2100-01-01 09:00:00",
            "available_time": "2100-01-01 09:00:00",
            "evidence_phase": "source_event",
            "time_resolution_status": "resolved",
            "source_table": "ed.vitalsign",
        },
        _lab_result("k1", "2100-01-01 08:00:00", "2100-01-01 09:00:00", "Potassium", "sp1"),
    ]
    result = build_admission_corpus(events, hadm_id="h1", split_role="development")
    doc = result["documents"][0]
    assert doc["index_time"].startswith("2100-01-01 08:00:00")
    assert doc["query_start"].startswith("2100-01-01 08:00:00")
    evidence = result["evidence"]
    assert any(row["preferred_name"] == "dyspnea" for row in evidence)
    assert all(row["event_id"] != "vital" for row in evidence)
