import pytest

from data_pipeline.investigation_selection.decision_documents import (
    DecisionDocumentError,
    build_decision_documents,
)


def _snapshot(*, event_id="e1", overlap=False):
    source_event_id = "target-event" if overlap else event_id
    return {
        "lineage_status": "boundary_authenticated",
        "snapshot_sha256": "a" * 64,
        "source_lineage": {
            "protocol_lock_sha256": "b" * 64,
            "subject_split_manifest_sha256": "c" * 64,
            "encounter_boundary_manifest_sha256": "d" * 64,
        },
        "events": [{"event_id": source_event_id, "visibility_status": "visible", "visible_evidence": {"concept": "chest pain"}}],
    }


def _episode(episode_id="ep1", source_event_ids=None):
    return {"episode_id": episode_id, "track_id": "imaging_order", "candidate_id": "cand:ct", "candidate_level": "modality", "source_event_ids": source_event_ids or ["order-event"], "occurrence_time": "2100-01-01 08:10:00", "available_time": "2100-01-01 08:10:00"}


def _node(snapshot, target_episode_ids=None):
    return {"decision_id": "decision:1", "subject_ref": "sub:1", "journey_id": "journey:1", "index_time": "2100-01-01 08:00:00", "track_id": "imaging_order", "candidate_class": "imaging", "snapshot": snapshot, "target_episode_ids": target_episode_ids or [], "target_window": "15m", "observation_window": "4h", "input_manifest_sha256": "e" * 64}


def test_zero_target_document_is_retained() -> None:
    result = build_decision_documents([_node(_snapshot())], [_episode()])
    assert len(result.documents) == 1
    assert result.documents[0]["zero_candidate_observed"] is True
    assert result.targets == []


def test_target_evidence_overlap_is_excluded() -> None:
    result = build_decision_documents([_node(_snapshot(event_id="target-event"), ["ep1"])], [_episode(source_event_ids=["target-event"])])
    assert result.documents == []
    assert result.exclusions[0]["reason_codes"] == ["DECISION_TARGET_EVIDENCE_OVERLAP"]


def test_non_authenticated_snapshot_is_not_formal_document() -> None:
    result = build_decision_documents([_node({"lineage_status": "generic_unverified", "events": []})], [])
    assert result.documents == []
    assert result.exclusions[0]["reason_codes"] == ["DECISION_SPLIT_FORBIDDEN"]


def test_duplicate_decision_ids_fail_closed() -> None:
    with pytest.raises(DecisionDocumentError):
        build_decision_documents([_node(_snapshot()), _node(_snapshot())], [_episode()])

