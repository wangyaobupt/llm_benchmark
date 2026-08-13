"""Validate and deterministically lock an evaluation protocol bundle."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Mapping

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


def _find_repository_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "uv.lock").is_file():
            return candidate
    raise ProtocolBundleError(
        f"cannot locate repository root containing .git and uv.lock from {start}"
    )


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
    reason_registry_schema_path: Path | None = None,
) -> dict[str, Any]:
    """Load the three source documents exposed by the governance interface."""
    paths = {
        "protocol": Path(protocol_path).resolve(),
        "schema": Path(schema_path).resolve(),
        "reason_registry": Path(reason_registry_path).resolve(),
        "reason_registry_schema": Path(
            reason_registry_schema_path
            or Path(schema_path).parent / "reason-code-registry.schema.json"
        ).resolve(),
    }
    for path in paths.values():
        if not path.is_file():
            raise ProtocolBundleError(f"missing protocol source: {path}")
    source_bytes = {name: path.read_bytes() for name, path in paths.items()}
    protocol = yaml.safe_load(source_bytes["protocol"].decode("utf-8"))
    schema = json.loads(source_bytes["schema"].decode("utf-8"))
    reason_registry = yaml.safe_load(source_bytes["reason_registry"].decode("utf-8"))
    reason_registry_schema = json.loads(
        source_bytes["reason_registry_schema"].decode("utf-8")
    )
    for name, value in (
        ("protocol", protocol), ("schema", schema),
        ("reason_registry", reason_registry),
        ("reason_registry_schema", reason_registry_schema),
    ):
        if not isinstance(value, dict):
            raise ProtocolBundleError(f"{paths[name]} must contain an object")
        _json_types_only(value)
    return {
        "protocol": protocol,
        "schema": schema,
        "reason_registry": reason_registry,
        "reason_registry_schema": reason_registry_schema,
        "paths": paths,
        "source_bytes": source_bytes,
        "repository_root": _find_repository_root(paths["schema"].parent),
    }


def _git_output(repository_root: Path, *arguments: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *arguments],
            cwd=repository_root,
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        output = getattr(error, "output", "")
        raise ProtocolBundleError(
            f"git {' '.join(arguments)} failed: {str(output).strip() or error}"
        ) from error


def _audit_evidence_blockers(bundle: dict[str, Any]) -> list[str]:
    audit = bundle.get("protocol", {}).get("audit_metadata", {})
    repository_root = bundle.get("repository_root")
    if not isinstance(repository_root, Path):
        return ["AUDIT_EVIDENCE:repository_root_missing"]
    blockers: list[str] = []

    commit = audit.get("source_git_commit")
    if commit:
        try:
            resolved = _git_output(repository_root, "rev-parse", f"{commit}^{{commit}}")
            head = _git_output(repository_root, "rev-parse", "HEAD")
        except ProtocolBundleError:
            blockers.append("AUDIT_EVIDENCE:source_git_commit_not_found")
        else:
            if resolved != commit:
                blockers.append("AUDIT_EVIDENCE:source_git_commit_not_canonical")
            if resolved != head:
                blockers.append("AUDIT_EVIDENCE:source_git_commit_not_current_head")

    dependency_hash = audit.get("dependency_lock_sha256")
    if dependency_hash:
        dependency_lock = repository_root / "uv.lock"
        if not dependency_lock.is_file():
            blockers.append("AUDIT_EVIDENCE:dependency_lock_missing")
        elif file_sha256(dependency_lock) != dependency_hash:
            blockers.append("AUDIT_EVIDENCE:dependency_lock_sha256_mismatch")

    manifests = audit.get("input_manifest_sha256")
    if isinstance(manifests, dict):
        for relative_name, expected_hash in sorted(manifests.items()):
            relative = Path(relative_name)
            if relative.is_absolute() or ".." in relative.parts:
                blockers.append(
                    f"AUDIT_EVIDENCE:input_manifest_path_invalid:{relative_name}"
                )
                continue
            manifest_path = (repository_root / relative).resolve()
            if repository_root.resolve() not in manifest_path.parents:
                blockers.append(
                    f"AUDIT_EVIDENCE:input_manifest_path_invalid:{relative_name}"
                )
            elif not manifest_path.is_file():
                blockers.append(
                    f"AUDIT_EVIDENCE:input_manifest_missing:{relative_name}"
                )
            elif file_sha256(manifest_path) != expected_hash:
                blockers.append(
                    f"AUDIT_EVIDENCE:input_manifest_sha256_mismatch:{relative_name}"
                )
    return blockers


def _registered_reason_codes(registry: dict[str, Any]) -> tuple[set[str], list[str]]:
    errors: list[str] = []
    codes: set[str] = set()
    if registry.get("schema_version") != "reason-code-registry/1.0.0":
        errors.append("invalid reason registry schema_version")
    if registry.get("registry_id") != "investigation-selection-shared-gates":
        errors.append("invalid reason registry registry_id")
    rows = registry.get("codes")
    if not isinstance(rows, list) or not rows:
        return codes, ["reason registry must contain a non-empty codes list"]
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"code", "stage", "description"}:
            errors.append(f"reason registry row {index} has invalid fields")
            continue
        if not isinstance(row.get("code"), str):
            errors.append(f"reason registry row {index} has no string code")
            continue
        code = row["code"]
        if not code or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for character in code):
            errors.append(f"reason registry row {index} has invalid code format")
        if row.get("stage") not in {"protocol", "split", "snapshot", "journey", "hypothesis", "validation", "release"}:
            errors.append(f"reason registry row {index} has invalid stage")
        if not isinstance(row.get("description"), str) or not row["description"]:
            errors.append(f"reason registry row {index} has empty description")
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
    schema_validity: dict[str, bool] = {}
    for name, schema in (
        ("protocol", bundle["schema"]),
        ("reason_registry", bundle["reason_registry_schema"]),
    ):
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as error:
            schema_validity[name] = False
            errors.append(f"invalid_json_schema:{name}:{error}")
        else:
            schema_validity[name] = True
    if schema_validity["protocol"]:
        try:
            schema_errors = sorted(
                Draft202012Validator(bundle["schema"]).iter_errors(protocol),
                key=lambda error: list(error.absolute_path),
            )
        except Exception as error:
            errors.append(f"invalid_json_schema:protocol:{error}")
        else:
            errors.extend(
                f"schema:{'.'.join(map(str, error.absolute_path)) or '$'}:{error.message}"
                for error in schema_errors
            )
    if schema_validity["reason_registry"]:
        try:
            registry_schema_errors = sorted(
                Draft202012Validator(bundle["reason_registry_schema"]).iter_errors(
                    bundle["reason_registry"]
                ),
                key=lambda error: list(error.absolute_path),
            )
        except Exception as error:
            errors.append(f"invalid_json_schema:reason_registry:{error}")
        else:
            errors.extend(
                f"registry_schema:{'.'.join(map(str, error.absolute_path)) or '$'}:{error.message}"
                for error in registry_schema_errors
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
    freeze_blockers.extend(_audit_evidence_blockers(bundle))
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
    source_bytes = bundle.get("source_bytes")
    if not isinstance(source_bytes, dict) or set(source_bytes) != set(paths):
        raise ProtocolBundleError("protocol bundle has no complete source-byte binding")
    parsed_sources = {
        "protocol": yaml.safe_load(source_bytes["protocol"].decode("utf-8")),
        "schema": json.loads(source_bytes["schema"].decode("utf-8")),
        "reason_registry": yaml.safe_load(source_bytes["reason_registry"].decode("utf-8")),
        "reason_registry_schema": json.loads(
            source_bytes["reason_registry_schema"].decode("utf-8")
        ),
    }
    for name in parsed_sources:
        if parsed_sources[name] != bundle[name]:
            raise ProtocolBundleError(f"in-memory {name} differs from its loaded source bytes")
        if not paths[name].is_file() or paths[name].read_bytes() != source_bytes[name]:
            raise ProtocolBundleError(f"source file changed after bundle load: {paths[name]}")
    source_hashes = {
        name: hashlib.sha256(source_bytes[name]).hexdigest()
        for name in sorted(paths)
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


def verify_protocol_lock(bundle: dict[str, Any], lock: Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical lock only when it matches a freeze-ready source bundle."""
    if not isinstance(lock, Mapping):
        raise ProtocolBundleError("protocol lock must be a mapping")
    expected = build_protocol_lock(bundle)
    if not hmac.compare_digest(
        canonical_bytes(dict(lock)), canonical_bytes(expected)
    ):
        raise ProtocolBundleError("protocol lock does not match its freeze-ready source bundle")
    return expected


def write_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
