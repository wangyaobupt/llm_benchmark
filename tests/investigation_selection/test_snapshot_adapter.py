from data_pipeline.investigation_selection.snapshot_adapter import (
    SnapshotAdapter,
    normalize_discharge_ner_records,
)


def test_discharge_ner_is_always_post_hoc_and_not_formal() -> None:
    rows = normalize_discharge_ner_records([
        {
            "mention": "pneumonia",
            "canonical_concept": "condition:pneumonia",
            "assertion": "present",
            "section": "hospital course",
        }
    ])
    assert rows[0]["evidence_phase"] == "post_hoc"
    assert rows[0]["review_status"] == "pending"
    assert rows[0]["formal_feature_eligible"] is False


def test_adapter_declares_track_and_operation() -> None:
    adapter = SnapshotAdapter(track_id="imaging_order", operation="rule_discovery")
    assert adapter.track_id == "imaging_order"
    assert adapter.operation == "rule_discovery"

