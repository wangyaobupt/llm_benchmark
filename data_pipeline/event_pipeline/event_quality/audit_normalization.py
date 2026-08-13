"""Independent acceptance audit for deterministic event normalization output."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
from itertools import zip_longest
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from ..event_contracts.schemas import (
    EVENT_ARROW_SCHEMA,
    MAPPING_ARROW_SCHEMA,
    REVIEW_ARROW_SCHEMA,
    TERM_INVENTORY_ARROW_SCHEMA,
)


EXPECTED_MAPPING_VERSION = "event-terminology/1.1.0"
MUTABLE_EVENT_FIELDS = {
    "concept_id",
    "preferred_name",
    "normalization_status",
    "terminology_mapping_version",
    "normalized_value_numeric",
    "normalized_value_text",
    "normalized_unit",
    "unit_normalization_status",
}
REVIEWED_TEXT_MAPPINGS = {
    ("symptom", "chest pain"): (
        "symptom:chest_pain",
        "Chest pain",
        "reviewed-synonym",
    ),
    ("imaging_study", "general xray"): (
        "investigation:general_xray",
        "General radiography",
        "reviewed-local-order-subtype",
    ),
}
UNIT_ALIASES = {
    "/min": "/min",
    "#/hpf": "#/hpf",
    "#/lpf": "#/lpf",
    "#/ul": "#/uL",
    "%": "%",
    "/hpf": "/hpf",
    "day": "day",
    "fl": "fL",
    "g/dl": "g/dL",
    "grams": "g",
    "hour": "h",
    "iu/l": "IU/L",
    "iu/ml": "IU/mL",
    "k/ul": "K/uL",
    "l": "L",
    "l/min": "L/min",
    "log10 iu/ml": "log10 IU/mL",
    "m/ul": "m/uL",
    "mcg": "mcg",
    "meq": "mEq",
    "meq.": "mEq",
    "meq/l": "mEq/L",
    "mg": "mg",
    "mg/24hr": "mg/24 h",
    "mg/dl": "mg/dL",
    "mg/l": "mg/L",
    "mg/mg": "mg/mg",
    "min": "min",
    "ml": "mL",
    "mm hg": "mmHg",
    "mm/hr": "mm/h",
    "mmhg": "mmHg",
    "mmol": "mmol",
    "mmol/l": "mmol/L",
    "mosm/kg": "mOsm/kg",
    "ng/dl": "ng/dL",
    "ng/ml": "ng/mL",
    "ng/ml feu": "ng/mL FEU",
    "pg": "pg",
    "pg/ml": "pg/mL",
    "ratio": "ratio",
    "sec": "s",
    "ug/dl": "ug/dL",
    "ug/ml": "ug/mL",
    "uiu/ml": "uIU/mL",
    "units": "units",
    "°f": "°F",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalized_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def _term_key(row: dict[str, Any], *, unit_field: str = "unit") -> tuple[str, str, str, str]:
    return (
        row.get("entity_type") or "<none>",
        row.get("source_concept_id") or "<none>",
        _normalized_text(
            row.get("source_label") or row.get("source_label_example")
        )
        or "<missing>",
        row.get(unit_field) or "<none>",
    )


def _source_code_is_usable(source_concept_id: str) -> bool:
    vocabulary, separator, code = source_concept_id.partition(":")
    if not separator or not code:
        return False
    if vocabulary == "ndc":
        return bool(re.fullmatch(r"\d{11}", code)) and set(code) != {"0"}
    if vocabulary == "gsn":
        return bool(re.fullmatch(r"\d{6}", code))
    return True


def _expected_term_resolution(row: dict[str, Any]) -> dict[str, str | None]:
    entity_type = row.get("entity_type")
    source_concept_id = row.get("source_concept_id")
    source_label = row.get("source_label") or row.get("source_label_example")
    if source_concept_id and _source_code_is_usable(source_concept_id):
        return {
            "concept_id": source_concept_id,
            "preferred_name": source_label or source_concept_id,
            "normalization_status": "mapped",
            "mapping_rule": "source-code",
        }
    if source_concept_id:
        return {
            "concept_id": None,
            "preferred_name": source_label,
            "normalization_status": "unresolved",
            "mapping_rule": "invalid-source-code",
        }
    reviewed = REVIEWED_TEXT_MAPPINGS.get(
        (entity_type, _normalized_text(source_label))
    )
    if reviewed:
        concept_id, preferred_name, mapping_rule = reviewed
        return {
            "concept_id": concept_id,
            "preferred_name": preferred_name,
            "normalization_status": "mapped",
            "mapping_rule": mapping_rule,
        }
    if entity_type is None:
        return {
            "concept_id": None,
            "preferred_name": None,
            "normalization_status": "not_applicable",
            "mapping_rule": "not-applicable",
        }
    return {
        "concept_id": None,
        "preferred_name": source_label,
        "normalization_status": "unresolved",
        "mapping_rule": "unresolved",
    }


def _expected_unit(unit: str | None) -> tuple[str | None, str]:
    if unit in (None, ""):
        return None, "not_applicable"
    normalized = _normalized_text(unit)
    if normalized == "n/a":
        return None, "not_applicable"
    mapped = UNIT_ALIASES.get(normalized)
    return mapped, "mapped" if mapped else "unresolved"


def _arrow_type_contract(data_type: pa.DataType) -> Any:
    if pa.types.is_list(data_type) or pa.types.is_large_list(data_type):
        return (str(data_type.id), _arrow_type_contract(data_type.value_type))
    return str(data_type)


def _arrow_schema_matches(actual: pa.Schema, expected: pa.Schema) -> bool:
    if len(actual) != len(expected) or actual.metadata != expected.metadata:
        return False
    return all(
        actual_field.name == expected_field.name
        and actual_field.nullable == expected_field.nullable
        and _arrow_type_contract(actual_field.type)
        == _arrow_type_contract(expected_field.type)
        for actual_field, expected_field in zip(actual, expected)
    )


def _add_issue(
    counts: Counter[str], examples: dict[str, list[str]], issue: str, example: str
) -> None:
    counts[issue] += 1
    if len(examples[issue]) < 5:
        examples[issue].append(example)


def _iter_parquet_rows(
    parquet_file: pq.ParquetFile,
    *,
    batch_size: int = 8192,
):
    for batch in parquet_file.iter_batches(batch_size=batch_size):
        yield from batch.to_pylist()


def audit(
    cleaned_path: Path,
    term_inventory_path: Path,
    normalized_path: Path,
    mappings_path: Path,
    review_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    cleaned_file = pq.ParquetFile(cleaned_path)
    inventory_file = pq.ParquetFile(term_inventory_path)
    normalized_file = pq.ParquetFile(normalized_path)
    mappings_file = pq.ParquetFile(mappings_path)
    review_file = pq.ParquetFile(review_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    issue_counts: Counter[str] = Counter()
    issue_examples: dict[str, list[str]] = defaultdict(list)
    schema_matches = {
        "cleaned_events": _arrow_schema_matches(cleaned_file.schema_arrow, EVENT_ARROW_SCHEMA),
        "term_inventory": _arrow_schema_matches(
            inventory_file.schema_arrow, TERM_INVENTORY_ARROW_SCHEMA
        ),
        "normalized_events": _arrow_schema_matches(
            normalized_file.schema_arrow, EVENT_ARROW_SCHEMA
        ),
        "normalization_mappings": _arrow_schema_matches(
            mappings_file.schema_arrow, MAPPING_ARROW_SCHEMA
        ),
        "normalization_review_queue": _arrow_schema_matches(
            review_file.schema_arrow, REVIEW_ARROW_SCHEMA
        ),
    }
    for name, matched in schema_matches.items():
        if not matched:
            _add_issue(issue_counts, issue_examples, "arrow_schema_mismatch", name)

    immutable_fields = [
        field for field in EVENT_ARROW_SCHEMA.names if field not in MUTABLE_EVENT_FIELDS
    ]
    inventory_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    inventory_rows = 0
    for row in _iter_parquet_rows(inventory_file):
        inventory_rows += 1
        key = _term_key(row)
        if key in inventory_by_key:
            _add_issue(
                issue_counts,
                issue_examples,
                "duplicate_term_inventory_key",
                repr(key),
            )
        inventory_by_key[key] = row

    mappings_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    mapping_rule_counts: Counter[str] = Counter()
    mapping_rows = 0
    for row in _iter_parquet_rows(mappings_file):
        mapping_rows += 1
        key = _term_key(row, unit_field="source_unit")
        if key in mappings_by_key:
            _add_issue(
                issue_counts,
                issue_examples,
                "duplicate_mapping_key",
                repr(key),
            )
        mappings_by_key[key] = row
        mapping_rule_counts[str(row.get("mapping_rule"))] += 1
        source = inventory_by_key.get(key)
        if source is None:
            _add_issue(issue_counts, issue_examples, "mapping_without_inventory", repr(key))
            continue
        copied_fields = {
            "entity_type": source.get("entity_type"),
            "source_concept_id": source.get("source_concept_id"),
            "normalized_source_label": source.get("normalized_source_label"),
            "source_label_example": source.get("source_label_example"),
            "source_unit": source.get("unit"),
            "event_count": source.get("event_count"),
        }
        if any(row.get(field) != value for field, value in copied_fields.items()):
            _add_issue(
                issue_counts,
                issue_examples,
                "mapping_inventory_fields_mismatch",
                repr(key),
            )
        expected_term = _expected_term_resolution(source)
        expected_unit, expected_unit_status = _expected_unit(source.get("unit"))
        expected = {
            **expected_term,
            "normalized_unit": expected_unit,
            "unit_normalization_status": expected_unit_status,
            "mapping_version": EXPECTED_MAPPING_VERSION,
        }
        if any(row.get(field) != value for field, value in expected.items()):
            _add_issue(
                issue_counts,
                issue_examples,
                "mapping_rule_application_mismatch",
                repr(key),
            )

    for key in sorted(set(inventory_by_key) - set(mappings_by_key)):
        _add_issue(issue_counts, issue_examples, "inventory_mapping_missing", repr(key))

    expected_review: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for key, mapping in mappings_by_key.items():
        reasons = []
        if mapping.get("normalization_status") == "unresolved":
            reasons.append("TERM_UNRESOLVED")
        if mapping.get("unit_normalization_status") == "unresolved":
            reasons.append("UNIT_UNRESOLVED")
        if reasons:
            expected_review[key] = {
                "review_reason": "+".join(reasons),
                "mapping": mapping,
                "inventory": inventory_by_key[key],
            }
    review_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    review_reason_counts: Counter[str] = Counter()
    review_rows = 0
    for row in _iter_parquet_rows(review_file):
        review_rows += 1
        key = _term_key(row)
        if key in review_by_key:
            _add_issue(issue_counts, issue_examples, "duplicate_review_key", repr(key))
        review_by_key[key] = row
        review_reason_counts[str(row.get("review_reason"))] += 1
        expected = expected_review.get(key)
        if expected is None:
            _add_issue(issue_counts, issue_examples, "unexpected_review_row", repr(key))
            continue
        mapping = expected["mapping"]
        inventory_row = expected["inventory"]
        expected_fields = {
            "entity_type": mapping.get("entity_type"),
            "source_concept_id": mapping.get("source_concept_id"),
            "normalized_source_label": mapping.get("normalized_source_label"),
            "source_label_example": mapping.get("source_label_example"),
            "unit": mapping.get("source_unit"),
            "normalized_unit": mapping.get("normalized_unit"),
            "unit_normalization_status": mapping.get("unit_normalization_status"),
            "review_reason": expected["review_reason"],
            "event_count": mapping.get("event_count"),
            "first_event_id": inventory_row.get("first_event_id"),
            "mapping_version": EXPECTED_MAPPING_VERSION,
        }
        if any(row.get(field) != value for field, value in expected_fields.items()):
            _add_issue(
                issue_counts,
                issue_examples,
                "review_row_fields_mismatch",
                repr(key),
            )
    for key in sorted(set(expected_review) - set(review_by_key)):
        _add_issue(issue_counts, issue_examples, "expected_review_row_missing", repr(key))

    status_counts: Counter[Any] = Counter()
    unit_status_counts: Counter[Any] = Counter()
    status_by_source: Counter[tuple[Any, Any]] = Counter()
    status_by_entity: Counter[tuple[Any, Any]] = Counter()
    cleaned_rows = normalized_rows = 0
    event_id_sequence_equal = True
    identity_db = sqlite3.connect("")
    identity_db.execute("PRAGMA temp_store=FILE")
    identity_db.execute(
        "CREATE TABLE event_ids(dataset TEXT NOT NULL, event_id TEXT NOT NULL, "
        "PRIMARY KEY(dataset, event_id)) WITHOUT ROWID"
    )
    for source, target in zip_longest(
        _iter_parquet_rows(cleaned_file), _iter_parquet_rows(normalized_file)
    ):
        if source is None:
            event_id_sequence_equal = False
            normalized_rows += 1
            event_id = str(target.get("event_id"))
            try:
                identity_db.execute(
                    "INSERT INTO event_ids VALUES ('normalized', ?)", (event_id,)
                )
            except sqlite3.IntegrityError:
                _add_issue(
                    issue_counts,
                    issue_examples,
                    "duplicate_normalized_event_id",
                    event_id,
                )
            status = target.get("normalization_status")
            unit_status = target.get("unit_normalization_status")
            status_counts[status] += 1
            unit_status_counts[unit_status] += 1
            status_by_source[(target.get("source_table"), status)] += 1
            status_by_entity[(target.get("entity_type"), status)] += 1
            _add_issue(issue_counts, issue_examples, "normalized_event_extra", event_id)
            continue
        if target is None:
            event_id_sequence_equal = False
            cleaned_rows += 1
            event_id = str(source.get("event_id"))
            try:
                identity_db.execute(
                    "INSERT INTO event_ids VALUES ('cleaned', ?)", (event_id,)
                )
            except sqlite3.IntegrityError:
                _add_issue(
                    issue_counts,
                    issue_examples,
                    "duplicate_cleaned_event_id",
                    event_id,
                )
            _add_issue(issue_counts, issue_examples, "normalized_event_missing", event_id)
            continue
        cleaned_rows += 1
        normalized_rows += 1
        event_id = str(source.get("event_id"))
        for dataset, row in (("cleaned", source), ("normalized", target)):
            candidate = str(row.get("event_id"))
            try:
                identity_db.execute(
                    "INSERT INTO event_ids VALUES (?, ?)", (dataset, candidate)
                )
            except sqlite3.IntegrityError:
                _add_issue(
                    issue_counts,
                    issue_examples,
                    f"duplicate_{dataset}_event_id",
                    candidate,
                )
        if source.get("event_id") != target.get("event_id"):
            event_id_sequence_equal = False
            _add_issue(
                issue_counts,
                issue_examples,
                "event_id_sequence_mismatch",
                f"{source.get('event_id')}!={target.get('event_id')}",
            )
        if any(source.get(field) is not None for field in MUTABLE_EVENT_FIELDS):
            _add_issue(issue_counts, issue_examples, "cleaned_event_already_normalized", event_id)
        changed_fields = [
            field for field in immutable_fields if source.get(field) != target.get(field)
        ]
        if changed_fields:
            _add_issue(
                issue_counts,
                issue_examples,
                "immutable_event_field_changed",
                f"{event_id}:{','.join(changed_fields)}",
            )
        if target.get("normalized_value_numeric") != source.get("value_numeric"):
            _add_issue(issue_counts, issue_examples, "normalized_numeric_value_changed", event_id)
        if target.get("normalized_value_text") != source.get("value_text"):
            _add_issue(issue_counts, issue_examples, "normalized_text_value_changed", event_id)

        mapping = mappings_by_key.get(_term_key(source))
        if source.get("entity_type") is not None and mapping is None:
            _add_issue(issue_counts, issue_examples, "event_mapping_missing", event_id)
        else:
            expected_term = _expected_term_resolution(source)
            expected_unit, expected_unit_status = _expected_unit(source.get("unit"))
            expected_event_fields = {
                **{
                    field: value
                    for field, value in expected_term.items()
                    if field != "mapping_rule"
                },
                "terminology_mapping_version": EXPECTED_MAPPING_VERSION,
                "normalized_unit": expected_unit,
                "unit_normalization_status": expected_unit_status,
            }
            if any(
                target.get(field) != value
                for field, value in expected_event_fields.items()
            ):
                _add_issue(
                    issue_counts,
                    issue_examples,
                    "event_mapping_application_mismatch",
                    event_id,
                )
        status = target.get("normalization_status")
        unit_status = target.get("unit_normalization_status")
        status_counts[status] += 1
        unit_status_counts[unit_status] += 1
        status_by_source[(target.get("source_table"), status)] += 1
        status_by_entity[(target.get("entity_type"), status)] += 1
    identity_db.close()
    hashes = {
        "cleaned_events.parquet": _sha256(cleaned_path),
        "term_inventory.parquet": _sha256(term_inventory_path),
        "normalized_events.parquet": _sha256(normalized_path),
        "normalization_mappings.parquet": _sha256(mappings_path),
        "normalization_review_queue.parquet": _sha256(review_path),
    }
    manifest_contract = {
        "schema": manifest.get("schema")
        == {"name": "normalization_run_manifest", "version": "1.0.0"},
        "mapping_version": manifest.get("mapping_version")
        == EXPECTED_MAPPING_VERSION,
        "cleaned_events_sha256": manifest.get("inputs", {}).get(
            "cleaned_events_sha256"
        )
        == hashes["cleaned_events.parquet"],
        "term_inventory_sha256": manifest.get("inputs", {}).get(
            "term_inventory_sha256"
        )
        == hashes["term_inventory.parquet"],
        "events": manifest.get("counts", {}).get("events") == normalized_rows,
        "mapping_rows": manifest.get("counts", {}).get("mapping_rows")
        == mapping_rows,
        "review_queue_rows": manifest.get("counts", {}).get("review_queue_rows")
        == review_rows,
        "normalization_status_counts": manifest.get("normalization_status_counts")
        == dict(sorted(status_counts.items())),
        "unit_normalization_status_counts": manifest.get(
            "unit_normalization_status_counts"
        )
        == dict(sorted(unit_status_counts.items())),
    }
    for filename in (
        "normalized_events.parquet",
        "normalization_mappings.parquet",
        "normalization_review_queue.parquet",
    ):
        manifest_contract[f"hash:{filename}"] = (
            manifest.get("output_sha256", {}).get(filename) == hashes[filename]
        )
    for name, matched in manifest_contract.items():
        if not matched:
            _add_issue(issue_counts, issue_examples, "manifest_contract_mismatch", name)

    material_issues = {key: value for key, value in issue_counts.items() if value}
    return {
        "audit_schema": "normalized_events_acceptance_audit/1.0.0",
        "inputs": {
            "cleaned_events": str(cleaned_path),
            "term_inventory": str(term_inventory_path),
            "normalized_events": str(normalized_path),
            "normalization_mappings": str(mappings_path),
            "normalization_review_queue": str(review_path),
            "normalization_manifest": str(manifest_path),
        },
        "rows": {
            "cleaned_events": cleaned_rows,
            "term_inventory": inventory_rows,
            "normalized_events": normalized_rows,
            "normalization_mappings": mapping_rows,
            "normalization_review_queue": review_rows,
        },
        "hashes": hashes,
        "schema_matches": schema_matches,
        "manifest_contract": manifest_contract,
        "event_invariants": {
            "same_row_count": cleaned_rows == normalized_rows,
            "event_id_sequence_equal": event_id_sequence_equal,
            "immutable_fields_checked": immutable_fields,
            "mutable_fields_allowed": sorted(MUTABLE_EVENT_FIELDS),
        },
        "normalization_status_counts": dict(sorted(status_counts.items())),
        "unit_normalization_status_counts": dict(sorted(unit_status_counts.items())),
        "mapping_rule_counts": dict(sorted(mapping_rule_counts.items())),
        "review_reason_counts": dict(sorted(review_reason_counts.items())),
        "status_by_source": [
            {"source_table": table, "normalization_status": status, "events": count}
            for (table, status), count in sorted(status_by_source.items())
        ],
        "status_by_entity": [
            {"entity_type": entity, "normalization_status": status, "events": count}
            for (entity, status), count in sorted(status_by_entity.items())
        ],
        "issues": {
            "counts": dict(sorted(material_issues.items())),
            "examples": {
                key: values
                for key, values in sorted(issue_examples.items())
                if issue_counts[key]
            },
        },
        "acceptance": {
            "can_publish_normalization": not material_issues,
            "can_start_text_ner": not material_issues,
            "blocking_issue_codes": sorted(material_issues),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleaned", type=Path, required=True)
    parser.add_argument("--term-inventory", type=Path, required=True)
    parser.add_argument("--normalized", type=Path, required=True)
    parser.add_argument("--mappings", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    result = audit(
        args.cleaned.resolve(),
        args.term_inventory.resolve(),
        args.normalized.resolve(),
        args.mappings.resolve(),
        args.review.resolve(),
        args.manifest.resolve(),
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["acceptance"], ensure_ascii=False))
    return 0 if result["acceptance"]["can_publish_normalization"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
