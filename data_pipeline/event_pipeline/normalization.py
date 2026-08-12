"""Deterministic second-stage terminology and unit normalization."""

from __future__ import annotations

from collections import Counter
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any

import pyarrow.parquet as pq

from .pipeline import (
    PARQUET_ROW_GROUP_SIZE,
    BufferedParquetWriter,
    _json_dump,
    _safe_remove_temporary,
    _sha256,
)
from .schemas import (
    EVENT_ARROW_SCHEMA,
    MAPPING_ARROW_SCHEMA,
    REVIEW_ARROW_SCHEMA,
)
from .terminology import (
    MAPPING_VERSION,
    normalize_event,
    normalized_text,
    resolve_term,
    resolve_unit,
)
from .validation import EventPipelineError, EventValidator


def _term_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        row.get("entity_type") or "<none>",
        row.get("source_concept_id") or "<none>",
        normalized_text(row.get("source_label") or row.get("source_label_example")) or "<missing>",
        row.get("unit") or "<none>",
    )


def run_normalization(
    cleaned_events_path: Path,
    term_inventory_path: Path,
    output_directory: Path,
    *,
    batch_size: int = 5000,
) -> dict[str, Any]:
    cleaned_events_path = Path(cleaned_events_path).resolve()
    term_inventory_path = Path(term_inventory_path).resolve()
    output_directory = Path(output_directory).resolve()
    for path in (cleaned_events_path, term_inventory_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output_directory.exists():
        raise EventPipelineError("OUTPUT_ALREADY_EXISTS", str(output_directory))
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.tmp-", dir=output_directory.parent
        )
    )
    normalized_writer = BufferedParquetWriter(
        temporary / "normalized_events.parquet",
        EVENT_ARROW_SCHEMA,
        PARQUET_ROW_GROUP_SIZE,
    )
    mapping_writer = BufferedParquetWriter(
        temporary / "normalization_mappings.parquet",
        MAPPING_ARROW_SCHEMA,
        PARQUET_ROW_GROUP_SIZE,
    )
    review_writer = BufferedParquetWriter(
        temporary / "normalization_review_queue.parquet",
        REVIEW_ARROW_SCHEMA,
        PARQUET_ROW_GROUP_SIZE,
    )
    validator = EventValidator()
    status_counts: Counter[str] = Counter()
    unit_status_counts: Counter[str] = Counter()
    event_count = 0
    try:
        inventory_table = pq.read_table(term_inventory_path)
        mapping_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for inventory in inventory_table.to_pylist():
            resolution = resolve_term(
                inventory.get("entity_type"),
                inventory.get("source_concept_id"),
                inventory.get("source_label_example"),
            )
            normalized_unit, unit_status = resolve_unit(inventory.get("unit"))
            key = _term_key(inventory)
            mapping = {
                "schema_version": "1.0.0",
                "entity_type": inventory["entity_type"],
                "source_concept_id": inventory.get("source_concept_id"),
                "normalized_source_label": inventory["normalized_source_label"],
                "source_label_example": inventory["source_label_example"],
                "concept_id": resolution["concept_id"],
                "preferred_name": resolution["preferred_name"],
                "normalization_status": resolution["normalization_status"],
                "source_unit": inventory.get("unit"),
                "normalized_unit": normalized_unit,
                "unit_normalization_status": unit_status,
                "mapping_rule": resolution["mapping_rule"],
                "mapping_version": MAPPING_VERSION,
                "event_count": inventory["event_count"],
            }
            mapping_by_key[key] = mapping
            mapping_writer.write(mapping)
            review_reasons = []
            if mapping["normalization_status"] == "unresolved":
                review_reasons.append("TERM_UNRESOLVED")
            if mapping["unit_normalization_status"] == "unresolved":
                review_reasons.append("UNIT_UNRESOLVED")
            if review_reasons:
                review_writer.write(
                    {
                        "schema_version": "1.0.0",
                        "entity_type": inventory["entity_type"],
                        "source_concept_id": inventory.get("source_concept_id"),
                        "normalized_source_label": inventory["normalized_source_label"],
                        "source_label_example": inventory["source_label_example"],
                        "unit": inventory.get("unit"),
                        "normalized_unit": normalized_unit,
                        "unit_normalization_status": unit_status,
                        "review_reason": "+".join(review_reasons),
                        "event_count": inventory["event_count"],
                        "first_event_id": inventory["first_event_id"],
                        "mapping_version": MAPPING_VERSION,
                    }
                )

        parquet = pq.ParquetFile(cleaned_events_path)
        known_source_ids: set[str] = set()
        event_ids: set[str] = set()
        for batch in parquet.iter_batches(batch_size=batch_size):
            rows = batch.to_pylist()
            known_source_ids.update(row["source_row_id"] for row in rows)
            known_source_ids.update(
                source_id
                for row in rows
                for source_id in row["supporting_source_row_ids"]
            )
            normalized_rows = []
            for row in rows:
                if row.get("normalization_status") is not None:
                    raise EventPipelineError(
                        "CLEANED_EVENT_ALREADY_NORMALIZED", row["event_id"]
                    )
                key = _term_key(row)
                normalized, mapping_rule = normalize_event(dict(row))
                if normalized["entity_type"] is not None:
                    mapping = mapping_by_key.get(key)
                    if mapping is None:
                        raise EventPipelineError(
                            "TERM_NOT_IN_INVENTORY", normalized["event_id"]
                        )
                    if (
                        normalized["concept_id"] != mapping["concept_id"]
                        or normalized["normalization_status"] != mapping["normalization_status"]
                        or normalized["normalized_unit"] != mapping["normalized_unit"]
                        or normalized["unit_normalization_status"] != mapping["unit_normalization_status"]
                        or mapping_rule != mapping["mapping_rule"]
                    ):
                        raise EventPipelineError(
                            "MAPPING_APPLICATION_MISMATCH", normalized["event_id"]
                        )
                if normalized["normalization_status"] not in {
                    "mapped", "unresolved", "not_applicable"
                }:
                    raise EventPipelineError(
                        "NORMALIZATION_STATUS_MISSING", normalized["event_id"]
                    )
                if normalized["event_id"] in event_ids:
                    raise EventPipelineError("DUPLICATE_EVENT_ID", normalized["event_id"])
                event_ids.add(normalized["event_id"])
                normalized_rows.append(normalized)
                status_counts[normalized["normalization_status"]] += 1
                unit_status_counts[normalized["unit_normalization_status"]] += 1
            for normalized in normalized_rows:
                validator.validate(normalized, known_source_ids)
                normalized_writer.write(normalized)
                event_count += 1

        normalized_writer.close()
        mapping_writer.close()
        review_writer.close()
        output_files = (
            "normalized_events.parquet",
            "normalization_mappings.parquet",
            "normalization_review_queue.parquet",
        )
        output_hashes = {name: _sha256(temporary / name) for name in output_files}
        input_hash = _sha256(cleaned_events_path)
        manifest = {
            "schema": {"name": "normalization_run_manifest", "version": "1.0.0"},
            "run_id": hashlib.sha256(
                f"{input_hash}|{MAPPING_VERSION}".encode("utf-8")
            ).hexdigest()[:24],
            "inputs": {
                "cleaned_events": cleaned_events_path.name,
                "cleaned_events_sha256": input_hash,
                "term_inventory": term_inventory_path.name,
                "term_inventory_sha256": _sha256(term_inventory_path),
            },
            "mapping_version": MAPPING_VERSION,
            "counts": {
                "events": event_count,
                "mapping_rows": len(mapping_by_key),
                "review_queue_rows": sum(
                    mapping["normalization_status"] == "unresolved"
                    or mapping["unit_normalization_status"] == "unresolved"
                    for mapping in mapping_by_key.values()
                ),
            },
            "normalization_status_counts": dict(sorted(status_counts.items())),
            "unit_normalization_status_counts": dict(sorted(unit_status_counts.items())),
            "output_sha256": output_hashes,
        }
        _json_dump(temporary / "normalization_manifest.json", manifest)
        os.replace(temporary, output_directory)
        return manifest
    except Exception:
        for writer in (normalized_writer, mapping_writer, review_writer):
            try:
                writer.close()
            except Exception:
                pass
        if temporary.exists():
            _safe_remove_temporary(temporary, output_directory.parent)
        raise
