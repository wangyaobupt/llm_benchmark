"""Thin adapter over the authenticated snapshot implementation.

This module owns the investigation-selection track boundary, but delegates all
occurrence/availability/phase/split checks to ``evaluation_pipeline.snapshot``.
It intentionally has no time-comparison implementation of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from evaluation_pipeline.snapshot import (
    SnapshotPolicy,
    audit_authenticated_snapshot,
    build_snapshot_from_boundary,
)


@dataclass(frozen=True)
class SnapshotAdapter:
    track_id: str
    operation: str

    def build(
        self,
        events: Iterable[Mapping[str, Any]],
        *,
        boundary_manifest: Mapping[str, Any],
        reference_secret: bytes | str,
        protocol_lock_sha256: str,
        public_split_manifest_sha256: str,
        source_inputs_sha256: str,
        journey_id: str,
        index_time: str,
        policy: SnapshotPolicy,
    ) -> dict[str, Any]:
        snapshot = build_snapshot_from_boundary(
            events,
            boundary_manifest=boundary_manifest,
            reference_secret=reference_secret,
            expected_protocol_lock_sha256=protocol_lock_sha256,
            expected_public_manifest_sha256=public_split_manifest_sha256,
            expected_source_inputs_sha256=source_inputs_sha256,
            journey_id=journey_id,
            operation=self.operation,
            index_time=index_time,
            policy=policy,
        )
        return snapshot

    def audit(
        self,
        snapshot: Mapping[str, Any],
        *,
        boundary_manifest: Mapping[str, Any],
        reference_secret: bytes | str,
        protocol_lock_sha256: str,
        public_split_manifest_sha256: str,
        source_inputs_sha256: str,
        journey_id: str,
    ) -> dict[str, Any]:
        return audit_authenticated_snapshot(
            snapshot,
            boundary_manifest=boundary_manifest,
            reference_secret=reference_secret,
            expected_protocol_lock_sha256=protocol_lock_sha256,
            expected_public_manifest_sha256=public_split_manifest_sha256,
            expected_source_inputs_sha256=source_inputs_sha256,
            expected_journey_id=journey_id,
            expected_operation=self.operation,
        )


def normalize_discharge_ner_records(
    records: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize NER output for audit/error analysis only.

    Discharge mentions are always post-hoc.  Missing review metadata is
    explicitly pending; this function never promotes an annotation to a
    formal feature or snapshot evidence.
    """
    normalized: list[dict[str, Any]] = []
    for record in records:
        row = dict(record)
        required = ("mention", "canonical_concept", "assertion", "section")
        missing = [field for field in required if field not in row]
        if missing:
            raise ValueError(f"discharge NER record missing fields: {missing}")
        row["evidence_phase"] = "post_hoc"
        row["review_status"] = row.get("review_status", "pending")
        row["formal_feature_eligible"] = False
        normalized.append(row)
    return normalized
