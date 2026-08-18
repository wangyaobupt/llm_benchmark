"""Build deterministic decision-document, evidence, and target tables."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping


TARGET_EVIDENCE_OVERLAP = "DECISION_TARGET_EVIDENCE_OVERLAP"
TARGET_WINDOW_INVALID = "DECISION_TARGET_WINDOW_INVALID"
SPLIT_FORBIDDEN = "DECISION_SPLIT_FORBIDDEN"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class DecisionDocumentError(ValueError):
    """Raised when a decision corpus cannot be built without leakage."""


@dataclass(frozen=True)
class DecisionDocumentResult:
    documents: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    targets: list[dict[str, Any]]
    exclusions: list[dict[str, Any]]
    manifest: dict[str, Any]


def _episode_map(episodes: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for episode in episodes:
        episode_id = episode.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            raise DecisionDocumentError("each episode requires episode_id")
        if episode_id in result:
            raise DecisionDocumentError(f"duplicate episode_id: {episode_id}")
        result[episode_id] = episode
    return result


def build_decision_documents(
    decision_nodes: Iterable[Mapping[str, Any]],
    episodes: Iterable[Mapping[str, Any]],
) -> DecisionDocumentResult:
    """Build three canonical tables from snapshot-backed decision nodes.

    A node must carry a boundary-authenticated snapshot and its lineage hashes.
    Target episodes are referenced explicitly; no target is inferred from
    temporal proximity inside this function.
    """
    episode_by_id = _episode_map(episodes)
    documents: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    target_rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for node_index, node in enumerate(decision_nodes):
        decision_id = node.get("decision_id")
        required = ("decision_id", "subject_ref", "journey_id", "index_time", "track_id", "candidate_class", "snapshot")
        missing = [field for field in required if not node.get(field)]
        if missing:
            raise DecisionDocumentError(f"decision node {node_index} missing fields: {missing}")
        if not isinstance(decision_id, str) or decision_id in seen_ids:
            raise DecisionDocumentError(f"duplicate or invalid decision_id: {decision_id}")
        seen_ids.add(decision_id)
        snapshot = node["snapshot"]
        if snapshot.get("lineage_status") != "boundary_authenticated":
            exclusions.append({"decision_id": decision_id, "reason_codes": [SPLIT_FORBIDDEN]})
            continue
        snapshot_events = snapshot.get("events")
        if not isinstance(snapshot_events, list):
            raise DecisionDocumentError(f"snapshot events missing for {decision_id}")
        target_ids = list(node.get("target_episode_ids") or [])
        if len(target_ids) != len(set(target_ids)):
            raise DecisionDocumentError(f"duplicate target episode IDs for {decision_id}")
        missing_targets = [episode_id for episode_id in target_ids if episode_id not in episode_by_id]
        if missing_targets:
            exclusions.append({"decision_id": decision_id, "reason_codes": [TARGET_WINDOW_INVALID], "missing_episode_ids": missing_targets})
            continue
        evidence_ids = {row.get("event_id") for row in snapshot_events if row.get("visibility_status") == "visible"}
        target_event_ids = {
            event_id
            for episode_id in target_ids
            for event_id in (episode_by_id[episode_id].get("source_event_ids") or [])
        }
        if evidence_ids & target_event_ids:
            exclusions.append({
                "decision_id": decision_id,
                "reason_codes": [TARGET_EVIDENCE_OVERLAP],
                "overlap_event_ids": sorted(evidence_ids & target_event_ids),
            })
            continue
        lineage = snapshot.get("source_lineage") or {}
        document = {
            "decision_id": decision_id,
            "subject_ref": str(node["subject_ref"]),
            "journey_id": str(node["journey_id"]),
            "index_time": str(node["index_time"]),
            "track_id": str(node["track_id"]),
            "candidate_class": str(node["candidate_class"]),
            "target_window": node.get("target_window"),
            "observation_window": node.get("observation_window"),
            "snapshot_sha256": snapshot.get("snapshot_sha256"),
            "protocol_lock_sha256": lineage.get("protocol_lock_sha256"),
            "subject_split_manifest_sha256": lineage.get("subject_split_manifest_sha256"),
            "encounter_boundary_manifest_sha256": lineage.get("encounter_boundary_manifest_sha256"),
            "input_manifest_sha256": node.get("input_manifest_sha256"),
            "zero_candidate_observed": len(target_ids) == 0,
        }
        documents.append(document)
        for snapshot_row in sorted(snapshot_events, key=lambda row: str(row.get("event_id", ""))):
            if snapshot_row.get("visibility_status") != "visible":
                continue
            evidence_rows.append({
                "decision_id": decision_id,
                "event_id": snapshot_row["event_id"],
                "visible_evidence": snapshot_row.get("visible_evidence"),
            })
        for episode_id in sorted(target_ids):
            episode = episode_by_id[episode_id]
            target_rows.append({
                "decision_id": decision_id,
                "episode_id": episode_id,
                "candidate_id": episode.get("candidate_id"),
                "candidate_level": episode.get("candidate_level"),
                "target_occurrence_time": episode.get("occurrence_time"),
                "target_available_time": episode.get("available_time"),
                "target_semantics": episode.get("track_id"),
                "is_primary_target": True,
            })
    documents.sort(key=lambda row: row["decision_id"])
    evidence_rows.sort(key=lambda row: (row["decision_id"], row["event_id"]))
    target_rows.sort(key=lambda row: (row["decision_id"], row["episode_id"]))
    body = {
        "schema_version": "decision-document-corpus/1.0.0",
        "counts": {
            "documents": len(documents),
            "evidence": len(evidence_rows),
            "targets": len(target_rows),
            "zero_candidate_documents": sum(row["zero_candidate_observed"] for row in documents),
            "excluded": len(exclusions),
        },
        "tables": {"documents": documents, "evidence": evidence_rows, "targets": target_rows},
        "exclusions": exclusions,
    }
    manifest = {**body, "corpus_sha256": _hash(body)}
    return DecisionDocumentResult(documents, evidence_rows, target_rows, exclusions, manifest)

