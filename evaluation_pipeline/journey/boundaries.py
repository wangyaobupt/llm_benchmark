"""Build deterministic admission-centric encounter boundaries.

The public interface accepts context rows and current clinical events in one
``EncounterInputs`` value. Native MIMIC links, interval checks, pseudonymous
references, event ownership, unresolved routing, tie preservation, and hashing
remain behind :func:`build_encounter_boundaries`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator
from evaluation_pipeline.governance import ProtocolBundleError, verify_protocol_lock
from evaluation_pipeline.subject_split import audit_subject_split


FORMAL_SPLIT_ROLES = ("development", "validation", "final_test")
ALL_SPLIT_ROLES = (*FORMAL_SPLIT_ROLES, "engineering_audit")
JOURNEY_REASON_CODES = (
    "JOURNEY_SPLIT_ROLE_UNKNOWN",
    "JOURNEY_ADMISSION_INVALID_INTERVAL",
    "JOURNEY_STANDALONE_ED_EXCLUDED",
    "JOURNEY_LINKED_ADMISSION_NOT_FOUND",
    "JOURNEY_SUBJECT_MISMATCH",
    "JOURNEY_ED_HANDOFF_INVALID",
    "JOURNEY_ICU_OUTSIDE_ADMISSION",
    "JOURNEY_EVENT_HADM_MISSING",
    "JOURNEY_EVENT_TIME_INVALID",
    "JOURNEY_EVENT_TIME_UNKNOWN",
    "JOURNEY_EVENT_OUTSIDE_BOUNDARY",
)

LOCAL_TIME_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[T ][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?)?$"
)
CLINICAL_EVENT_ID_PATTERN = re.compile(r"^evt:[0-9a-f]{24}$")
ROLE_USE = {
    "development": "rule_discovery",
    "validation": "threshold_validation",
    "final_test": "blind_final_evaluation",
    "engineering_audit": "engineering_audit_only",
}
MANIFEST_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "encounter-boundary-manifest.schema.json"
)


class EncounterBoundaryError(ValueError):
    """Raised for malformed configuration or structurally ambiguous input."""


@dataclass(frozen=True)
class EncounterInputs:
    admissions: Iterable[Mapping[str, Any]]
    ed_stays: Iterable[Mapping[str, Any]]
    icu_stays: Iterable[Mapping[str, Any]]
    events: Iterable[Mapping[str, Any]]
    protocol_bundle: Mapping[str, Any]
    protocol_lock: Mapping[str, Any]
    subject_split_artifacts: Mapping[str, Any]
    subject_split_secret: bytes | str
    subject_role: str
    reference_key_id: str
    reference_secret: bytes | str


@dataclass(frozen=True)
class JourneyScopePolicy:
    linked_pre_admission_ed: str = "include_native_hadm_handoff"
    standalone_ed: str = "exclude_first_release"
    multi_admission_boundary: str = "one_hadm_per_journey_subject_linked"
    icu_scope: str = "nested_substay"
    engineering_audit_policy: str = "build_but_formal_statistics_forbidden"


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
        raise EncounterBoundaryError(f"value is not canonical JSON: {error}") from error


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _identifier(value: Any, field: str) -> str | int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise EncounterBoundaryError(f"{field} must be a non-empty string or integer")
    if isinstance(value, str) and not value:
        raise EncounterBoundaryError(f"{field} must be a non-empty string or integer")
    return value


def _optional_identifier(value: Any, field: str) -> str | int | None:
    if value in (None, ""):
        return None
    return _identifier(value, field)


def _parse_time(value: Any, field: str) -> tuple[str | None, datetime | None]:
    if value in (None, ""):
        return None, None
    if not isinstance(value, str):
        return str(value), None
    if not LOCAL_TIME_PATTERN.fullmatch(value):
        return value, None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value, None
    return value, parsed


def _time_matches_precision(value: str, precision: str) -> bool:
    if precision == "date":
        return bool(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value))
    if precision == "second":
        return bool(
            re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}",
                value,
            )
        )
    if precision == "subsecond":
        return bool(
            re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{1,6}",
                value,
            )
        )
    return precision == "unknown" and value == ""


def _identity_key(value: Any, field: str) -> bytes:
    identifier = _identifier(value, field)
    return _canonical_bytes({"type": type(identifier).__name__, "value": identifier})


def _reference(secret: bytes, kind: str, *parts: Any) -> str:
    payload = _canonical_bytes({"kind": kind, "parts": list(parts)})
    return f"{kind}_" + hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _secret(value: bytes | str) -> bytes:
    if isinstance(value, str):
        value = value.encode("utf-8")
    if not isinstance(value, bytes) or len(value) < 32:
        raise EncounterBoundaryError("reference_secret must contain at least 32 bytes")
    return value


def _validated_policy(policy: JourneyScopePolicy) -> dict[str, str]:
    canonical = {
        "linked_pre_admission_ed": policy.linked_pre_admission_ed,
        "standalone_ed": policy.standalone_ed,
        "multi_admission_boundary": policy.multi_admission_boundary,
        "icu_scope": policy.icu_scope,
        "engineering_audit_policy": policy.engineering_audit_policy,
    }
    expected = {
        "linked_pre_admission_ed": "include_native_hadm_handoff",
        "standalone_ed": "exclude_first_release",
        "multi_admission_boundary": "one_hadm_per_journey_subject_linked",
        "icu_scope": "nested_substay",
        "engineering_audit_policy": "build_but_formal_statistics_forbidden",
    }
    if canonical != expected:
        raise EncounterBoundaryError(
            "journey policy is outside the frozen first-release scope"
        )
    return canonical


def _subject_map(
    artifacts: Mapping[str, Any], permitted_role: str
) -> tuple[dict[bytes, dict[str, str]], dict[str, str]]:
    if permitted_role not in ALL_SPLIT_ROLES:
        raise EncounterBoundaryError(f"invalid permitted subject_role: {permitted_role}")
    if not isinstance(artifacts, Mapping):
        raise EncounterBoundaryError("subject_split_artifacts must be a mapping")
    public = artifacts.get("public_manifest")
    protected = artifacts.get("protected_mapping")
    if not isinstance(public, Mapping) or not isinstance(protected, Mapping):
        raise EncounterBoundaryError(
            "subject_split_artifacts must contain public_manifest and protected_mapping"
        )
    audit = audit_subject_split(
        public, protected, subject_ref_secret=artifacts.get("verification_secret")
    )
    if not audit["valid"]:
        raise EncounterBoundaryError(
            "subject split audit failed: " + json.dumps(audit["errors"], ensure_ascii=False)
        )
    result: dict[bytes, dict[str, str]] = {}
    seen_refs: set[str] = set()
    for value in protected["records"]:
        subject_id = value.get("subject_id")
        key = _identity_key(subject_id, "protected_mapping.subject_id")
        if key in result:
            raise EncounterBoundaryError("duplicate typed subject_id in protected mapping")
        subject_ref = value.get("subject_ref")
        role = value.get("subject_role")
        if (
            not isinstance(subject_ref, str)
            or not re.fullmatch(r"sub_[0-9a-f]{64}", subject_ref)
        ):
            raise EncounterBoundaryError("subject_ref violates subject-split contract")
        if role not in ALL_SPLIT_ROLES:
            raise EncounterBoundaryError(f"invalid subject_role: {role}")
        if subject_ref in seen_refs:
            raise EncounterBoundaryError(f"duplicate subject_ref: {subject_ref}")
        seen_refs.add(subject_ref)
        result[key] = {"subject_ref": subject_ref, "subject_role": role}
    lineage = {
        "split_id": public["split_id"],
        "protocol_lock_sha256": public["protocol_lock_sha256"],
        "public_manifest_sha256": protected["public_manifest_sha256"],
        "subject_ref_key_id": public["subject_ref_key_id"],
        "subject_role": permitted_role,
        "permitted_use": ROLE_USE[permitted_role],
    }
    return result, lineage


def _unique_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    record_type: str,
    id_field: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[bytes] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise EncounterBoundaryError(f"{record_type} row must be an object")
        identifier = _identifier(row.get(id_field), f"{record_type}.{id_field}")
        identity = _identity_key(identifier, f"{record_type}.{id_field}")
        if identity in seen:
            raise EncounterBoundaryError(
                f"duplicate {record_type}.{id_field}: {identifier}"
            )
        seen.add(identity)
        output.append(dict(row))
    return output


def _assert_single_split(
    rows: Iterable[Mapping[str, Any]],
    subjects: Mapping[bytes, Mapping[str, str]],
    permitted_role: str,
    record_type: str,
) -> None:
    for row in rows:
        subject_id = row.get("subject_id")
        try:
            key = _identity_key(subject_id, f"{record_type}.subject_id")
        except EncounterBoundaryError:
            continue
        assignment = subjects.get(key)
        if assignment is not None and assignment["subject_role"] != permitted_role:
            raise EncounterBoundaryError(
                "input contains records from multiple splits; build one split per manifest"
            )


def _unresolved(
    secret: bytes,
    record_type: str,
    native_id: str | int,
    reasons: Iterable[str],
) -> dict[str, Any]:
    unique_reasons = sorted(set(reasons), key=JOURNEY_REASON_CODES.index)
    if not unique_reasons:
        raise EncounterBoundaryError("unresolved record must have a reason code")
    return {
        "record_type": record_type,
        "record_ref": _reference(secret, record_type, native_id),
        "reason_codes": unique_reasons,
    }


def audit_encounter_boundary_manifest(
    manifest: Mapping[str, Any],
    *,
    reference_secret: bytes | str,
    expected_protocol_lock_sha256: str,
    expected_public_manifest_sha256: str,
    expected_source_inputs_sha256: str,
) -> dict[str, Any]:
    """Authenticate lineage and recompute boundary consistency checks."""
    errors: list[str] = []
    try:
        secret = _secret(reference_secret)
    except EncounterBoundaryError as error:
        secret = b""
        errors.append(str(error))
    try:
        schema = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        schema_errors = sorted(
            Draft202012Validator(schema).iter_errors(manifest),
            key=lambda error: list(error.absolute_path),
        )
        errors.extend(
            f"schema:{'.'.join(map(str, error.absolute_path)) or '$'}:{error.message}"
            for error in schema_errors
        )
    except Exception as error:
        errors.append(f"manifest schema unavailable or invalid: {error}")
    body = dict(manifest)
    declared_hash = body.pop("manifest_sha256", None)
    declared_hmac = body.pop("manifest_hmac_sha256", None)
    if declared_hash != _sha256(body):
        errors.append("manifest_sha256 mismatch")
    if secret:
        expected_hmac = hmac.new(
            secret,
            b"encounter-boundary-manifest/1.0.0\x00" + _canonical_bytes(body),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(str(declared_hmac), expected_hmac):
            errors.append("manifest_hmac_sha256 mismatch")
    policy = manifest.get("policy", {})
    if manifest.get("policy_sha256") != _sha256(policy):
        errors.append("policy_sha256 mismatch")
    lineage = manifest.get("split_lineage", {})
    role = lineage.get("subject_role") if isinstance(lineage, Mapping) else None
    permitted_use = ROLE_USE.get(role)
    if permitted_use is None or lineage.get("permitted_use") != permitted_use:
        errors.append("split lineage role/use mismatch")
    if lineage.get("protocol_lock_sha256") != expected_protocol_lock_sha256:
        errors.append("protocol lock lineage mismatch")
    if lineage.get("public_manifest_sha256") != expected_public_manifest_sha256:
        errors.append("subject split manifest lineage mismatch")
    if manifest.get("source_inputs_sha256") != expected_source_inputs_sha256:
        errors.append("source input lineage mismatch")

    journeys = manifest.get("journeys", [])
    assignments = manifest.get("event_assignments", [])
    unresolved = manifest.get("unresolved", [])
    if not all(isinstance(value, list) for value in (journeys, assignments, unresolved)):
        return {
            "schema_version": "encounter-boundary-audit/1.0.0",
            "valid": False,
            "errors": sorted(set([*errors, "manifest collections must be arrays"])),
        }
    journey_ids = [row.get("journey_id") for row in journeys if isinstance(row, Mapping)]
    if len(journey_ids) != len(set(journey_ids)):
        errors.append("duplicate journey_id")
    journey_set = set(journey_ids)
    journey_by_id = {
        row.get("journey_id"): row for row in journeys if isinstance(row, Mapping)
    }
    expected_formal = role in FORMAL_SPLIT_ROLES
    expected_discovery = role == "development"
    admission_refs: list[Any] = []
    ed_refs: list[Any] = []
    icu_refs: list[Any] = []
    for row in journeys:
        if not isinstance(row, Mapping):
            errors.append("journey row must be an object")
            continue
        if row.get("subject_role") != role or row.get("permitted_use") != permitted_use:
            errors.append("journey role/use differs from split lineage")
        if row.get("formal_evaluation_eligible") is not expected_formal:
            errors.append("journey formal evaluation gate mismatch")
        if row.get("rule_discovery_eligible") is not expected_discovery:
            errors.append("journey rule discovery gate mismatch")
        admission_refs.append(row.get("admission_ref"))
        ed_refs.extend(row.get("linked_ed_stay_refs", []))
        icu_refs.extend(
            item.get("icu_stay_ref")
            for item in row.get("icu_substays", [])
            if isinstance(item, Mapping)
        )
        start_text = row.get("journey_start_time")
        admit_text = row.get("admit_time")
        discharge_text = row.get("discharge_time")
        _, start = _parse_time(start_text, "journey_start_time")
        _, admit = _parse_time(admit_text, "admit_time")
        _, discharge = _parse_time(discharge_text, "discharge_time")
        if start is None or admit is None or discharge is None or not start <= admit <= discharge:
            errors.append("journey time interval is invalid")
    for label, references in (
        ("admission", admission_refs), ("ED", ed_refs), ("ICU", icu_refs)
    ):
        if len(references) != len(set(references)):
            errors.append(f"{label} reference has multiple journey owners")
    event_ids = [row.get("event_id") for row in assignments if isinstance(row, Mapping)]
    if len(event_ids) != len(set(event_ids)):
        errors.append("duplicate assigned event_id")
    group_by_key: dict[tuple[Any, str, str], Any] = {}
    key_by_group: dict[Any, tuple[Any, str, str]] = {}
    for row in assignments:
        if not isinstance(row, Mapping) or row.get("journey_id") not in journey_set:
            errors.append("event assignment references an unknown journey")
            continue
        journey = journey_by_id[row["journey_id"]]
        _, event_time = _parse_time(row.get("event_time"), "event_time")
        _, journey_start = _parse_time(journey.get("journey_start_time"), "journey_start_time")
        _, discharge = _parse_time(journey.get("discharge_time"), "discharge_time")
        precision = row.get("time_precision")
        if event_time is None or journey_start is None or discharge is None:
            errors.append("assigned event has invalid time semantics")
        elif not _time_matches_precision(str(row.get("event_time")), str(precision)):
            errors.append("event_time and time_precision are inconsistent")
        elif precision == "date":
            if not journey_start.date() <= event_time.date() <= discharge.date():
                errors.append("assigned date event is outside journey boundary")
        elif not journey_start <= event_time <= discharge:
            errors.append("assigned event is outside journey boundary")
        group_id = row.get("time_group_id")
        if precision in {"date", "unknown"} and group_id is not None:
            errors.append("imprecise event must not have exact time_group_id")
        if precision in {"second", "subsecond"} and group_id is None:
            errors.append("precise event must have time_group_id")
        if event_time is not None and precision in {"second", "subsecond"}:
            key = (
                row.get("journey_id"),
                event_time.isoformat(timespec="microseconds"),
                precision,
            )
            previous_group = group_by_key.setdefault(key, group_id)
            if previous_group != group_id:
                errors.append("one exact time group was split across multiple identifiers")
            previous_key = key_by_group.setdefault(group_id, key)
            if previous_key != key:
                errors.append("one time_group_id merges distinct exact time groups")
    unresolved_refs = [
        (row.get("record_type"), row.get("record_ref"))
        for row in unresolved
        if isinstance(row, Mapping)
    ]
    if len(unresolved_refs) != len(set(unresolved_refs)):
        errors.append("duplicate unresolved record reference")
    reason_counts = {code: 0 for code in JOURNEY_REASON_CODES}
    for row in unresolved:
        if isinstance(row, Mapping):
            for code in row.get("reason_codes", []):
                if code in reason_counts:
                    reason_counts[code] += 1
                else:
                    errors.append(f"unknown journey reason code: {code}")
    expected_counts = {
        "journeys": len(journeys),
        "formal_evaluation_eligible_journeys": sum(
            row.get("formal_evaluation_eligible") is True
            for row in journeys
            if isinstance(row, Mapping)
        ),
        "rule_discovery_eligible_journeys": sum(
            row.get("rule_discovery_eligible") is True
            for row in journeys
            if isinstance(row, Mapping)
        ),
        "engineering_audit_journeys": sum(
            row.get("subject_role") == "engineering_audit"
            for row in journeys
            if isinstance(row, Mapping)
        ),
        "linked_ed_stays": sum(
            len(row.get("linked_ed_stay_refs", []))
            for row in journeys
            if isinstance(row, Mapping)
        ),
        "icu_substays": sum(
            len(row.get("icu_substays", []))
            for row in journeys
            if isinstance(row, Mapping)
        ),
        "assigned_events": len(assignments),
        "unresolved_records": len(unresolved),
        "unresolved_reason_counts": reason_counts,
    }
    if manifest.get("counts") != expected_counts:
        errors.append("declared counts do not match manifest contents")
    return {
        "schema_version": "encounter-boundary-audit/1.0.0",
        "valid": not errors,
        "errors": sorted(set(errors)),
        "manifest_sha256": declared_hash,
    }


def build_encounter_boundaries(
    inputs: EncounterInputs,
    policy: JourneyScopePolicy = JourneyScopePolicy(),
) -> dict[str, Any]:
    """Return a deterministic, identity-safe encounter-boundary manifest."""
    canonical_policy = _validated_policy(policy)
    secret = _secret(inputs.reference_secret)
    if not isinstance(inputs.reference_key_id, str) or not inputs.reference_key_id:
        raise EncounterBoundaryError("reference_key_id must be a non-empty string")
    subjects, split_lineage = _subject_map(
        {
            **inputs.subject_split_artifacts,
            "verification_secret": inputs.subject_split_secret,
        },
        inputs.subject_role,
    )
    try:
        verified_lock = verify_protocol_lock(
            dict(inputs.protocol_bundle), inputs.protocol_lock
        )
    except ProtocolBundleError as error:
        raise EncounterBoundaryError(
            f"protocol lock verification failed: {error}"
        ) from error
    if split_lineage["protocol_lock_sha256"] != verified_lock["protocol_lock_sha256"]:
        raise EncounterBoundaryError(
            "subject split is not bound to the supplied protocol lock"
        )
    admissions = _unique_rows(
        inputs.admissions, record_type="admission", id_field="hadm_id"
    )
    ed_stays = _unique_rows(inputs.ed_stays, record_type="ed_stay", id_field="stay_id")
    icu_stays = _unique_rows(
        inputs.icu_stays, record_type="icu_stay", id_field="stay_id"
    )
    events = _unique_rows(inputs.events, record_type="event", id_field="event_id")
    for row in events:
        if not CLINICAL_EVENT_ID_PATTERN.fullmatch(str(row["event_id"])):
            raise EncounterBoundaryError(
                "event.event_id violates the current clinical-event contract"
            )
    for rows, record_type in (
        (admissions, "admission"),
        (ed_stays, "ed_stay"),
        (icu_stays, "icu_stay"),
        (events, "event"),
    ):
        _assert_single_split(rows, subjects, inputs.subject_role, record_type)

    journeys: list[dict[str, Any]] = []
    journey_by_hadm: dict[bytes, dict[str, Any]] = {}
    subject_by_hadm: dict[bytes, bytes] = {}
    admission_times: dict[bytes, tuple[datetime, datetime]] = {}
    journey_starts: dict[bytes, datetime] = {}
    unresolved: list[dict[str, Any]] = []

    for row in admissions:
        hadm_id = _identifier(row["hadm_id"], "admission.hadm_id")
        subject_id = _identifier(row.get("subject_id"), "admission.subject_id")
        subject_key = _identity_key(subject_id, "admission.subject_id")
        hadm_key = _identity_key(hadm_id, "admission.hadm_id")
        assignment = subjects.get(subject_key)
        admit_text, admit_time = _parse_time(row.get("admittime"), "admittime")
        discharge_text, discharge_time = _parse_time(row.get("dischtime"), "dischtime")
        reasons: list[str] = []
        if assignment is None:
            reasons.append("JOURNEY_SPLIT_ROLE_UNKNOWN")
        elif assignment["subject_role"] != inputs.subject_role:
            raise EncounterBoundaryError(
                "input contains a subject outside the permitted single split: "
                f"{assignment['subject_role']}"
            )
        if (
            admit_time is None
            or discharge_time is None
            or admit_time > discharge_time
        ):
            reasons.append("JOURNEY_ADMISSION_INVALID_INTERVAL")
        if reasons:
            unresolved.append(_unresolved(secret, "admission", hadm_id, reasons))
            continue
        assert assignment is not None and admit_time is not None and discharge_time is not None
        journey_id = _reference(secret, "journey", subject_id, hadm_id)
        journey = {
            "journey_id": journey_id,
            "subject_ref": assignment["subject_ref"],
            "subject_role": assignment["subject_role"],
            "formal_evaluation_eligible": assignment["subject_role"] in FORMAL_SPLIT_ROLES,
            "rule_discovery_eligible": assignment["subject_role"] == "development",
            "permitted_use": ROLE_USE[assignment["subject_role"]],
            "admission_ref": _reference(secret, "admission", hadm_id),
            "admit_time": admit_text,
            "journey_start_time": admit_text,
            "discharge_time": discharge_text,
            "linked_ed_stay_refs": [],
            "icu_substays": [],
        }
        journeys.append(journey)
        journey_by_hadm[hadm_key] = journey
        subject_by_hadm[hadm_key] = subject_key
        admission_times[hadm_key] = (admit_time, discharge_time)
        journey_starts[hadm_key] = admit_time

    for row in ed_stays:
        stay_id = _identifier(row["stay_id"], "ed_stay.stay_id")
        hadm_id = _optional_identifier(row.get("hadm_id"), "ed_stay.hadm_id")
        if hadm_id is None:
            unresolved.append(
                _unresolved(
                    secret,
                    "ed_stay",
                    stay_id,
                    ["JOURNEY_STANDALONE_ED_EXCLUDED"],
                )
            )
            continue
        hadm_key = _identity_key(hadm_id, "ed_stay.hadm_id")
        journey = journey_by_hadm.get(hadm_key)
        if journey is None:
            unresolved.append(
                _unresolved(
                    secret,
                    "ed_stay",
                    stay_id,
                    ["JOURNEY_LINKED_ADMISSION_NOT_FOUND"],
                )
            )
            continue
        reasons: list[str] = []
        subject_id = _identifier(row.get("subject_id"), "ed_stay.subject_id")
        if _identity_key(subject_id, "ed_stay.subject_id") != subject_by_hadm[hadm_key]:
            reasons.append("JOURNEY_SUBJECT_MISMATCH")
        _, intime = _parse_time(row.get("intime"), "ed_stay.intime")
        _, outtime = _parse_time(row.get("outtime"), "ed_stay.outtime")
        admit_time, discharge_time = admission_times[hadm_key]
        if (
            intime is None
            or outtime is None
            or intime > outtime
            or intime > admit_time
            or outtime < admit_time
            or outtime > discharge_time
        ):
            reasons.append("JOURNEY_ED_HANDOFF_INVALID")
        if reasons:
            unresolved.append(_unresolved(secret, "ed_stay", stay_id, reasons))
        else:
            journey["linked_ed_stay_refs"].append(
                _reference(secret, "ed_stay", stay_id)
            )
            assert intime is not None
            journey_starts[hadm_key] = min(journey_starts[hadm_key], intime)
            journey["journey_start_time"] = min(journey_starts[hadm_key], intime).isoformat(
                timespec="microseconds"
            )

    for row in icu_stays:
        stay_id = _identifier(row["stay_id"], "icu_stay.stay_id")
        hadm_id = _identifier(row.get("hadm_id"), "icu_stay.hadm_id")
        hadm_key = _identity_key(hadm_id, "icu_stay.hadm_id")
        journey = journey_by_hadm.get(hadm_key)
        if journey is None:
            unresolved.append(
                _unresolved(
                    secret,
                    "icu_stay",
                    stay_id,
                    ["JOURNEY_LINKED_ADMISSION_NOT_FOUND"],
                )
            )
            continue
        reasons: list[str] = []
        subject_id = _identifier(row.get("subject_id"), "icu_stay.subject_id")
        if _identity_key(subject_id, "icu_stay.subject_id") != subject_by_hadm[hadm_key]:
            reasons.append("JOURNEY_SUBJECT_MISMATCH")
        in_text, intime = _parse_time(row.get("intime"), "icu_stay.intime")
        out_text, outtime = _parse_time(row.get("outtime"), "icu_stay.outtime")
        admit_time, discharge_time = admission_times[hadm_key]
        if (
            intime is None
            or outtime is None
            or intime > outtime
            or intime < admit_time
            or outtime > discharge_time
        ):
            reasons.append("JOURNEY_ICU_OUTSIDE_ADMISSION")
        if reasons:
            unresolved.append(_unresolved(secret, "icu_stay", stay_id, reasons))
        else:
            journey["icu_substays"].append(
                {
                    "icu_stay_ref": _reference(secret, "icu_stay", stay_id),
                    "in_time": in_text,
                    "out_time": out_text,
                }
            )

    event_assignments: list[dict[str, Any]] = []
    for row in events:
        event_id = _identifier(row["event_id"], "event.event_id")
        hadm_id = _optional_identifier(row.get("hadm_id"), "event.hadm_id")
        if hadm_id is None:
            unresolved.append(
                _unresolved(
                    secret, "event", event_id, ["JOURNEY_EVENT_HADM_MISSING"]
                )
            )
            continue
        hadm_key = _identity_key(hadm_id, "event.hadm_id")
        journey = journey_by_hadm.get(hadm_key)
        if journey is None:
            unresolved.append(
                _unresolved(
                    secret,
                    "event",
                    event_id,
                    ["JOURNEY_LINKED_ADMISSION_NOT_FOUND"],
                )
            )
            continue
        subject_id = _identifier(row.get("subject_id"), "event.subject_id")
        if _identity_key(subject_id, "event.subject_id") != subject_by_hadm[hadm_key]:
            unresolved.append(
                _unresolved(
                    secret, "event", event_id, ["JOURNEY_SUBJECT_MISMATCH"]
                )
            )
            continue
        event_time_text, event_time = _parse_time(
            row.get("event_time"), "event.event_time"
        )
        available_time_text, available_time = _parse_time(
            row.get("available_time"), "event.available_time"
        )
        if event_time_text is None:
            unresolved.append(
                _unresolved(
                    secret, "event", event_id, ["JOURNEY_EVENT_TIME_UNKNOWN"]
                )
            )
            continue
        if (
            (event_time_text is not None and event_time is None)
            or (available_time_text is not None and available_time is None)
        ):
            unresolved.append(
                _unresolved(
                    secret, "event", event_id, ["JOURNEY_EVENT_TIME_INVALID"]
                )
            )
            continue
        time_precision = row.get("time_precision")
        if time_precision not in {"subsecond", "second", "date", "unknown"}:
            raise EncounterBoundaryError("event.time_precision violates clinical-event contract")
        if not _time_matches_precision(event_time_text, time_precision):
            unresolved.append(
                _unresolved(
                    secret, "event", event_id, ["JOURNEY_EVENT_TIME_INVALID"]
                )
            )
            continue
        admit_time, discharge_time = admission_times[hadm_key]
        journey_start = journey_starts[hadm_key]
        assert event_time is not None
        outside_boundary = (
            event_time.date() < journey_start.date()
            or event_time.date() > discharge_time.date()
            if time_precision == "date"
            else event_time < journey_start or event_time > discharge_time
        )
        if outside_boundary:
            unresolved.append(
                _unresolved(
                    secret, "event", event_id, ["JOURNEY_EVENT_OUTSIDE_BOUNDARY"]
                )
            )
            continue
        canonical_event_time = (
            event_time.isoformat(timespec="microseconds")
            if event_time is not None
            else None
        )
        event_assignments.append(
            {
                "event_id": event_id,
                "source_event_sha256": _sha256(dict(row)),
                "journey_id": journey["journey_id"],
                "event_time": event_time_text,
                "available_time": available_time_text,
                "time_precision": time_precision,
                "time_group_id": (
                    _reference(
                        secret,
                        "time_group",
                        journey["journey_id"],
                        canonical_event_time,
                        time_precision,
                    )
                    if canonical_event_time is not None
                    and time_precision in {"second", "subsecond"}
                    else None
                ),
            }
        )

    for journey in journeys:
        journey["linked_ed_stay_refs"].sort()
        journey["icu_substays"].sort(
            key=lambda value: (value["in_time"], value["icu_stay_ref"])
        )
    journeys.sort(key=lambda value: value["journey_id"])
    event_assignments.sort(key=lambda value: value["event_id"])
    unresolved.sort(key=lambda value: (value["record_type"], value["record_ref"]))
    reason_counts = {code: 0 for code in JOURNEY_REASON_CODES}
    for row in unresolved:
        for code in row["reason_codes"]:
            reason_counts[code] += 1

    source_inputs_sha256 = _sha256(
        {
            "admissions": sorted(admissions, key=_canonical_bytes),
            "ed_stays": sorted(ed_stays, key=_canonical_bytes),
            "icu_stays": sorted(icu_stays, key=_canonical_bytes),
            "events": sorted(events, key=_canonical_bytes),
        }
    )
    body = {
        "schema_version": "encounter-boundary-manifest/1.0.0",
        "reference_key_id": inputs.reference_key_id,
        "split_lineage": split_lineage,
        "policy": canonical_policy,
        "policy_sha256": _sha256(canonical_policy),
        "source_inputs_sha256": source_inputs_sha256,
        "counts": {
            "journeys": len(journeys),
            "formal_evaluation_eligible_journeys": sum(
                row["formal_evaluation_eligible"] for row in journeys
            ),
            "rule_discovery_eligible_journeys": sum(
                row["rule_discovery_eligible"] for row in journeys
            ),
            "engineering_audit_journeys": sum(
                row["subject_role"] == "engineering_audit" for row in journeys
            ),
            "linked_ed_stays": sum(
                len(row["linked_ed_stay_refs"]) for row in journeys
            ),
            "icu_substays": sum(len(row["icu_substays"]) for row in journeys),
            "assigned_events": len(event_assignments),
            "unresolved_records": len(unresolved),
            "unresolved_reason_counts": reason_counts,
        },
        "journeys": journeys,
        "event_assignments": event_assignments,
        "unresolved": unresolved,
    }
    manifest = {
        **body,
        "manifest_sha256": _sha256(body),
        "manifest_hmac_sha256": hmac.new(
            secret,
            b"encounter-boundary-manifest/1.0.0\x00" + _canonical_bytes(body),
            hashlib.sha256,
        ).hexdigest(),
    }
    audit = audit_encounter_boundary_manifest(
        manifest,
        reference_secret=secret,
        expected_protocol_lock_sha256=split_lineage["protocol_lock_sha256"],
        expected_public_manifest_sha256=split_lineage["public_manifest_sha256"],
        expected_source_inputs_sha256=source_inputs_sha256,
    )
    if not audit["valid"]:
        raise EncounterBoundaryError(
            "generated manifest failed audit: "
            + json.dumps(audit["errors"], ensure_ascii=False)
        )
    return manifest
