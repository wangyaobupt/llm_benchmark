from data_pipeline.investigation_selection.actions import project_investigation_actions
from data_pipeline.investigation_selection.first_wave import attach_radiology_exam_details
from data_pipeline.investigation_selection.eligibility import load_eligibility_policy
from data_pipeline.investigation_selection.source_grouping import attach_source_groups


def _lab_create(**overrides):
    row = {
        "event_id": "evt:lab1",
        "subject_id": "s1",
        "hadm_id": "h1",
        "event_kind": "laboratory_ordered",
        "lifecycle_action": "create",
        "status": "Inactive",
        "event_time": "2100-01-01 08:00:00",
        "available_time": "2100-01-01 08:00:00",
        "source_table": "hosp.poe_timeline",
        "value_structured_json": (
            '{"order_type":"Lab","order_subtype":null,"poe_id":"s1-4",'
            '"poe_seq":"4","relations":{"chain_root_poe_id":"s1-4",'
            '"successor_poe_id":"s1-9","chain_complete":true}}'
        ),
    }
    row.update(overrides)
    return row


def test_actions_lift_chain_root_and_keep_inactive_create() -> None:
    result = project_investigation_actions([_lab_create()])
    assert len(result.actions) == 1
    action = result.actions[0]
    assert action["chain_root_poe_id"] == "s1-4"
    assert action["source_group_type"] == "poe_lifecycle_chain"
    assert action["track_id"] == "generic_lab_order"
    assert action["candidate_specificity"] == "category"
    assert action["status"] == "Inactive"
    assert action["action"] == "create"
    assert action["eligibility"] == "eligible_investigation"


def test_medication_order_is_not_an_investigation() -> None:
    result = project_investigation_actions([
        {
            "event_id": "evt:med",
            "hadm_id": "h1",
            "event_kind": "clinical_ordered",
            "lifecycle_action": "create",
            "event_time": "2100-01-01 08:00:00",
            "available_time": "2100-01-01 08:00:00",
            "source_table": "hosp.poe_timeline",
            "value_structured_json": (
                '{"order_type":"Medications","order_subtype":null,"poe_id":"s1-12",'
                '"relations":{"chain_root_poe_id":"s1-12"}}'
            ),
        }
    ])
    assert result.actions[0]["eligibility"] == "excluded_non_investigation"
    assert result.actions[0]["track_id"] is None


def test_imaging_keeps_source_specificity() -> None:
    result = project_investigation_actions([
        {
            "event_id": "evt:ct",
            "hadm_id": "h1",
            "event_kind": "imaging_ordered",
            "lifecycle_action": "create",
            "preferred_name": "CT Scan",
            "content_specificity": "subtype_only",
            "event_time": "2100-01-01 08:02:00",
            "available_time": "2100-01-01 08:02:00",
            "source_table": "hosp.poe_timeline",
            "value_structured_json": (
                '{"order_type":"Radiology","order_subtype":"CT Scan","poe_id":"s1-9",'
                '"relations":{"chain_root_poe_id":"s1-9"}}'
            ),
        }
    ])
    assert result.actions[0]["candidate_name"] == "CT Scan"
    assert result.actions[0]["candidate_specificity"] == "subtype"
    assert result.actions[0]["candidate_name"] != "CT head"


def test_imaging_report_uses_exam_name_not_note_type() -> None:
    result = project_investigation_actions([
        {
            "event_id": "rr1",
            "hadm_id": "h1",
            "event_kind": "imaging_reported",
            "preferred_name": "RR",
            "event_time": "2100-01-01 08:12:00",
            "available_time": "2100-01-01 10:00:00",
            "source_table": "note.radiology",
            "content_specificity": "entity_specific",
            "value_structured_json": (
                '{"note_id":"n1","details":['
                '{"field_name":"exam_name","field_ordinal":"1","field_value":"CT CHEST W/O CONTRAST"},'
                '{"field_name":"exam_name","field_ordinal":"2","field_value":"OUTSIDE FILMS READ ONLY"}'
                ']}'
            ),
        }
    ])
    assert [row["candidate_name"] for row in result.actions] == ["CT CHEST W/O CONTRAST"]
    assert result.actions[0]["track_id"] == "imaging_result_proxy"
    assert result.actions[0]["candidate_specificity"] == "entity"


def test_exam_name_is_reattached_from_radiology_detail_sidecar() -> None:
    events = attach_radiology_exam_details(
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
        {
            "n1": [
                {"field_name": "exam_name", "field_value": "CHEST (PORTABLE AP)", "note_id": "n1"},
            ]
        },
    )
    result = project_investigation_actions(events)
    assert [row["candidate_name"] for row in result.actions] == ["CHEST (PORTABLE AP)"]


def test_poe_chain_spans_multiple_poe_ids() -> None:
    grouped = attach_source_groups([
        _lab_create(event_id="evt:a", poe_id="s1-4"),
        _lab_create(
            event_id="evt:b",
            lifecycle_action="change",
            value_structured_json=(
                '{"order_type":"Lab","poe_id":"s1-8","poe_seq":"8",'
                '"relations":{"chain_root_poe_id":"s1-4"}}'
            ),
        ),
    ])
    ids = {row["source_group_id"] for row in grouped.rows}
    assert len(ids) == 1
    assert grouped.rows[0]["source_group_type"] == "poe_lifecycle_chain"


def test_eligibility_catalog_loads() -> None:
    policy = load_eligibility_policy()
    assert policy.classify("Medications", None) == "excluded_non_investigation"
    assert policy.classify("Cardiology", "ECG") == "eligible_investigation"
    assert policy.classify("General Care", "Telemetry") == "monitoring_only"
    assert policy.classify("General Care", "Vitals/Monitoring") == "monitoring_only"
    assert policy.status == "protocol_frozen"
