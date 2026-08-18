"""Fail-closed gates for artifacts invalidated by the investigation-selection rebuild.

The legacy manifest is an audit record, not an input to the new pipeline.  This
module deliberately rejects known legacy IDs and the legacy holdout artifact at
the points where artifacts can enter review, release, or formal splitting.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "docs" / "legacy-invalidation-manifest.json"

INVALIDATED_UPSTREAM_CONTRACT = "invalidated_upstream_contract"
LEGACY_HOLDOUT_NOT_FORMAL_FINAL_TEST = "legacy_holdout_not_formal_final_test"
LEGACY_PHENOTYPE_FORMAL_FORBIDDEN = "legacy_phenotype_formal_generation_forbidden"


class LegacyArtifactError(ValueError):
    """Raised when an invalidated artifact is about to enter a formal path."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = Path(path or DEFAULT_MANIFEST)
    if not manifest_path.is_file():
        raise LegacyArtifactError(
            f"legacy invalidation manifest is missing: {manifest_path}"
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("status") != "active" or payload.get("gold_count") != 0:
        raise LegacyArtifactError("legacy invalidation manifest is not an active gold=0 gate")
    return payload


def _artifact_sets(manifest: Mapping[str, Any]) -> tuple[set[str], set[str], set[str]]:
    ids = manifest.get("invalidated_ids", {})
    return (
        set(ids.get("candidate_ids", [])),
        set(ids.get("rule_ids", [])),
        set(ids.get("question_ids", [])),
    )


def assert_id_not_invalidated(
    artifact_id: str,
    *,
    kind: str,
    manifest_path: Path | None = None,
) -> None:
    candidates, rules, questions = _artifact_sets(load_manifest(manifest_path))
    pools = {"candidate": candidates, "rule": rules, "question": questions}
    if kind not in pools:
        raise ValueError(f"unsupported legacy artifact kind: {kind}")
    if artifact_id in pools[kind]:
        raise LegacyArtifactError(
            f"{kind} ID {artifact_id} is blocked: {INVALIDATED_UPSTREAM_CONTRACT}"
        )


def assert_ids_not_invalidated(
    artifact_ids: Iterable[str],
    *,
    kind: str,
    manifest_path: Path | None = None,
) -> None:
    for artifact_id in artifact_ids:
        assert_id_not_invalidated(artifact_id, kind=kind, manifest_path=manifest_path)


def assert_split_not_legacy(
    split_path: Path,
    *,
    manifest_path: Path | None = None,
) -> None:
    manifest = load_manifest(manifest_path)
    resolved = Path(split_path).resolve()
    split_records = manifest.get("legacy_split_artifacts", [])
    current_hash = _sha256_file(resolved) if resolved.is_file() else None
    for record in split_records:
        if record.get("sha256") == current_hash or record.get("path") == str(resolved):
            raise LegacyArtifactError(
                f"legacy split is blocked: {LEGACY_HOLDOUT_NOT_FORMAL_FINAL_TEST}"
            )


def assert_legacy_phenotype_formal_forbidden(profile: str) -> None:
    if profile == "formal":
        raise LegacyArtifactError(
            "the legacy phenotype entrypoint cannot generate formal artifacts: "
            f"{LEGACY_PHENOTYPE_FORMAL_FORBIDDEN}; use the new investigation-selection "
            "decision_document pipeline"
        )


def assert_release_ids_not_invalidated(
    records: Iterable[Mapping[str, Any]], *, manifest_path: Path | None = None
) -> None:
    manifest = load_manifest(manifest_path)
    candidates, rules, questions = _artifact_sets(manifest)
    for record in records:
        for key, pool, kind in (
            ("target_investigation_id", candidates, "candidate"),
            ("source_rule_id", rules, "rule"),
            ("question_id", questions, "question"),
        ):
            value = record.get(key)
            if value in pool:
                raise LegacyArtifactError(
                    f"{kind} ID {value} is blocked: {INVALIDATED_UPSTREAM_CONTRACT}"
                )

