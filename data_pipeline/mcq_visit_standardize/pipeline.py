"""Standardize frozen visit extract rows. Never overwrites the extract."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from data_pipeline.mcq_visit_extract.atomic import (
    atomic_write_json,
    atomic_write_jsonl,
    canonical_hash,
    file_sha256,
    read_manifest,
    write_manifest,
)
from data_pipeline.mcq_visit_extract.columns import RESULT_COLUMNS

from .columns import MAPPING_VERSION, OUTPUT_COLUMNS, SCHEMA_NAME, SCHEMA_VERSION
from .inventory import add_inventory_from_visit, inventory_rows, review_rows
from .io import iter_json_array, write_csv, write_json_array
from .synonyms import load_reviewed_maps
from .transform import celsius_to_fahrenheit, standardize_visit


class StandardizeError(ValueError):
    pass


def _identity(
    input_path: Path,
    input_sha256: str,
    expected_count: int,
    synonym_table: Path | None,
) -> dict[str, Any]:
    return {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "mapping_version": MAPPING_VERSION,
        "input_path": str(input_path.resolve()),
        "input_sha256": input_sha256,
        "expected_count": expected_count,
        "output_columns": list(OUTPUT_COLUMNS),
        "synonym_table": str(synonym_table.resolve()) if synonym_table else None,
        "synonym_table_sha256": (
            file_sha256(synonym_table) if synonym_table and synonym_table.is_file() else None
        ),
    }


def _original_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for key in RESULT_COLUMNS:
        if left.get(key) != right.get(key):
            return False
    return True


def run(
    *,
    input_path: Path,
    output_dir: Path,
    expected_count: int,
    synonym_table: Path | None = None,
) -> dict[str, Any]:
    if not input_path.is_file():
        raise StandardizeError(f"input missing: {input_path}")
    if input_path.name not in {"visits.json"}:
        raise StandardizeError("input must be the extract visits.json")
    output_dir = output_dir.resolve()
    extract_dir = input_path.parent.resolve()
    if output_dir == extract_dir:
        raise StandardizeError("refusing to write into the extract directory")
    output_dir.mkdir(parents=True, exist_ok=True)

    input_sha = file_sha256(input_path)
    identity = _identity(input_path, input_sha, expected_count, synonym_table)
    identity_sha = canonical_hash(identity)
    manifest_path = output_dir / "manifest.json"
    existing = read_manifest(manifest_path)
    if existing is not None and existing.get("identity_sha256") != identity_sha:
        raise StandardizeError("manifest identity mismatch; refusing to mix runs")
    manifest = existing or {
        "identity": identity,
        "identity_sha256": identity_sha,
        "status": "running",
    }
    write_manifest(manifest_path, manifest)

    extra_maps = load_reviewed_maps(synonym_table) if synonym_table else {}
    extra_symptoms = extra_maps.get("symptom", {})
    extra_exams = extra_maps.get("radiology", {})
    visits: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    counts: dict[str, Counter[str]] = {}
    converted = 0
    converted_ok = 0
    mapped_cc = 0
    total_cc = 0
    for visit in iter_json_array(input_path):
        add_inventory_from_visit(visit, counts)
        standardized, review_items = standardize_visit(
            visit,
            extra_symptoms=extra_symptoms,
            extra_exams=extra_exams,
            extra_drugs=extra_maps.get("drug"),
            extra_allergies=extra_maps.get("allergy"),
            extra_units=extra_maps.get("unit"),
            extra_rhythms=extra_maps.get("rhythm"),
        )
        if not _original_equal(visit, standardized):
            raise StandardizeError(
                f"original columns mutated for hadm_id={visit.get('hadm_id')}"
            )
        visits.append(standardized)
        reviews.extend(review_items)
        concepts = standardized.get("chief_complaint_concepts") or []
        total_cc += len(concepts)
        mapped_cc += sum(1 for item in concepts if str(item.get("status", "")).startswith("mapped/"))
        temp_f = standardized.get("temperature_f")
        temp_c = standardized.get("temperature_c")
        if isinstance(temp_f, (int, float)) and isinstance(temp_c, (int, float)):
            converted += 1
            if abs(celsius_to_fahrenheit(float(temp_c)) - float(temp_f)) <= 0.15:
                converted_ok += 1
    if len(visits) != expected_count:
        raise StandardizeError(f"row count {len(visits)} != expected {expected_count}")
    hadm = [row["hadm_id"] for row in visits]
    if len(set(hadm)) != len(hadm):
        raise StandardizeError("hadm_id is not unique")

    inventory = inventory_rows(counts)
    queue = review_rows(reviews)
    atomic_write_jsonl(output_dir / "term_inventory.jsonl", inventory)
    atomic_write_jsonl(output_dir / "review_queue.jsonl", queue)
    json_hash = write_json_array(output_dir / "visits_standardized.json", visits)
    csv_hash = write_csv(output_dir / "visits_standardized.csv", visits)
    acceptance = {
        "records": len(visits),
        "mapping_version": MAPPING_VERSION,
        "unique_hadm_id": len(set(hadm)),
        "chief_complaint_concepts": total_cc,
        "chief_complaint_mapped": mapped_cc,
        "chief_complaint_mapped_rate": round(mapped_cc / total_cc, 4) if total_cc else None,
        "temperature_converted": converted,
        "temperature_reversible": converted_ok,
        "review_queue_rows": len(queue),
        "inventory_rows": len(inventory),
        "json_sha256": json_hash,
        "csv_sha256": csv_hash,
        "original_columns_preserved": True,
        "gold": 0,
        "status": "exploratory_unreviewed",
    }
    atomic_write_json(output_dir / "acceptance.json", acceptance)
    (output_dir / "visits_standardized.json.sha256").write_text(json_hash + "\n", encoding="ascii")
    (output_dir / "visits_standardized.csv.sha256").write_text(csv_hash + "\n", encoding="ascii")
    manifest["status"] = "complete"
    manifest["acceptance"] = acceptance
    write_manifest(manifest_path, manifest)
    return manifest


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standardize extracted visit rows")
    parser.add_argument("--input", type=Path, required=True, help="extract visits.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument(
        "--synonym-table",
        type=Path,
        help="reviewed_synonyms.jsonl from the chief-complaint review UI",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        manifest = run(
            input_path=args.input,
            output_dir=args.output_dir,
            expected_count=args.expected_count,
            synonym_table=args.synonym_table,
        )
    except (StandardizeError, ValueError, FileNotFoundError) as exc:
        print(f"mcq_visit_standardize failed: {exc}")
        return 1
    acceptance = manifest.get("acceptance") or {}
    print(
        f"complete records={acceptance.get('records')} "
        f"cc_mapped_rate={acceptance.get('chief_complaint_mapped_rate')} "
        f"review_queue={acceptance.get('review_queue_rows')} "
        f"output={args.output_dir}"
    )
    return 0
