"""Validate and deterministically lock an evaluation protocol bundle."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


class ProtocolBundleError(ValueError):
    """Raised when a protocol cannot be validated or frozen."""


def _json_types_only(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProtocolBundleError(f"non-finite number at {path}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _json_types_only(child, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ProtocolBundleError(f"non-string key at {path}")
            _json_types_only(child, f"{path}.{key}")
        return
    raise ProtocolBundleError(f"unsupported YAML value at {path}: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Return stable UTF-8 JSON bytes for JSON-compatible protocol data."""
    _json_types_only(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def semantic_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProtocolBundleError(f"{path} must contain a YAML object")
    _json_types_only(value)
    return value


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProtocolBundleError(f"{path} must contain a JSON object")
    return value


def load_protocol_bundle(
    protocol_path: Path,
    schema_path: Path,
    reason_registry_path: Path,
) -> dict[str, Any]:
    """Load the three source documents exposed by the governance interface."""
    paths = {
        "protocol": Path(protocol_path).resolve(),
        "schema": Path(schema_path).resolve(),
        "reason_registry": Path(reason_registry_path).resolve(),
    }
    for path in paths.values():
        if not path.is_file():
            raise ProtocolBundleError(f"missing protocol source: {path}")
    return {
        "protocol": _load_yaml(paths["protocol"]),
        "schema": _load_json(paths["schema"]),
        "reason_registry": _load_yaml(paths["reason_registry"]),
        "paths": paths,
    }


def _registered_reason_codes(registry: dict[str, Any]) -> tuple[set[str], list[str]]:
    errors: list[str] = []
    codes: set[str] = set()
    rows = registry.get("codes")
    if not isinstance(rows, list) or not rows:
        return codes, ["reason registry must contain a non-empty codes list"]
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("code"), str):
            errors.append(f"reason registry row {index} has no string code")
            continue
        code = row["code"]
        if code in codes:
            errors.append(f"duplicate reason code: {code}")
        codes.add(code)
    return codes, errors


def _reason_references(value: Any, path: str = "$") -> list[tuple[str, str]]:
    references: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key.endswith("_reason_code") and isinstance(child, str):
                references.append((child_path, child))
            elif key.endswith("_reason_codes") and isinstance(child, list):
                references.extend(
                    (f"{child_path}[{index}]", code)
                    for index, code in enumerate(child)
                    if isinstance(code, str)
                )
            references.extend(_reason_references(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            references.extend(_reason_references(child, f"{path}[{index}]"))
    return references


def _null_paths(value: Any, path: str = "$") -> list[str]:
    if value is None:
        return [path]
    if isinstance(value, dict):
        return [
            item
            for key, child in value.items()
            for item in _null_paths(child, f"{path}.{key}")
        ]
    if isinstance(value, list):
        return [
            item
            for index, child in enumerate(value)
            for item in _null_paths(child, f"{path}[{index}]")
        ]
    return []


def validate_protocol_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Validate schema, registry references, construct separation and freeze state."""
    protocol = bundle["protocol"]
    errors: list[str] = []
    schema_errors = sorted(
        Draft202012Validator(bundle["schema"]).iter_errors(protocol),
        key=lambda error: list(error.absolute_path),
    )
    errors.extend(
        f"schema:{'.'.join(map(str, error.absolute_path)) or '$'}:{error.message}"
        for error in schema_errors
    )

    registered, registry_errors = _registered_reason_codes(bundle["reason_registry"])
    errors.extend(f"registry:{error}" for error in registry_errors)
    for path, code in _reason_references(protocol):
        if code not in registered:
            errors.append(f"unknown_reason_code:{path}:{code}")

    scientific = protocol.get("scientific_protocol", {})
    constructs = scientific.get("construct_registry", [])
    gold_fields = [
        row.get("gold_field") for row in constructs if isinstance(row, dict)
    ]
    if len(gold_fields) != len(set(gold_fields)):
        errors.append("construct gold_field values must be unique")

    ratios = scientific.get("subject_split", {}).get("ratios", {})
    numeric_ratios = [ratios.get(name) for name in ("development", "validation", "final_test")]
    if all(isinstance(value, (int, float)) for value in numeric_ratios):
        if any(float(value) <= 0 for value in numeric_ratios):
            errors.append("split ratios must all be positive")
        if not math.isclose(sum(map(float, numeric_ratios)), 1.0, abs_tol=1e-12):
            errors.append("split ratios must sum to 1")

    unresolved = protocol.get("unresolved_decisions", [])
    null_scientific_paths = _null_paths(scientific, "$.scientific_protocol")
    status = protocol.get("protocol_status")
    freeze_blockers = list(unresolved)
    freeze_blockers.extend(f"NULL_VALUE:{path}" for path in null_scientific_paths)
    audit = protocol.get("audit_metadata", {})
    if not audit.get("source_git_commit"):
        freeze_blockers.append("AUDIT_METADATA:source_git_commit")
    if not audit.get("dependency_lock_sha256"):
        freeze_blockers.append("AUDIT_METADATA:dependency_lock_sha256")
    if not audit.get("input_manifest_sha256"):
        freeze_blockers.append("AUDIT_METADATA:input_manifest_sha256")
    if status == "frozen" and freeze_blockers:
        errors.append("frozen protocol contains unresolved freeze blockers")

    return {
        "schema_version": "protocol-validation/1.0.0",
        "protocol_id": protocol.get("protocol_id"),
        "protocol_version": protocol.get("protocol_version"),
        "protocol_status": status,
        "valid": not errors,
        "freeze_ready": not errors and status == "frozen" and not freeze_blockers,
        "errors": errors,
        "freeze_blockers": sorted(set(freeze_blockers)),
        "registered_reason_code_count": len(registered),
        "scientific_protocol_sha256": semantic_sha256(scientific),
    }


def build_protocol_lock(bundle: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic lock; refuse drafts or unresolved scientific fields."""
    validation = validate_protocol_bundle(bundle)
    if not validation["freeze_ready"]:
        raise ProtocolBundleError(
            "protocol is not freeze-ready: "
            + json.dumps(validation, ensure_ascii=False, sort_keys=True)
        )
    protocol = bundle["protocol"]
    paths: dict[str, Path] = bundle["paths"]
    source_hashes = {
        name: file_sha256(path) for name, path in sorted(paths.items())
    }
    lock_body = {
        "schema_version": "investigation-selection-protocol-lock/1.0.0",
        "protocol_id": protocol["protocol_id"],
        "protocol_version": protocol["protocol_version"],
        "scientific_protocol_sha256": validation["scientific_protocol_sha256"],
        "runtime_configuration_sha256": semantic_sha256(
            protocol["runtime_configuration"]
        ),
        "audit_metadata_sha256": semantic_sha256(protocol["audit_metadata"]),
        "source_file_sha256": source_hashes,
    }
    return {**lock_body, "protocol_lock_sha256": semantic_sha256(lock_body)}


def write_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
