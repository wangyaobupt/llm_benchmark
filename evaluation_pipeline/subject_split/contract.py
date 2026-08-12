"""Deterministic, patient-atomic subject split construction and auditing.

The public manifest contains only pseudonymous ``subject_ref`` values.  Raw
``subject_id`` values are confined to the separately handled protected map.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from collections import Counter
from typing import Any, Iterable, Mapping


FORMAL_ROLES = ("development", "validation", "final_test")
ALL_ROLES = (*FORMAL_ROLES, "engineering_audit")
ASSIGNMENT_METHOD = "sha256-ranked-largest-remainder/1.0.0"


class SubjectSplitError(ValueError):
    """Raised when split inputs, configuration, or artifacts violate the contract."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _subject_token(subject_id: int | str) -> dict[str, int | str]:
    if isinstance(subject_id, bool) or not isinstance(subject_id, (int, str)):
        raise SubjectSplitError("subject_id must be an integer or non-empty string")
    if isinstance(subject_id, str) and not subject_id:
        raise SubjectSplitError("subject_id must be an integer or non-empty string")
    return {"type": type(subject_id).__name__, "value": subject_id}


def _normalize_subjects(
    values: Iterable[int | str], *, label: str
) -> list[tuple[bytes, int | str]]:
    rows: list[tuple[bytes, int | str]] = []
    seen: set[bytes] = set()
    for subject_id in values:
        token = _canonical_bytes(_subject_token(subject_id))
        if token in seen:
            raise SubjectSplitError(f"duplicate subject_id in {label}: {subject_id!r}")
        seen.add(token)
        rows.append((token, subject_id))
    return rows


def _required_string(config: Mapping[str, Any], name: str) -> str:
    value = config.get(name)
    if not isinstance(value, str) or not value:
        raise SubjectSplitError(f"config.{name} must be a non-empty string")
    return value


def _validated_config(config: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(config, Mapping):
        raise SubjectSplitError("config must be a mapping")
    split_id = _required_string(config, "split_id")
    protocol_lock_sha256 = _required_string(config, "protocol_lock_sha256")
    if len(protocol_lock_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in protocol_lock_sha256
    ):
        raise SubjectSplitError("config.protocol_lock_sha256 must be 64 lowercase hex characters")
    assignment_seed = _required_string(config, "assignment_seed")
    subject_ref_key_id = _required_string(config, "subject_ref_key_id")
    subject_ref_secret = config.get("subject_ref_secret")
    if isinstance(subject_ref_secret, str):
        subject_ref_secret = subject_ref_secret.encode("utf-8")
    if not isinstance(subject_ref_secret, bytes) or not subject_ref_secret:
        raise SubjectSplitError("config.subject_ref_secret must be non-empty bytes or string")

    ratios = config.get("ratios")
    if not isinstance(ratios, Mapping) or set(ratios) != set(FORMAL_ROLES):
        raise SubjectSplitError(
            "config.ratios must explicitly contain only development, validation, and final_test"
        )
    checked_ratios: dict[str, float] = {}
    for role in FORMAL_ROLES:
        value = ratios[role]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SubjectSplitError(f"config.ratios.{role} must be a number")
        number = float(value)
        if not math.isfinite(number) or not 0 < number < 1:
            raise SubjectSplitError(f"config.ratios.{role} must be between 0 and 1")
        checked_ratios[role] = number
    if not math.isclose(sum(checked_ratios.values()), 1.0, abs_tol=1e-12):
        raise SubjectSplitError("config.ratios must sum to 1")

    expected_input_sha256 = config.get("expected_input_sha256")
    if expected_input_sha256 is not None and (
        not isinstance(expected_input_sha256, str)
        or len(expected_input_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_input_sha256)
    ):
        raise SubjectSplitError("config.expected_input_sha256 must be 64 lowercase hex characters")

    return {
        "split_id": split_id,
        "protocol_lock_sha256": protocol_lock_sha256,
        "assignment_seed": assignment_seed,
        "subject_ref_key_id": subject_ref_key_id,
        "subject_ref_secret": subject_ref_secret,
        "ratios": checked_ratios,
        "expected_input_sha256": expected_input_sha256,
    }


def _allocate_counts(total: int, ratios: Mapping[str, float]) -> dict[str, int]:
    if total < len(FORMAL_ROLES):
        raise SubjectSplitError(
            f"at least {len(FORMAL_ROLES)} formal subjects are required to keep all partitions non-empty"
        )
    exact = {role: total * ratios[role] for role in FORMAL_ROLES}
    counts = {role: math.floor(exact[role]) for role in FORMAL_ROLES}
    remaining = total - sum(counts.values())
    remainder_order = sorted(
        FORMAL_ROLES,
        key=lambda role: (-(exact[role] - counts[role]), FORMAL_ROLES.index(role)),
    )
    for role in remainder_order[:remaining]:
        counts[role] += 1

    for empty_role in (role for role in FORMAL_ROLES if counts[role] == 0):
        donors = [role for role in FORMAL_ROLES if counts[role] > 1]
        if not donors:
            raise SubjectSplitError("cannot create non-empty formal partitions")
        donor = min(
            donors,
            key=lambda role: (
                -(counts[role] - exact[role]),
                -counts[role],
                FORMAL_ROLES.index(role),
            ),
        )
        counts[donor] -= 1
        counts[empty_role] = 1
    return counts


def _subject_ref(token: bytes, secret: bytes) -> str:
    digest = hmac.new(secret, b"subject-ref/1.0.0\x00" + token, hashlib.sha256)
    return "sub_" + digest.hexdigest()


def _input_fingerprint(protected_records: list[dict[str, Any]]) -> str:
    rows = [
        {
            "subject_ref": row["subject_ref"],
            "subject_role": row["subject_role"],
        }
        for row in protected_records
    ]
    rows.sort(key=_canonical_bytes)
    return _sha256(rows)


def _contains_key(value: Any, forbidden_key: str) -> bool:
    if isinstance(value, Mapping):
        return forbidden_key in value or any(
            _contains_key(child, forbidden_key) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_key(child, forbidden_key) for child in value)
    return False


def build_subject_split(
    formal_subject_ids: Iterable[int | str],
    engineering_audit_subject_ids: Iterable[int | str],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Build public/private split artifacts and fail closed on any audit error.

    ``config`` requires ``split_id``, ``protocol_lock_sha256``, all three
    ``ratios``, ``assignment_seed``, ``subject_ref_key_id``, and
    ``subject_ref_secret``.  An optional ``expected_input_sha256`` turns the
    first generated fingerprint into a drift lock on later runs.
    """
    checked = _validated_config(config)
    formal = _normalize_subjects(formal_subject_ids, label="formal_subject_ids")
    engineering = _normalize_subjects(
        engineering_audit_subject_ids, label="engineering_audit_subject_ids"
    )
    formal_tokens = {token for token, _ in formal}
    engineering_tokens = {token for token, _ in engineering}
    overlap = formal_tokens & engineering_tokens
    if overlap:
        raise SubjectSplitError(
            "engineering_audit subjects must not appear in the formal input population"
        )

    counts = _allocate_counts(len(formal), checked["ratios"])
    seed = checked["assignment_seed"].encode("utf-8")
    ranked = sorted(
        formal,
        key=lambda row: (hashlib.sha256(seed + b"\x00" + row[0]).digest(), row[0]),
    )
    role_by_token: dict[bytes, str] = {}
    offset = 0
    for role in FORMAL_ROLES:
        for token, _ in ranked[offset : offset + counts[role]]:
            role_by_token[token] = role
        offset += counts[role]

    protected_records: list[dict[str, Any]] = []
    for token, subject_id in (*formal, *engineering):
        role = role_by_token.get(token, "engineering_audit")
        protected_records.append(
            {
                "subject_ref": _subject_ref(token, checked["subject_ref_secret"]),
                "subject_id": subject_id,
                "subject_role": role,
            }
        )
    protected_records.sort(key=lambda row: row["subject_ref"])

    assignments = [
        {
            "subject_ref": row["subject_ref"],
            "subject_role": row["subject_role"],
            "formal_test_eligible": row["subject_role"] != "engineering_audit",
        }
        for row in protected_records
    ]
    input_sha256 = _input_fingerprint(protected_records)
    public_manifest = {
        "schema_version": "subject-split-manifest/1.0.0",
        "split_id": checked["split_id"],
        "protocol_lock_sha256": checked["protocol_lock_sha256"],
        "subject_ref_key_id": checked["subject_ref_key_id"],
        "assignment": {
            "method": ASSIGNMENT_METHOD,
            "assignment_seed_sha256": hashlib.sha256(seed).hexdigest(),
            "requested_ratios": checked["ratios"],
        },
        "input_population_sha256": input_sha256,
        "counts": {
            "total": len(assignments),
            "formal_total": len(formal),
            **{role: counts[role] for role in FORMAL_ROLES},
            "engineering_audit": len(engineering),
        },
        "assignments_sha256": _sha256(assignments),
        "assignments": assignments,
    }
    protected_mapping = {
        "schema_version": "protected-subject-map/1.0.0",
        "split_id": checked["split_id"],
        "public_manifest_sha256": _sha256(public_manifest),
        "records": protected_records,
    }
    audit_report = audit_subject_split(
        public_manifest,
        protected_mapping,
        expected_input_sha256=checked["expected_input_sha256"],
    )
    if not audit_report["valid"]:
        raise SubjectSplitError(
            "generated split failed audit: "
            + json.dumps(audit_report["errors"], ensure_ascii=False)
        )
    return {
        "public_manifest": public_manifest,
        "protected_mapping": protected_mapping,
        "audit_report": audit_report,
    }


def audit_subject_split(
    public_manifest: Mapping[str, Any],
    protected_mapping: Mapping[str, Any],
    *,
    expected_input_sha256: str | None = None,
) -> dict[str, Any]:
    """Audit assignment uniqueness, isolation, counts, hashes, and input drift."""
    errors: list[str] = []
    if _contains_key(public_manifest, "subject_id"):
        errors.append("public manifest exposes subject_id")
    if public_manifest.get("split_id") != protected_mapping.get("split_id"):
        errors.append("public and protected split_id values do not match")
    assignments = public_manifest.get("assignments", [])
    records = protected_mapping.get("records", [])
    if not isinstance(assignments, list):
        assignments = []
        errors.append("public assignments must be a list")
    if not isinstance(records, list):
        records = []
        errors.append("protected records must be a list")

    public_refs: list[str] = []
    public_roles: Counter[str] = Counter()
    public_by_ref: dict[str, str] = {}
    for index, row in enumerate(assignments):
        if not isinstance(row, Mapping):
            errors.append(f"public assignment {index} must be an object")
            continue
        subject_ref = row.get("subject_ref")
        role = row.get("subject_role")
        if not isinstance(subject_ref, str) or not subject_ref:
            errors.append(f"public assignment {index} has invalid subject_ref")
            continue
        if role not in ALL_ROLES:
            errors.append(f"public assignment {index} has invalid subject_role")
            continue
        public_refs.append(subject_ref)
        public_roles[role] += 1
        if subject_ref in public_by_ref and public_by_ref[subject_ref] != role:
            errors.append(f"subject_ref assigned across partitions: {subject_ref}")
        public_by_ref[subject_ref] = role
        expected_eligibility = role != "engineering_audit"
        if row.get("formal_test_eligible") is not expected_eligibility:
            errors.append(f"incorrect formal_test_eligible for {subject_ref}")
    duplicate_public_refs = sorted(
        subject_ref for subject_ref, count in Counter(public_refs).items() if count > 1
    )
    errors.extend(f"duplicate public subject_ref: {value}" for value in duplicate_public_refs)
    for role in FORMAL_ROLES:
        if public_roles[role] == 0:
            errors.append(f"empty formal partition: {role}")

    protected_refs: list[str] = []
    protected_tokens: list[bytes] = []
    protected_by_ref: dict[str, str] = {}
    valid_records: list[dict[str, Any]] = []
    for index, row in enumerate(records):
        if not isinstance(row, Mapping):
            errors.append(f"protected record {index} must be an object")
            continue
        subject_ref = row.get("subject_ref")
        role = row.get("subject_role")
        try:
            token = _canonical_bytes(_subject_token(row.get("subject_id")))
        except SubjectSplitError as error:
            errors.append(f"protected record {index}: {error}")
            continue
        if not isinstance(subject_ref, str) or not subject_ref:
            errors.append(f"protected record {index} has invalid subject_ref")
            continue
        if role not in ALL_ROLES:
            errors.append(f"protected record {index} has invalid subject_role")
            continue
        protected_refs.append(subject_ref)
        protected_tokens.append(token)
        protected_by_ref[subject_ref] = role
        valid_records.append(dict(row))
    for subject_ref, count in Counter(protected_refs).items():
        if count > 1:
            errors.append(f"duplicate protected subject_ref: {subject_ref}")
    for token, count in Counter(protected_tokens).items():
        if count > 1:
            errors.append(
                "duplicate protected subject_id: "
                + token.decode("utf-8")
            )
    if public_by_ref != protected_by_ref:
        errors.append("public assignments and protected mapping do not match")

    declared_counts = public_manifest.get("counts", {})
    observed_counts = {
        "total": len(assignments),
        "formal_total": sum(public_roles[role] for role in FORMAL_ROLES),
        **{role: public_roles[role] for role in ALL_ROLES},
    }
    if declared_counts != observed_counts:
        errors.append("declared counts do not match assignments")
    if public_manifest.get("assignments_sha256") != _sha256(assignments):
        errors.append("assignments_sha256 mismatch")
    if protected_mapping.get("public_manifest_sha256") != _sha256(public_manifest):
        errors.append("public_manifest_sha256 mismatch")

    observed_input_sha256 = (
        _input_fingerprint(valid_records) if len(valid_records) == len(records) else None
    )
    declared_input_sha256 = public_manifest.get("input_population_sha256")
    if observed_input_sha256 is not None and declared_input_sha256 != observed_input_sha256:
        errors.append("input_population_sha256 does not match protected mapping")
    drift_status = "baseline_created"
    if expected_input_sha256 is not None:
        drift_status = "unchanged"
        if declared_input_sha256 != expected_input_sha256:
            drift_status = "drift_detected"
            errors.append("input population drift detected")

    return {
        "schema_version": "subject-split-audit/1.0.0",
        "split_id": public_manifest.get("split_id"),
        "valid": not errors,
        "errors": sorted(set(errors)),
        "input_drift": {
            "status": drift_status,
            "expected_sha256": expected_input_sha256,
            "observed_sha256": declared_input_sha256,
        },
        "observed_counts": observed_counts,
    }
