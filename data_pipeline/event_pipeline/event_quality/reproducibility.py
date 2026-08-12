"""Independent byte-level comparison of two event workflow runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


CLEANING_FILES = (
    "cleaned_events.parquet",
    "cleaning_rejected.parquet",
    "encounter_manifest.parquet",
    "term_inventory.parquet",
    "source_reconciliation.json",
)
NORMALIZATION_FILES = (
    "normalized_events.parquet",
    "normalization_mappings.parquet",
    "normalization_review_queue.parquet",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare_runs(
    canonical_root: Path,
    replay_root: Path,
    *,
    canonical_batch_size: int,
    replay_batch_size: int,
) -> dict[str, Any]:
    """Compare all deterministic data products and their run contracts."""
    canonical_root = Path(canonical_root).resolve()
    replay_root = Path(replay_root).resolve()
    canonical_cleaning = canonical_root / "cleaning"
    replay_cleaning = replay_root / "cleaning"
    canonical_normalization = canonical_root / "normalization"
    replay_normalization = replay_root / "normalization"
    cleaning_manifest = _manifest(canonical_cleaning / "run_manifest.json")
    replay_cleaning_manifest = _manifest(replay_cleaning / "run_manifest.json")
    normalization_manifest = _manifest(
        canonical_normalization / "normalization_manifest.json"
    )
    replay_normalization_manifest = _manifest(
        replay_normalization / "normalization_manifest.json"
    )

    file_checks: dict[str, dict[str, Any]] = {}
    for stage, names, canonical_dir, replay_dir in (
        ("cleaning", CLEANING_FILES, canonical_cleaning, replay_cleaning),
        (
            "normalization",
            NORMALIZATION_FILES,
            canonical_normalization,
            replay_normalization,
        ),
    ):
        for name in names:
            canonical_hash = _sha256(canonical_dir / name)
            replay_hash = _sha256(replay_dir / name)
            file_checks[f"{stage}/{name}"] = {
                "canonical_sha256": canonical_hash,
                "replay_sha256": replay_hash,
                "equal": canonical_hash == replay_hash,
            }

    contract_checks = {
        "cleaning_run_id_equal": (
            cleaning_manifest.get("run_id")
            == replay_cleaning_manifest.get("run_id")
        ),
        "cleaning_counts_equal": (
            cleaning_manifest.get("counts")
            == replay_cleaning_manifest.get("counts")
        ),
        "cleaning_output_hashes_equal": (
            cleaning_manifest.get("output_sha256")
            == replay_cleaning_manifest.get("output_sha256")
        ),
        "normalization_run_id_equal": (
            normalization_manifest.get("run_id")
            == replay_normalization_manifest.get("run_id")
        ),
        "normalization_counts_equal": (
            normalization_manifest.get("counts")
            == replay_normalization_manifest.get("counts")
        ),
        "normalization_output_hashes_equal": (
            normalization_manifest.get("output_sha256")
            == replay_normalization_manifest.get("output_sha256")
        ),
    }
    failed = [
        name for name, result in file_checks.items() if not result["equal"]
    ] + [name for name, passed in contract_checks.items() if not passed]
    return {
        "schema": {
            "name": "event_workflow_reproducibility",
            "version": "1.0.0",
        },
        "batch_sizes": {
            "canonical": canonical_batch_size,
            "replay": replay_batch_size,
        },
        "file_checks": file_checks,
        "contract_checks": contract_checks,
        "acceptance": {
            "reproducible": not failed,
            "blocking_issue_codes": sorted(failed),
        },
    }


__all__ = ["CLEANING_FILES", "NORMALIZATION_FILES", "compare_runs"]
