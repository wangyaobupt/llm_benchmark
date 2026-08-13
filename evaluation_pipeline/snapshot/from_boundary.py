"""Authenticate an encounter boundary and build one journey decision snapshot."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator

from evaluation_pipeline.journey import audit_encounter_boundary_manifest

from .visibility import SNAPSHOT_REASON_CODES, SnapshotPolicy, _build_snapshot


CLINICAL_EVENT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "data_pipeline"
    / "event_pipeline"
    / "event_contracts"
    / "schemas"
    / "clinical-event.schema.json"
)
SNAPSHOT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schemas" / "snapshot-manifest.schema.json"
)


class BoundarySnapshotError(ValueError):
    """Raised when boundary lineage or joined clinical events are not trustworthy."""


def _secret(value: bytes | str) -> bytes:
    if isinstance(value, str):
        value = value.encode("utf-8")
    if not isinstance(value, bytes) or len(value) < 32:
        raise BoundarySnapshotError("reference_secret must contain at least 32 bytes")
    return value


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise BoundarySnapshotError(f"value is not canonical JSON: {error}") from error


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _reference(secret: bytes, kind: str, *parts: Any) -> str:
    payload = _canonical_bytes({"kind": kind, "parts": list(parts)})
    return f"{kind}_" + hmac.new(secret, payload, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class AuthenticatedBoundaryContext:
    """One-time authenticated indexes reused across all journey snapshots."""

    _reference_secret: bytes = field(repr=False, compare=False)
    _journey_bytes: Mapping[str, bytes] = field(repr=False)
    _event_records_by_journey: Mapping[str, tuple[tuple[bytes, str], ...]] = field(
        repr=False
    )
    _subject_splits_by_journey: Mapping[str, Mapping[str, str]] = field(repr=False)
    _source_lineage_base: Mapping[str, str] = field(repr=False)

    def build_snapshot(
        self,
        journey_id: str,
        *,
        operation: str,
        index_time: str,
        policy: SnapshotPolicy,
        batch_size: int = 1024,
    ) -> dict[str, Any]:
        journey_bytes = self._journey_bytes.get(journey_id)
        if journey_bytes is None:
            raise BoundarySnapshotError(
                "journey_id is not present in the boundary manifest"
            )
        journey = json.loads(journey_bytes)
        if operation != self._source_lineage_base["permitted_use"]:
            raise BoundarySnapshotError(
                "operation is not permitted for the boundary subject role"
            )
        try:
            parsed_index_time = datetime.fromisoformat(index_time)
            journey_start = datetime.fromisoformat(journey["journey_start_time"])
            journey_end = datetime.fromisoformat(journey["discharge_time"])
        except (TypeError, ValueError) as error:
            raise BoundarySnapshotError(
                f"index or journey boundary time is invalid: {error}"
            ) from error
        if any(
            value.tzinfo is not None and value.utcoffset() is not None
            for value in (parsed_index_time, journey_start, journey_end)
        ):
            raise BoundarySnapshotError(
                "index and journey times must use the naive MIMIC timeline"
            )
        if not journey_start <= parsed_index_time <= journey_end:
            raise BoundarySnapshotError(
                "index_time is outside the selected journey boundary"
            )
        if set(policy.allowed_splits) != {self._source_lineage_base["subject_role"]}:
            raise BoundarySnapshotError(
                "snapshot allowed_splits must contain only the authenticated boundary role"
            )
        if dict(policy.subject_splits) != dict(
            self._subject_splits_by_journey[journey_id]
        ):
            raise BoundarySnapshotError(
                "snapshot subject_splits must exactly match authenticated joined events"
            )
        source_lineage = {
            **self._source_lineage_base,
            "journey_id": journey_id,
        }
        events: list[dict[str, Any]] = []
        for event_bytes, expected_hash in self._event_records_by_journey[journey_id]:
            event = json.loads(event_bytes)
            if _sha256(event) != expected_hash:
                raise BoundarySnapshotError(
                    f"authenticated context event hash mismatch: {event.get('event_id')}"
                )
            events.append(event)
        return _build_snapshot(
            events,
            index_time=index_time,
            policy=policy,
            batch_size=batch_size,
            source_lineage=source_lineage,
            authentication_secret=self._reference_secret,
        )


def authenticate_boundary_context(
    events: Iterable[Mapping[str, Any]],
    *,
    boundary_manifest: Mapping[str, Any],
    reference_secret: bytes | str,
    expected_protocol_lock_sha256: str,
    expected_public_manifest_sha256: str,
    expected_source_inputs_sha256: str,
) -> AuthenticatedBoundaryContext:
    """Authenticate once and index all journeys, assignments, and source events."""
    secret = _secret(reference_secret)
    trusted_boundary = json.loads(_canonical_bytes(boundary_manifest))
    audit = audit_encounter_boundary_manifest(
        trusted_boundary,
        reference_secret=secret,
        expected_protocol_lock_sha256=expected_protocol_lock_sha256,
        expected_public_manifest_sha256=expected_public_manifest_sha256,
        expected_source_inputs_sha256=expected_source_inputs_sha256,
    )
    if not audit["valid"]:
        raise BoundarySnapshotError(
            "encounter boundary audit failed: "
            + json.dumps(audit["errors"], ensure_ascii=False)
        )
    lineage = trusted_boundary["split_lineage"]
    journeys = {row["journey_id"]: row for row in trusted_boundary["journeys"]}
    for journey in journeys.values():
        if journey["subject_role"] != lineage["subject_role"]:
            raise BoundarySnapshotError("journey role differs from boundary lineage")
    assignments = {
        row["event_id"]: row for row in trusted_boundary["event_assignments"]
    }
    try:
        schema = json.loads(CLINICAL_EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
    except Exception as error:
        raise BoundarySnapshotError(
            f"clinical-event schema unavailable or invalid: {error}"
        ) from error
    joined: dict[str, list[dict[str, Any]]] = {key: [] for key in journeys}
    subject_splits: dict[str, dict[str, str]] = {key: {} for key in journeys}
    seen_event_ids: set[str] = set()
    found_assignment_ids: set[str] = set()
    for event in events:
        if not isinstance(event, Mapping):
            raise BoundarySnapshotError("each source event must be an object")
        trusted_event = json.loads(_canonical_bytes(event))
        event_id = trusted_event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise BoundarySnapshotError("each source event must have a non-empty event_id")
        if event_id in seen_event_ids:
            raise BoundarySnapshotError(f"duplicate source event_id: {event_id}")
        seen_event_ids.add(event_id)
        assignment = assignments.get(event_id)
        if assignment is None:
            continue
        schema_errors = sorted(
            validator.iter_errors(trusted_event), key=lambda error: list(error.absolute_path)
        )
        if schema_errors:
            raise BoundarySnapshotError(
                f"source event {event_id} violates clinical-event schema: "
                + "; ".join(error.message for error in schema_errors)
            )
        if _sha256(trusted_event) != assignment["source_event_sha256"]:
            raise BoundarySnapshotError(
                f"source event hash differs from boundary assignment: {event_id}"
            )
        expected_journey_id = _reference(
            secret, "journey", trusted_event["subject_id"], trusted_event["hadm_id"]
        )
        if assignment["journey_id"] != expected_journey_id:
            raise BoundarySnapshotError(
                f"source event does not belong to assigned journey: {event_id}"
            )
        for field in ("event_time", "available_time", "time_precision"):
            if assignment[field] != trusted_event[field]:
                raise BoundarySnapshotError(
                    f"boundary assignment {field} differs from source event: {event_id}"
                )
        expected_time_group_id = None
        if trusted_event["time_precision"] in {"second", "subsecond"}:
            canonical_event_time = datetime.fromisoformat(trusted_event["event_time"]).isoformat(
                timespec="microseconds"
            )
            expected_time_group_id = _reference(
                secret,
                "time_group",
                expected_journey_id,
                canonical_event_time,
                trusted_event["time_precision"],
            )
        if assignment["time_group_id"] != expected_time_group_id:
            raise BoundarySnapshotError(
                f"boundary assignment time_group_id differs from source event: {event_id}"
            )
        journey_id = assignment["journey_id"]
        if journey_id not in journeys:
            raise BoundarySnapshotError("assignment references an unknown journey")
        subject_id = str(trusted_event["subject_id"])
        subject_splits[journey_id][subject_id] = lineage["subject_role"]
        joined[journey_id].append(trusted_event)
        found_assignment_ids.add(event_id)
    missing = sorted(set(assignments) - found_assignment_ids)
    if missing:
        raise BoundarySnapshotError(
            f"boundary assignments are missing exact source events: {missing}"
        )
    return AuthenticatedBoundaryContext(
        _reference_secret=secret,
        _journey_bytes=MappingProxyType(
            {key: _canonical_bytes(value) for key, value in journeys.items()}
        ),
        _event_records_by_journey=MappingProxyType(
            {
                key: tuple(
                    (_canonical_bytes(row), _sha256(row))
                    for row in sorted(value, key=lambda row: row["event_id"])
                )
                for key, value in joined.items()
            }
        ),
        _subject_splits_by_journey=MappingProxyType(
            {
                key: MappingProxyType(dict(value))
                for key, value in subject_splits.items()
            }
        ),
        _source_lineage_base=MappingProxyType(
            {
                "protocol_lock_sha256": lineage["protocol_lock_sha256"],
                "subject_split_manifest_sha256": lineage["public_manifest_sha256"],
                "encounter_boundary_manifest_sha256": trusted_boundary["manifest_sha256"],
                "encounter_boundary_manifest_hmac_sha256": trusted_boundary["manifest_hmac_sha256"],
                "boundary_source_inputs_sha256": trusted_boundary["source_inputs_sha256"],
                "boundary_reference_key_id": trusted_boundary["reference_key_id"],
                "subject_role": lineage["subject_role"],
                "permitted_use": lineage["permitted_use"],
            }
        ),
    )


def build_snapshot_from_boundary(
    events: Iterable[Mapping[str, Any]],
    *,
    boundary_manifest: Mapping[str, Any],
    reference_secret: bytes | str,
    expected_protocol_lock_sha256: str,
    expected_public_manifest_sha256: str,
    expected_source_inputs_sha256: str,
    journey_id: str,
    operation: str,
    index_time: str,
    policy: SnapshotPolicy,
    batch_size: int = 1024,
) -> dict[str, Any]:
    """One-off wrapper; reuse :func:`authenticate_boundary_context` for batches."""
    context = authenticate_boundary_context(
        events,
        boundary_manifest=boundary_manifest,
        reference_secret=reference_secret,
        expected_protocol_lock_sha256=expected_protocol_lock_sha256,
        expected_public_manifest_sha256=expected_public_manifest_sha256,
        expected_source_inputs_sha256=expected_source_inputs_sha256,
    )
    return context.build_snapshot(
        journey_id,
        operation=operation,
        index_time=index_time,
        policy=policy,
        batch_size=batch_size,
    )


def audit_authenticated_snapshot(
    snapshot: Mapping[str, Any],
    *,
    boundary_manifest: Mapping[str, Any],
    reference_secret: bytes | str,
    expected_protocol_lock_sha256: str,
    expected_public_manifest_sha256: str,
    expected_source_inputs_sha256: str,
    expected_journey_id: str,
    expected_operation: str,
) -> dict[str, Any]:
    """Independently authenticate boundary, snapshot, lineage, and event set."""
    errors: list[str] = []
    try:
        secret = _secret(reference_secret)
    except BoundarySnapshotError as error:
        secret = b""
        errors.append(str(error))
    boundary_audit = audit_encounter_boundary_manifest(
        boundary_manifest,
        reference_secret=reference_secret,
        expected_protocol_lock_sha256=expected_protocol_lock_sha256,
        expected_public_manifest_sha256=expected_public_manifest_sha256,
        expected_source_inputs_sha256=expected_source_inputs_sha256,
    )
    if not boundary_audit["valid"]:
        errors.extend(
            f"boundary:{error}" for error in boundary_audit["errors"]
        )
    lineage = boundary_manifest.get("split_lineage", {})
    selected_journey = next(
        (
            row
            for row in boundary_manifest.get("journeys", [])
            if isinstance(row, Mapping)
            and row.get("journey_id") == expected_journey_id
        ),
        None,
    )
    expected_lineage = {
        "protocol_lock_sha256": expected_protocol_lock_sha256,
        "subject_split_manifest_sha256": expected_public_manifest_sha256,
        "encounter_boundary_manifest_sha256": boundary_manifest.get("manifest_sha256"),
        "encounter_boundary_manifest_hmac_sha256": boundary_manifest.get("manifest_hmac_sha256"),
        "boundary_source_inputs_sha256": expected_source_inputs_sha256,
        "boundary_reference_key_id": boundary_manifest.get("reference_key_id"),
        "journey_id": expected_journey_id,
        "subject_role": lineage.get("subject_role"),
        "permitted_use": expected_operation,
    }
    if lineage.get("permitted_use") != expected_operation:
        errors.append("expected operation differs from boundary lineage")
    if selected_journey is None:
        errors.append("expected journey is absent from boundary manifest")
    else:
        try:
            index_time = datetime.fromisoformat(snapshot.get("index_time"))
            journey_start = datetime.fromisoformat(
                selected_journey["journey_start_time"]
            )
            journey_end = datetime.fromisoformat(selected_journey["discharge_time"])
        except (KeyError, TypeError, ValueError) as error:
            errors.append(f"snapshot or journey boundary time is invalid: {error}")
        else:
            if any(
                value.tzinfo is not None and value.utcoffset() is not None
                for value in (index_time, journey_start, journey_end)
            ):
                errors.append("snapshot and journey times must use the naive MIMIC timeline")
            elif not journey_start <= index_time <= journey_end:
                errors.append("snapshot index_time is outside the selected journey boundary")
    try:
        schema = json.loads(SNAPSHOT_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        errors.extend(
            f"schema:{'.'.join(map(str, error.absolute_path)) or '$'}:{error.message}"
            for error in Draft202012Validator(schema).iter_errors(snapshot)
        )
    except Exception as error:
        errors.append(f"snapshot schema unavailable or invalid: {error}")
    body = {
        key: value
        for key, value in snapshot.items()
        if key not in {"snapshot_sha256", "snapshot_hmac_sha256"}
    }
    if snapshot.get("lineage_status") != "boundary_authenticated":
        errors.append("snapshot is not boundary_authenticated")
    if snapshot.get("snapshot_sha256") != _sha256(body):
        errors.append("snapshot_sha256 mismatch")
    if secret:
        expected_hmac = hmac.new(
            secret,
            b"boundary-authenticated-snapshot/1.0.0\x00" + _canonical_bytes(body),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(
            str(snapshot.get("snapshot_hmac_sha256")), expected_hmac
        ):
            errors.append("snapshot_hmac_sha256 mismatch")
    if snapshot.get("source_lineage") != expected_lineage:
        errors.append("snapshot source lineage mismatch")
    expected_assignments = {
        row["event_id"]: row["source_event_sha256"]
        for row in boundary_manifest.get("event_assignments", [])
        if isinstance(row, Mapping) and row.get("journey_id") == expected_journey_id
    }
    snapshot_events = snapshot.get("events", [])
    if not isinstance(snapshot_events, list):
        snapshot_events = []
        errors.append("snapshot events must be an array")
    event_ids = [
        row.get("event_id") for row in snapshot_events if isinstance(row, Mapping)
    ]
    if len(event_ids) != len(set(event_ids)):
        errors.append("duplicate snapshot event_id")
    observed_events = {
        row.get("event_id"): row.get("source_event_sha256")
        for row in snapshot_events
        if isinstance(row, Mapping)
    }
    if (
        len(snapshot_events) != len(expected_assignments)
        or observed_events != expected_assignments
    ):
        errors.append("snapshot event set differs from boundary assignments")
    reason_counts = {code: 0 for code in SNAPSHOT_REASON_CODES}
    visible_count = 0
    for row in snapshot_events:
        if not isinstance(row, Mapping):
            errors.append("snapshot event row must be an object")
            continue
        if row.get("visibility_status") == "visible":
            visible_count += 1
        for code in row.get("exclusion_reason_codes", []):
            if code in reason_counts:
                reason_counts[code] += 1
            else:
                errors.append(f"unknown snapshot reason code: {code}")
    expected_counts = {
        "total": len(snapshot_events),
        "visible": visible_count,
        "excluded": len(snapshot_events) - visible_count,
        "exclusion_reason_counts": reason_counts,
    }
    if snapshot.get("counts") != expected_counts:
        errors.append("snapshot counts do not match event decisions")
    return {
        "schema_version": "authenticated-snapshot-audit/1.0.0",
        "valid": not errors,
        "errors": sorted(set(errors)),
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
    }
