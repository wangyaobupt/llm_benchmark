"""Build deterministic task snapshots from current ``clinical_event`` rows.

The public interface deliberately has one operation.  Callers provide an event
stream and a frozen policy; timing, split, phase, field projection, leakage
checks, reason ordering, and hashing remain local to this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
from itertools import islice
import json
import re
from typing import Any, Iterable, Mapping, Pattern


SNAPSHOT_REASON_CODES: tuple[str, ...] = (
    "SNAPSHOT_NOT_YET_OCCURRED",
    "SNAPSHOT_NOT_YET_AVAILABLE",
    "SNAPSHOT_TIME_UNKNOWN",
    "SNAPSHOT_POST_HOC",
    "SNAPSHOT_ADMINISTRATIVE_END",
    "SNAPSHOT_FIELD_NOT_ALLOWED",
    "SNAPSHOT_SPLIT_FORBIDDEN",
    "SNAPSHOT_SEMANTIC_LEAKAGE",
    "SNAPSHOT_IDENTITY_LEAKAGE",
)

_REASON_ORDER = {code: index for index, code in enumerate(SNAPSHOT_REASON_CODES)}
_IDENTITY_FIELDS = (
    "subject_id",
    "hadm_id",
    "encounter_id",
    "entity_id",
    "source_row_id",
    "raw_row_ref",
    "supporting_source_row_ids",
    "supporting_raw_row_refs",
    "jsonl_line_number",
)
_DEFAULT_LEAKAGE_TEXT_FIELDS = (
    "preferred_name",
    "source_label",
    "value_text",
    "normalized_value_text",
    "value_structured_json",
)
_SOURCE_LINEAGE_USE = {
    "development": "rule_discovery",
    "validation": "threshold_validation",
    "final_test": "blind_final_evaluation",
    "engineering_audit": "engineering_audit_only",
}


class SnapshotError(ValueError):
    """Base class for fail-closed snapshot errors."""


class SnapshotConfigurationError(SnapshotError):
    """Raised when the policy cannot define an auditable snapshot."""


class SnapshotInputError(SnapshotError):
    """Raised when an event violates the snapshot input interface."""


@dataclass(frozen=True)
class SnapshotPolicy:
    """Frozen scientific policy consumed by :func:`build_snapshot`.

    ``field_whitelist`` maps each permitted ``event_kind`` to the evidence
    fields that may be exposed.  Event identifiers remain audit metadata and
    are never copied into ``visible_evidence`` unless explicitly requested;
    requesting a known identity field excludes the event.
    """

    allowed_splits: tuple[str, ...]
    subject_splits: Mapping[str, str]
    field_whitelist: Mapping[str, tuple[str, ...]]
    semantic_leakage_terms: tuple[str, ...] = ()
    semantic_leakage_fields: tuple[str, ...] = _DEFAULT_LEAKAGE_TEXT_FIELDS
    identity_forbidden_fields: tuple[str, ...] = _IDENTITY_FIELDS
    identity_leakage_fields: tuple[str, ...] = _DEFAULT_LEAKAGE_TEXT_FIELDS
    identity_leakage_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CompiledPolicy:
    source: SnapshotPolicy
    canonical: dict[str, Any]
    semantic_patterns: tuple[Pattern[str], ...]
    identity_patterns: tuple[Pattern[str], ...]


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SnapshotInputError(f"value is not canonical JSON: {exc}") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _nonempty_strings(values: Iterable[str], name: str) -> tuple[str, ...]:
    result = tuple(values)
    if not result or any(not isinstance(value, str) or not value for value in result):
        raise SnapshotConfigurationError(f"{name} must contain non-empty strings")
    if len(set(result)) != len(result):
        raise SnapshotConfigurationError(f"{name} must not contain duplicates")
    return result


def _bounded_term(term: str) -> Pattern[str]:
    normalized = " ".join(term.casefold().split())
    if not normalized:
        raise SnapshotConfigurationError("semantic leakage terms must be non-empty")
    return re.compile(rf"(?<!\w){re.escape(normalized)}(?!\w)", re.IGNORECASE)


def _compile_policy(policy: SnapshotPolicy) -> _CompiledPolicy:
    allowed_splits = _nonempty_strings(policy.allowed_splits, "allowed_splits")
    if not isinstance(policy.subject_splits, Mapping):
        raise SnapshotConfigurationError("subject_splits must be a mapping")
    subject_splits = dict(policy.subject_splits)
    if any(
        not isinstance(subject, str)
        or not subject
        or not isinstance(split, str)
        or not split
        for subject, split in subject_splits.items()
    ):
        raise SnapshotConfigurationError("subject_splits must map non-empty strings")

    if not isinstance(policy.field_whitelist, Mapping) or not policy.field_whitelist:
        raise SnapshotConfigurationError("field_whitelist must be a non-empty mapping")
    field_whitelist: dict[str, list[str]] = {}
    for event_kind, fields in policy.field_whitelist.items():
        if not isinstance(event_kind, str) or not event_kind:
            raise SnapshotConfigurationError("field_whitelist keys must be non-empty strings")
        field_whitelist[event_kind] = list(
            _nonempty_strings(fields, f"field_whitelist[{event_kind!r}]")
        )

    semantic_fields = tuple(policy.semantic_leakage_fields)
    identity_forbidden_fields = tuple(policy.identity_forbidden_fields)
    identity_fields = tuple(policy.identity_leakage_fields)
    for name, values in (
        ("semantic_leakage_fields", semantic_fields),
        ("identity_forbidden_fields", identity_forbidden_fields),
        ("identity_leakage_fields", identity_fields),
    ):
        if any(not isinstance(value, str) or not value for value in values):
            raise SnapshotConfigurationError(f"{name} must contain non-empty strings")

    semantic_terms = tuple(policy.semantic_leakage_terms)
    semantic_patterns = tuple(_bounded_term(term) for term in semantic_terms)
    try:
        identity_patterns = tuple(
            re.compile(pattern, re.IGNORECASE)
            for pattern in policy.identity_leakage_patterns
        )
    except (re.error, TypeError) as exc:
        raise SnapshotConfigurationError(f"invalid identity leakage pattern: {exc}") from exc

    canonical = {
        "allowed_splits": sorted(allowed_splits),
        "subject_splits": dict(sorted(subject_splits.items())),
        "field_whitelist": {
            kind: sorted(fields) for kind, fields in sorted(field_whitelist.items())
        },
        "semantic_leakage_terms": sorted(
            " ".join(term.casefold().split()) for term in semantic_terms
        ),
        "semantic_leakage_fields": sorted(semantic_fields),
        "identity_forbidden_fields": sorted(identity_forbidden_fields),
        "identity_leakage_fields": sorted(identity_fields),
        "identity_leakage_patterns": sorted(policy.identity_leakage_patterns),
    }
    normalized_policy = SnapshotPolicy(
        allowed_splits=allowed_splits,
        subject_splits=subject_splits,
        field_whitelist={key: tuple(value) for key, value in field_whitelist.items()},
        semantic_leakage_terms=semantic_terms,
        semantic_leakage_fields=semantic_fields,
        identity_forbidden_fields=identity_forbidden_fields,
        identity_leakage_fields=identity_fields,
        identity_leakage_patterns=tuple(policy.identity_leakage_patterns),
    )
    return _CompiledPolicy(
        source=normalized_policy,
        canonical=canonical,
        semantic_patterns=semantic_patterns,
        identity_patterns=identity_patterns,
    )


def _validated_source_lineage(value: Mapping[str, Any] | None) -> dict[str, str] | None:
    if value is None:
        return None
    required = {
        "protocol_lock_sha256",
        "subject_split_manifest_sha256",
        "encounter_boundary_manifest_sha256",
        "encounter_boundary_manifest_hmac_sha256",
        "boundary_source_inputs_sha256",
        "boundary_reference_key_id",
        "journey_id",
        "subject_role",
        "permitted_use",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise SnapshotConfigurationError(
            "source_lineage must contain exactly the formal boundary lineage fields"
        )
    for field in (
        "protocol_lock_sha256",
        "subject_split_manifest_sha256",
        "encounter_boundary_manifest_sha256",
        "encounter_boundary_manifest_hmac_sha256",
        "boundary_source_inputs_sha256",
    ):
        if not isinstance(value[field], str) or not re.fullmatch(
            r"[0-9a-f]{64}", value[field]
        ):
            raise SnapshotConfigurationError(f"source_lineage.{field} must be SHA-256")
    if not isinstance(value["journey_id"], str) or not re.fullmatch(
        r"journey_[0-9a-f]{64}", value["journey_id"]
    ):
        raise SnapshotConfigurationError("source_lineage.journey_id is invalid")
    if not isinstance(value["boundary_reference_key_id"], str) or not value[
        "boundary_reference_key_id"
    ]:
        raise SnapshotConfigurationError(
            "source_lineage.boundary_reference_key_id is invalid"
        )
    role = value["subject_role"]
    if role not in _SOURCE_LINEAGE_USE:
        raise SnapshotConfigurationError("source_lineage.subject_role is invalid")
    if value["permitted_use"] != _SOURCE_LINEAGE_USE[role]:
        raise SnapshotConfigurationError("source_lineage role/use mismatch")
    return {field: value[field] for field in sorted(required)}


def _parse_time(value: Any, field: str, event_id: str | None = None) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise SnapshotInputError(f"{field} must be an ISO string or null for {event_id or 'snapshot'}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SnapshotInputError(f"invalid {field} for {event_id or 'snapshot'}: {value}") from exc
    if parsed.tzinfo is not None and parsed.utcoffset() is not None:
        raise SnapshotInputError(f"{field} must use the naive MIMIC timeline for {event_id or 'snapshot'}")
    return parsed


def _canonical_time(value: str | datetime) -> tuple[str, datetime]:
    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is not None and parsed.utcoffset() is not None:
            raise SnapshotConfigurationError("index_time must use the naive MIMIC timeline")
    else:
        try:
            parsed = _parse_time(value, "index_time")
        except SnapshotInputError as exc:
            raise SnapshotConfigurationError(str(exc)) from exc
        if parsed is None:
            raise SnapshotConfigurationError("index_time is required")
    return parsed.isoformat(timespec="microseconds"), parsed


def _iter_batches(events: Iterable[Mapping[str, Any]], batch_size: int) -> Iterable[list[Mapping[str, Any]]]:
    iterator = iter(events)
    while batch := list(islice(iterator, batch_size)):
        yield batch


def _text_values(evidence: Mapping[str, Any], fields: Iterable[str]) -> Iterable[str]:
    for field in fields:
        value = evidence.get(field)
        if isinstance(value, str):
            yield " ".join(value.casefold().split())
        elif isinstance(value, (list, tuple)):
            yield " ".join(str(item).casefold() for item in value)


def _classify_event(
    event: Mapping[str, Any],
    index_time: datetime,
    policy: _CompiledPolicy,
) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        raise SnapshotInputError("each event must be a mapping")
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        raise SnapshotInputError("each event must have a non-empty event_id")
    for field in ("subject_id", "event_kind", "evidence_phase"):
        if field not in event:
            raise SnapshotInputError(f"missing {field} for {event_id}")

    reasons: set[str] = set()
    event_time = _parse_time(event.get("event_time"), "event_time", event_id)
    available_time = _parse_time(event.get("available_time"), "available_time", event_id)
    if event_time is None or available_time is None:
        reasons.add("SNAPSHOT_TIME_UNKNOWN")
    if event_time is not None and event_time > index_time:
        reasons.add("SNAPSHOT_NOT_YET_OCCURRED")
    if available_time is not None and available_time > index_time:
        reasons.add("SNAPSHOT_NOT_YET_AVAILABLE")

    phase = event["evidence_phase"]
    if phase not in {"source_event", "post_hoc", "administrative_end"}:
        raise SnapshotInputError(f"invalid evidence_phase for {event_id}: {phase!r}")
    if phase == "post_hoc":
        reasons.add("SNAPSHOT_POST_HOC")
    elif phase == "administrative_end":
        reasons.add("SNAPSHOT_ADMINISTRATIVE_END")

    split = policy.source.subject_splits.get(str(event["subject_id"]))
    if split not in policy.source.allowed_splits:
        reasons.add("SNAPSHOT_SPLIT_FORBIDDEN")

    event_kind = event["event_kind"]
    if not isinstance(event_kind, str) or not event_kind:
        raise SnapshotInputError(f"event_kind must be a non-empty string for {event_id}")
    fields = policy.source.field_whitelist.get(str(event_kind))
    evidence: dict[str, Any] = {}
    if not fields:
        reasons.add("SNAPSHOT_FIELD_NOT_ALLOWED")
    else:
        missing_fields = [field for field in fields if field not in event]
        if missing_fields:
            raise SnapshotInputError(
                f"whitelisted fields missing for {event_id}: {sorted(missing_fields)}"
            )
        evidence = {field: event[field] for field in sorted(fields)}

        if set(fields).intersection(policy.source.identity_forbidden_fields):
            reasons.add("SNAPSHOT_IDENTITY_LEAKAGE")
        semantic_values = tuple(
            _text_values(evidence, policy.source.semantic_leakage_fields)
        )
        if any(
            pattern.search(value)
            for pattern in policy.semantic_patterns
            for value in semantic_values
        ):
            reasons.add("SNAPSHOT_SEMANTIC_LEAKAGE")
        identity_values = tuple(
            _text_values(evidence, policy.source.identity_leakage_fields)
        )
        if any(
            pattern.search(value)
            for pattern in policy.identity_patterns
            for value in identity_values
        ):
            reasons.add("SNAPSHOT_IDENTITY_LEAKAGE")

    ordered_reasons = sorted(reasons, key=_REASON_ORDER.__getitem__)
    excluded = bool(ordered_reasons)
    return {
        "event_id": event_id,
        "source_event_sha256": _sha256(dict(event)),
        "visibility_status": "excluded" if excluded else "visible",
        "exclusion_reason_codes": ordered_reasons,
        "visible_evidence": None if excluded else evidence,
    }


def _build_snapshot(
    events: Iterable[Mapping[str, Any]],
    *,
    index_time: str | datetime,
    policy: SnapshotPolicy,
    batch_size: int = 1024,
    source_lineage: Mapping[str, Any] | None = None,
    authentication_secret: bytes | str | None = None,
) -> dict[str, Any]:
    """Return an auditable snapshot manifest without reading or writing files.

    Input order and ``batch_size`` are runtime details and therefore do not
    affect ``snapshot_sha256``.  Malformed input raises instead of silently
    weakening a scientific exclusion rule.
    """
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
        raise SnapshotConfigurationError("batch_size must be a positive integer")
    compiled = _compile_policy(policy)
    checked_lineage = _validated_source_lineage(source_lineage)
    if (checked_lineage is None) != (authentication_secret is None):
        raise SnapshotConfigurationError(
            "authenticated source_lineage and authentication_secret are required together"
        )
    if isinstance(authentication_secret, str):
        authentication_secret = authentication_secret.encode("utf-8")
    if authentication_secret is not None and (
        not isinstance(authentication_secret, bytes)
        or len(authentication_secret) < 32
    ):
        raise SnapshotConfigurationError(
            "authentication_secret must contain at least 32 bytes"
        )
    canonical_index_time, parsed_index_time = _canonical_time(index_time)

    records: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    for batch in _iter_batches(events, batch_size):
        for event in batch:
            record = _classify_event(event, parsed_index_time, compiled)
            if record["event_id"] in event_ids:
                raise SnapshotInputError(f"duplicate event_id: {record['event_id']}")
            event_ids.add(record["event_id"])
            records.append(record)
    records.sort(key=lambda record: record["event_id"])

    reason_counts = {code: 0 for code in SNAPSHOT_REASON_CODES}
    for record in records:
        for code in record["exclusion_reason_codes"]:
            reason_counts[code] += 1
    visible_count = sum(record["visibility_status"] == "visible" for record in records)
    body = {
        "schema_version": "snapshot-manifest/1.1.0",
        "lineage_status": (
            "boundary_authenticated"
            if checked_lineage is not None
            else "generic_unverified"
        ),
        "index_time": canonical_index_time,
        "policy_sha256": _sha256(compiled.canonical),
        **(
            {"source_lineage": checked_lineage}
            if checked_lineage is not None
            else {}
        ),
        "counts": {
            "total": len(records),
            "visible": visible_count,
            "excluded": len(records) - visible_count,
            "exclusion_reason_counts": reason_counts,
        },
        "events": records,
    }
    manifest = {**body, "snapshot_sha256": _sha256(body)}
    if authentication_secret is not None:
        manifest["snapshot_hmac_sha256"] = hmac.new(
            authentication_secret,
            b"boundary-authenticated-snapshot/1.0.0\x00" + _canonical_bytes(body),
            hashlib.sha256,
        ).hexdigest()
    return manifest


def build_snapshot(
    events: Iterable[Mapping[str, Any]],
    *,
    index_time: str | datetime,
    policy: SnapshotPolicy,
    batch_size: int = 1024,
) -> dict[str, Any]:
    """Build a generic snapshot that cannot claim authenticated formal lineage."""
    return _build_snapshot(
        events,
        index_time=index_time,
        policy=policy,
        batch_size=batch_size,
    )
