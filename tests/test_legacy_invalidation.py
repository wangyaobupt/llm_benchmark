from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation_pipeline.governance.legacy import (
    LegacyArtifactError,
    assert_id_not_invalidated,
    assert_legacy_phenotype_formal_forbidden,
    assert_release_ids_not_invalidated,
    assert_split_not_legacy,
)


def _manifest(tmp_path: Path) -> Path:
    path = tmp_path / "legacy-invalidation-manifest.json"
    path.write_text(
        json.dumps(
            {
                "status": "active",
                "gold_count": 0,
                "invalidated_ids": {
                    "candidate_ids": ["cand_old"],
                    "rule_ids": ["rule_old"],
                    "question_ids": ["iq_old"],
                },
                "legacy_split_artifacts": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_invalidated_ids_are_rejected(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    with pytest.raises(LegacyArtifactError, match="invalidated_upstream_contract"):
        assert_id_not_invalidated("rule_old", kind="rule", manifest_path=manifest)


def test_release_records_reject_legacy_lineage(tmp_path: Path) -> None:
    with pytest.raises(LegacyArtifactError, match="invalidated_upstream_contract"):
        assert_release_ids_not_invalidated(
            [{"question_id": "iq_old"}], manifest_path=_manifest(tmp_path)
        )


def test_legacy_split_is_rejected_by_path_and_hash(tmp_path: Path) -> None:
    split = tmp_path / "subject_split.parquet"
    split.write_bytes(b"legacy")
    manifest = _manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    import hashlib

    payload["legacy_split_artifacts"] = [
        {"path": str(split.resolve()), "sha256": hashlib.sha256(b"legacy").hexdigest()}
    ]
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LegacyArtifactError, match="legacy_holdout_not_formal_final_test"):
        assert_split_not_legacy(split, manifest_path=manifest)


def test_legacy_phenotype_cannot_generate_formal() -> None:
    with pytest.raises(LegacyArtifactError, match="legacy_phenotype_formal_generation_forbidden"):
        assert_legacy_phenotype_formal_forbidden("formal")


def test_removed_phenotype_package_cannot_be_imported() -> None:
    import importlib

    with pytest.raises(LegacyArtifactError, match="legacy_phenotype_formal_generation_forbidden"):
        importlib.import_module("data_pipeline.phenotype")

