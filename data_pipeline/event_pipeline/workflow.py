"""Transactional orchestration for the complete event-processing workflow."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from .event_cleaning.pipeline import run_cleaning
from .event_cleaning.pipeline import CLEANING_LOGIC_VERSION
from .event_cleaning.source_catalog import (
    SOURCE_CATALOG_SHA256,
    SOURCE_CATALOG_VERSION,
)
from .event_normalization.pipeline import run_normalization
from .event_quality.audit_cleaning import audit as audit_cleaning
from .event_quality.audit_normalization import audit as audit_normalization
from .event_quality.reproducibility import compare_runs


WORKFLOW_VERSION = "event-workflow/1.1.0"


class EventWorkflowError(RuntimeError):
    """Raised when a workflow gate fails before publication."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _remove_temporary(directory: Path, expected_parent: Path) -> None:
    resolved = directory.resolve()
    parent = expected_parent.resolve()
    if resolved.parent != parent or not resolved.name.startswith("."):
        raise EventWorkflowError(
            f"refusing to remove unexpected temporary directory: {resolved}"
        )
    shutil.rmtree(resolved)


def _published_audit_paths(
    result: dict[str, Any],
    stage: str,
) -> dict[str, Any]:
    published = json.loads(json.dumps(result))
    inputs = published.get("inputs", {})
    for source_key in ("source_jsonl", "raw_source_jsonl"):
        if inputs.get(source_key):
            inputs[source_key] = Path(inputs[source_key]).name
    if stage == "cleaning":
        inputs.update(
            {
                "cleaned_events": "cleaning/cleaned_events.parquet",
                "cleaning_rejected": "cleaning/cleaning_rejected.parquet",
                "manifest": "cleaning/run_manifest.json",
                "source_reconciliation": "cleaning/source_reconciliation.json",
            }
        )
    else:
        inputs.update(
            {
                "cleaned_events": "cleaning/cleaned_events.parquet",
                "term_inventory": "cleaning/term_inventory.parquet",
                "normalized_events": "normalization/normalized_events.parquet",
                "normalization_mappings": "normalization/normalization_mappings.parquet",
                "normalization_review_queue": "normalization/normalization_review_queue.parquet",
                "normalization_manifest": "normalization/normalization_manifest.json",
            }
        )
    return published


def _run_data_stages(
    source_jsonl: Path,
    root: Path,
    *,
    batch_size: int,
    limit: int | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cleaning_directory = root / "cleaning"
    normalization_directory = root / "normalization"
    cleaning = run_cleaning(
        source_jsonl,
        cleaning_directory,
        batch_size=batch_size,
        limit=limit,
    )
    normalization = run_normalization(
        cleaning_directory / "cleaned_events.parquet",
        cleaning_directory / "term_inventory.parquet",
        normalization_directory,
        batch_size=batch_size,
    )
    return cleaning, normalization


def _cleanup_without_masking(
    directory: Path,
    expected_parent: Path,
    primary_error: Exception,
) -> None:
    """Best-effort cleanup that always preserves the stage's original error."""

    if not directory.exists():
        return
    try:
        _remove_temporary(directory, expected_parent)
    except Exception as cleanup_error:
        primary_error.add_note(f"temporary cleanup also failed: {cleanup_error}")


def _cleanup_incomplete_stage(
    directory: Path,
    staging_directory: Path,
    primary_error: Exception,
) -> None:
    resolved = directory.resolve()
    parent = staging_directory.resolve()
    if resolved.parent != parent or resolved.name not in {
        "normalization",
        ".replay",
        "quality",
    }:
        primary_error.add_note(
            f"refusing to remove unexpected incomplete stage: {resolved}"
        )
        return
    try:
        shutil.rmtree(resolved)
    except Exception as cleanup_error:
        primary_error.add_note(f"incomplete stage cleanup also failed: {cleanup_error}")


def _validate_resume_staging(
    staging_directory: Path,
    source_jsonl: Path,
    output_directory: Path,
    *,
    limit: int | None,
) -> dict[str, Any]:
    resolved = staging_directory.resolve()
    if resolved.parent != output_directory.parent.resolve():
        raise EventWorkflowError(
            "resume staging directory must share the output parent directory"
        )
    if not resolved.name.startswith(f".{output_directory.name}.tmp-"):
        raise EventWorkflowError(
            f"unexpected resume staging directory: {resolved}"
        )
    if output_directory.exists():
        raise EventWorkflowError(f"output already exists: {output_directory}")
    cleaning_directory = resolved / "cleaning"
    if not cleaning_directory.is_dir():
        raise EventWorkflowError("resume staging has no completed cleaning directory")
    for incomplete_stage in ("normalization", ".replay", "quality"):
        if (resolved / incomplete_stage).exists():
            raise EventWorkflowError(
                f"resume staging is not at the cleaning checkpoint: {incomplete_stage} exists"
            )
    manifest_path = cleaning_directory / "run_manifest.json"
    if not manifest_path.is_file():
        raise EventWorkflowError("resume staging is missing cleaning/run_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_contract = {
        "schema": {"name": "event_pipeline_run_manifest", "version": "1.1.0"},
        "cleaning_logic_version": CLEANING_LOGIC_VERSION,
        "source_catalog_version": SOURCE_CATALOG_VERSION,
        "source_catalog_sha256": SOURCE_CATALOG_SHA256,
    }
    observed_contract = {
        "schema": manifest.get("schema"),
        "cleaning_logic_version": manifest.get("cleaning_logic_version"),
        "source_catalog_version": manifest.get("source_catalog", {}).get("version"),
        "source_catalog_sha256": manifest.get("source_catalog", {}).get("sha256"),
    }
    if observed_contract != expected_contract:
        raise EventWorkflowError("resume cleaning manifest contract does not match current code")
    expected_input = {
        "filename": source_jsonl.name,
        "bytes": source_jsonl.stat().st_size,
        "sha256": _sha256(source_jsonl),
        "limit": limit,
    }
    if manifest.get("input") != expected_input:
        raise EventWorkflowError("resume source JSONL does not match the cleaning manifest")
    output_hashes = manifest.get("output_sha256", {})
    required_outputs = {
        "cleaned_events.parquet",
        "encounter_manifest.parquet",
        "cleaning_rejected.parquet",
        "term_inventory.parquet",
        "source_reconciliation.json",
    }
    if set(output_hashes) != required_outputs:
        raise EventWorkflowError("resume cleaning manifest has an unexpected output set")
    for filename in sorted(required_outputs):
        path = cleaning_directory / filename
        if not path.is_file() or _sha256(path) != output_hashes[filename]:
            raise EventWorkflowError(
                f"resume cleaning artifact hash mismatch: {filename}"
            )
    return manifest


def _complete_from_cleaning(
    source_jsonl: Path,
    raw_source_jsonl: Path,
    output_directory: Path,
    temporary: Path,
    cleaning: dict[str, Any],
    *,
    batch_size: int,
    replay_batch_size: int,
    limit: int | None,
    work_directory: Path | None,
) -> dict[str, Any]:
    cleaning_directory = temporary / "cleaning"
    normalization_directory = temporary / "normalization"
    replay_root = temporary / ".replay"
    cleaned_audit = audit_cleaning(
        cleaning_directory / "cleaned_events.parquet",
        cleaning_directory / "cleaning_rejected.parquet",
        source_jsonl,
        raw_source_jsonl,
        cleaning_directory / "source_reconciliation.json",
        cleaning_directory / "run_manifest.json",
        work_directory=work_directory,
    )
    if not cleaned_audit["acceptance"]["can_start_normalization"]:
        raise EventWorkflowError(
            "cleaning audit failed: "
            + ", ".join(cleaned_audit["acceptance"]["blocking_issue_codes"])
        )
    normalization = run_normalization(
        cleaning_directory / "cleaned_events.parquet",
        cleaning_directory / "term_inventory.parquet",
        normalization_directory,
        batch_size=batch_size,
    )
    normalized_audit = audit_normalization(
        cleaning_directory / "cleaned_events.parquet",
        cleaning_directory / "term_inventory.parquet",
        normalization_directory / "normalized_events.parquet",
        normalization_directory / "normalization_mappings.parquet",
        normalization_directory / "normalization_review_queue.parquet",
        normalization_directory / "normalization_manifest.json",
    )
    if not normalized_audit["acceptance"]["can_publish_normalization"]:
        raise EventWorkflowError(
            "normalization audit failed: "
            + ", ".join(
                normalized_audit["acceptance"]["blocking_issue_codes"]
            )
        )

    _run_data_stages(
        source_jsonl,
        replay_root,
        batch_size=replay_batch_size,
        limit=limit,
    )
    reproducibility = compare_runs(
        temporary,
        replay_root,
        canonical_batch_size=batch_size,
        replay_batch_size=replay_batch_size,
    )
    if not reproducibility["acceptance"]["reproducible"]:
        raise EventWorkflowError(
            "reproducibility failed: "
            + ", ".join(reproducibility["acceptance"]["blocking_issue_codes"])
        )
    _remove_temporary(replay_root, temporary)

    quality_directory = temporary / "quality"
    _write_json(
        quality_directory / "cleaned-events-acceptance-audit.json",
        _published_audit_paths(cleaned_audit, "cleaning"),
    )
    _write_json(
        quality_directory / "normalized-events-acceptance-audit.json",
        _published_audit_paths(normalized_audit, "normalization"),
    )
    _write_json(
        quality_directory / "reproducibility-report.json",
        reproducibility,
    )
    quality_hashes = {
        path.name: _sha256(path)
        for path in sorted(quality_directory.iterdir())
        if path.is_file()
    }
    source_hash = cleaned_audit["hashes"]["input"]
    raw_source_hash = cleaned_audit["hashes"]["raw_source"]
    workflow_manifest = {
        "schema": {"name": "event_workflow_manifest", "version": "1.1.0"},
        "workflow_version": WORKFLOW_VERSION,
        "run_id": hashlib.sha256(
            (
                f"{source_hash}|{raw_source_hash}|"
                f"{cleaning['run_id']}|{normalization['run_id']}|{limit}"
            ).encode("utf-8")
        ).hexdigest()[:24],
        "inputs": {
            "source_jsonl": source_jsonl.name,
            "source_jsonl_sha256": source_hash,
            "raw_source_jsonl": raw_source_jsonl.name,
            "raw_source_jsonl_sha256": raw_source_hash,
            "limit": limit,
        },
        "batch_sizes": {"canonical": batch_size, "replay": replay_batch_size},
        "stages": {
            "cleaning": {
                "run_id": cleaning["run_id"],
                "counts": cleaning["counts"],
                "output_sha256": cleaning["output_sha256"],
            },
            "normalization": {
                "run_id": normalization["run_id"],
                "counts": normalization["counts"],
                "output_sha256": normalization["output_sha256"],
            },
        },
        "quality_sha256": quality_hashes,
        "acceptance": {
            "cleaning": True,
            "normalization": True,
            "reproducible": True,
            "can_start_text_ner": True,
        },
    }
    _write_json(temporary / "workflow_manifest.json", workflow_manifest)
    os.replace(temporary, output_directory)
    return workflow_manifest


def run_workflow(
    source_jsonl: Path,
    raw_source_jsonl: Path,
    output_directory: Path,
    *,
    batch_size: int = 5000,
    replay_batch_size: int = 777,
    limit: int | None = None,
    work_directory: Path | None = None,
) -> dict[str, Any]:
    """Run cleaning, both audits, normalization, and reproducibility gates."""
    source_jsonl = Path(source_jsonl).resolve()
    raw_source_jsonl = Path(raw_source_jsonl).resolve()
    output_directory = Path(output_directory).resolve()
    for path in (source_jsonl, raw_source_jsonl):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output_directory.exists():
        raise EventWorkflowError(f"output already exists: {output_directory}")
    if batch_size < 1 or replay_batch_size < 1:
        raise ValueError("batch sizes must be positive")
    if batch_size == replay_batch_size:
        raise ValueError("replay batch size must differ from canonical batch size")
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.tmp-",
            dir=output_directory.parent,
        )
    )
    try:
        cleaning_directory = temporary / "cleaning"
        cleaning = run_cleaning(
            source_jsonl,
            cleaning_directory,
            batch_size=batch_size,
            limit=limit,
        )
        return _complete_from_cleaning(
            source_jsonl,
            raw_source_jsonl,
            output_directory,
            temporary,
            cleaning,
            batch_size=batch_size,
            replay_batch_size=replay_batch_size,
            limit=limit,
            work_directory=work_directory,
        )
    except Exception as error:
        _cleanup_without_masking(temporary, output_directory.parent, error)
        raise


def resume_workflow(
    staging_directory: Path,
    source_jsonl: Path,
    raw_source_jsonl: Path,
    output_directory: Path,
    *,
    batch_size: int = 5000,
    replay_batch_size: int = 777,
    limit: int | None = None,
    work_directory: Path | None = None,
) -> dict[str, Any]:
    """Resume only after verifying an immutable completed-cleaning checkpoint."""

    staging_directory = Path(staging_directory).resolve()
    source_jsonl = Path(source_jsonl).resolve()
    raw_source_jsonl = Path(raw_source_jsonl).resolve()
    output_directory = Path(output_directory).resolve()
    for path in (source_jsonl, raw_source_jsonl):
        if not path.is_file():
            raise FileNotFoundError(path)
    if batch_size < 1 or replay_batch_size < 1:
        raise ValueError("batch sizes must be positive")
    if batch_size == replay_batch_size:
        raise ValueError("replay batch size must differ from canonical batch size")
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    cleaning = _validate_resume_staging(
        staging_directory,
        source_jsonl,
        output_directory,
        limit=limit,
    )
    try:
        return _complete_from_cleaning(
            source_jsonl,
            raw_source_jsonl,
            output_directory,
            staging_directory,
            cleaning,
            batch_size=batch_size,
            replay_batch_size=replay_batch_size,
            limit=limit,
            work_directory=work_directory,
        )
    except Exception as error:
        for incomplete_stage in ("normalization", ".replay", "quality"):
            path = staging_directory / incomplete_stage
            if path.exists():
                _cleanup_incomplete_stage(path, staging_directory, error)
        raise


__all__ = [
    "EventWorkflowError",
    "WORKFLOW_VERSION",
    "resume_workflow",
    "run_workflow",
]
