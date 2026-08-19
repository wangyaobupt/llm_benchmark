from data_pipeline.investigation_selection.facts import (
    build_investigation_facts,
    first_wave_facts,
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
        "source_table": "hosp.poe_timeline",
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
        "source_table": "note.radiology",
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
        "source_table": "hosp.labevents",
        "raw_record_json": '{"specimen_id":"%s","charttime":"%s","storetime":"%s"}' % (specimen, charttime, storetime),
    }


def test_report_explodes_exam_names_and_keeps_poe_as_order() -> None:
    result = build_investigation_facts([
        _order("ct1", "2142-04-28 18:02:32"),
        _imaging_report(
            "rr6",
            "2142-04-28 18:04:00",
            "2142-04-28 19:40:00",
            "CT CHEST W/O CONTRAST",
            "CT ABD & PELVIS W/O CONTRAST",
            "OUTSIDE FILMS READ ONLY",
        ),
        _lab_result("pt1", "2142-04-29 05:55:00", "2142-04-29 06:45:00", "PT", "sp1"),
    ])
    names = {(row["domain"], row["fact_type"], row["investigation_name"]) for row in result.facts}
    assert names == {
        ("imaging", "order", "CT Scan"),
        ("imaging", "reported", "CT CHEST W/O CONTRAST"),
        ("imaging", "reported", "CT ABD & PELVIS W/O CONTRAST"),
        ("lab", "resulted", "PT"),
    }
    reported = [row for row in result.facts if row["fact_type"] == "reported"]
    assert all(row["occurrence_time"].startswith("2142-04-28 18:04:00") for row in reported)
    assert all(row["available_time"].startswith("2142-04-28 19:40:00") for row in reported)
    assert all(row["occurrence_semantics"] == "exam_time_proxy" for row in reported)
    assert all(row["preferred_name"] != "RR" for row in reported)
    orders = [row for row in result.facts if row["fact_type"] == "order"]
    assert orders[0]["occurrence_semantics"] == "order_entry_time"
    assert len({row["fact_id"] for row in result.facts}) == 4


def test_first_wave_facts_drop_poe_orders() -> None:
    result = build_investigation_facts([
        _order("ct1", "2142-04-28 18:02:32"),
        _imaging_report("rr6", "2142-04-28 18:04:00", "2142-04-28 19:40:00", "CT CHEST W/O CONTRAST"),
        _lab_result("pt1", "2142-04-29 05:55:00", "2142-04-29 06:45:00", "PT", "sp1"),
    ])
    wave = first_wave_facts(result.facts)
    assert {row["investigation_name"] for row in wave} == {"CT CHEST W/O CONTRAST", "PT"}
    assert all(row["fact_type"] != "order" for row in wave)
    assert "CT Scan" not in {row["investigation_name"] for row in wave}


def test_facts_do_not_join_order_to_result() -> None:
    result = build_investigation_facts([
        _order("ct1", "2142-04-28 18:02:32"),
        _imaging_report("rr6", "2142-04-28 18:04:00", "2142-04-28 19:40:00", "CT CHEST W/O CONTRAST"),
    ])
    groups = {row["group_type"] for row in result.facts}
    assert groups == {"poe_lifecycle_chain", "radiology_exam"}
    order = next(row for row in result.facts if row["fact_type"] == "order")
    reported = next(row for row in result.facts if row["fact_type"] == "reported")
    assert order["group_id"] != reported["group_id"]
    assert order["source_event_id"] != reported["source_event_id"]


def test_exam_name_reattached_from_sidecar_inside_facts() -> None:
    result = build_investigation_facts(
        [{
            "event_id": "rr1",
            "hadm_id": "h1",
            "event_kind": "imaging_reported",
            "preferred_name": "RR",
            "event_time": "2100-01-01 08:12:00",
            "available_time": "2100-01-01 10:00:00",
            "source_table": "note.radiology",
            "value_structured_json": '{"note_id":"n1","note_seq":"1"}',
        }],
        radiology_sidecar={
            "n1": [
                {"field_name": "exam_name", "field_value": "CHEST (PORTABLE AP)", "note_id": "n1"},
            ]
        },
    )
    assert [row["investigation_name"] for row in result.facts] == ["CHEST (PORTABLE AP)"]
    assert result.facts[0]["fact_type"] == "reported"
    assert result.facts[0]["domain"] == "imaging"


def test_symptom_events_are_not_investigation_facts() -> None:
    result = build_investigation_facts([
        {
            "event_id": "sx",
            "hadm_id": "h1",
            "event_kind": "symptom_reported",
            "preferred_name": "chest pain",
            "event_time": "2100-01-01 07:00:00",
            "available_time": "2100-01-01 07:00:00",
            "source_table": "ed.triage",
        },
        _lab_result("k1", "2100-01-01 08:00:00", "2100-01-01 09:00:00", "Potassium", "sp1"),
    ])
    assert [row["investigation_name"] for row in result.facts] == ["Potassium"]
    assert result.metrics["skipped_non_investigation"] == 1
