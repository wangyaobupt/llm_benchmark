"""Build an all-free-text NER manifest from an accepted event aggregation."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.event_pipeline.event_cleaning.ids import build_source_row_id
from data_pipeline.event_pipeline.event_cleaning.source_catalog import SOURCE_BY_PATH
from data_pipeline.event_pipeline.event_cleaning.time_resolver import resolved_times

from .aggregation_input import (
    AggregationInputError,
    ValidatedAggregation,
    aggregation_text_fields,
    iter_source_text_records,
    sha256_file,
    validate_aggregation_directory,
)
from .contracts import MANIFEST_ARROW_SCHEMA, MANIFEST_SCHEMA_VERSION
from .sections import TextSection, split_radiology_sections


AGGREGATION_TEXT_MANIFEST_VERSION = "aggregation-text-ner-input/1.0.0"
TEXT_EVENT_LINK_SCHEMA_VERSION = "text-ner-event-link/1.0.0"
TEXT_EVENT_LINK_ARROW_SCHEMA = pa.schema(
    [
        ("schema_version", pa.string()),
        ("manifest_row_id", pa.string()),
        ("event_id", pa.string()),
        ("normalization_status", pa.string()),
        ("concept_id", pa.string()),
        ("preferred_name", pa.string()),
        ("source_table", pa.string()),
    ],
    metadata={b"schema": TEXT_EVENT_LINK_SCHEMA_VERSION.encode("ascii")},
)


class AggregationTextManifestError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _implementation_hash() -> str:
    module_directory = Path(__file__).resolve().parent
    paths = [
        module_directory / "aggregation_manifest.py",
        module_directory / "aggregation_input.py",
        module_directory / "contracts.py",
        module_directory / "sections.py",
        Path(__file__).resolve().parents[1]
        / "event_pipeline"
        / "event_cleaning"
        / "source_catalog.py",
        Path(__file__).resolve().parents[1]
        / "event_pipeline"
        / "event_cleaning"
        / "time_resolver.py",
    ]
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(b"\x00")
        digest.update(path.read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}:{_sha256_text(payload)[:24]}"


def _json_dump(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _clean(value: Any) -> str | None:
    if value in (None, ""):
        return None
    result = str(value).strip()
    return result or None


def _bounded_spans(text: str, maximum: int) -> list[tuple[int, int]]:
    if maximum <= 0:
        raise AggregationTextManifestError("TEXT_CHUNK_SIZE_INVALID", str(maximum))
    spans: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + maximum)
        if end < len(text):
            minimum = start + maximum // 2
            candidates = (
                text.rfind("\n\n", minimum, end),
                text.rfind("\n", minimum, end),
                text.rfind(". ", minimum, end),
                text.rfind(" ", minimum, end),
            )
            boundary = max(candidates)
            if boundary >= minimum:
                end = boundary + (2 if text[boundary : boundary + 2] in {"\n\n", ". "} else 1)
        if end <= start:
            raise AggregationTextManifestError("TEXT_CHUNK_NO_PROGRESS", str(start))
        if text[start:end].strip():
            spans.append((start, end))
        start = end
    return spans


def _sections(text: str, strategy: str, maximum: int) -> list[TextSection]:
    bases = (
        split_radiology_sections(text)
        if strategy == "radiology_sections"
        else [TextSection("text", 0, 0, len(text))]
    )
    result: list[TextSection] = []
    for base in bases:
        for start, end in _bounded_spans(text[base.start : base.end], maximum):
            absolute_start = base.start + start
            absolute_end = base.start + end
            result.append(
                TextSection(base.name, len(result), absolute_start, absolute_end)
            )
    return result


def _load_catalog(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "text-ner-source-catalog/1.0.0":
        raise AggregationTextManifestError(
            "TEXT_SOURCE_CATALOG_VERSION_INVALID", str(value.get("schema_version"))
        )
    if not isinstance(value.get("sources"), list) or not value["sources"]:
        raise AggregationTextManifestError("TEXT_SOURCE_CATALOG_EMPTY", str(path))
    keys: set[tuple[str, str, str]] = set()
    for source in value["sources"]:
        required = {
            "source_module",
            "source_table",
            "text_field",
            "text_kind",
            "section_strategy",
            "event_time_field",
            "available_time_field",
            "recorded_time_field",
            "evidence_phase",
        }
        missing = required - set(source)
        if missing:
            raise AggregationTextManifestError(
                "TEXT_SOURCE_CATALOG_FIELD_MISSING", ",".join(sorted(missing))
            )
        table = source["source_table"].split(".", 1)[-1]
        path_key = (source["source_module"], table)
        if path_key not in SOURCE_BY_PATH:
            raise AggregationTextManifestError(
                "TEXT_SOURCE_NOT_IN_EVENT_CATALOG", ".".join(path_key)
            )
        key = (*path_key, source["text_field"])
        if key in keys:
            raise AggregationTextManifestError("TEXT_SOURCE_DUPLICATE", ".".join(key))
        keys.add(key)
    return value


def _manifest_rows(
    aggregation: ValidatedAggregation, catalog: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, list[str]]]:
    rules: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for rule in catalog["sources"]:
        key = (
            rule["source_module"],
            rule["source_table"],
            rule["text_field"],
            rule["text_kind"],
        )
        rules[key] = rule
    declared = aggregation_text_fields(aggregation)
    if set(rules) != declared:
        missing = sorted(set(rules) - declared)
        extra = sorted(declared - set(rules))
        raise AggregationTextManifestError(
            "TEXT_SOURCE_CATALOG_AGGREGATION_MISMATCH",
            f"missing={missing}; extra={extra}",
        )
    maximum = int(catalog["max_chunk_characters"])
    result: list[dict[str, Any]] = []
    manifest_ids_by_source_record: dict[str, list[str]] = defaultdict(list)
    documents = 0
    source_document_counts: Counter[str] = Counter()
    source_unit_counts: Counter[str] = Counter()
    source_character_counts: Counter[str] = Counter()
    for source in iter_source_text_records(aggregation):
        key = (
            source["source_module"],
            source["source_table"],
            source["source_text_field"],
            source["source_text_kind"],
        )
        rule = rules[key]
        module = source["source_module"]
        table = source["source_table_name"]
        try:
            row = json.loads(source["clinical_readable_record_json"])
        except json.JSONDecodeError as error:
            raise AggregationTextManifestError(
                "AGGREGATION_CLINICAL_RECORD_INVALID", source["source_record_id"]
            ) from error
        if not isinstance(row, dict) or str(row.get(rule["text_field"]) or "") != source["source_text"]:
            raise AggregationTextManifestError(
                "AGGREGATION_CLINICAL_TEXT_MISMATCH", source["source_record_id"]
            )
        text = source["source_text"]
        spec = SOURCE_BY_PATH[(module, table)]
        source_row_id = build_source_row_id(spec, row)
        document_id = _stable_id("doc", source_row_id, rule["text_field"])
        event_field = rule["event_time_field"]
        available_field = rule["available_time_field"]
        recorded_field = rule["recorded_time_field"]
        times = resolved_times(
            event_time=row.get(event_field) if event_field else None,
            available_time=row.get(available_field) if available_field else None,
            recorded_time=row.get(recorded_field) if recorded_field else None,
        )
        sections = _sections(text, rule["section_strategy"], maximum)
        if not sections:
            continue
        documents += 1
        source_document_counts[rule["source_table"]] += 1
        source_character_counts[rule["source_table"]] += len(text)
        note_id = _clean(row.get("note_id"))
        note_type = _clean(row.get("note_type")) or rule["text_kind"]
        for section in sections:
            section_id = _stable_id(
                "sec", document_id, section.ordinal, section.name, section.start, section.end
            )
            manifest_row_id = _stable_id("mrow", document_id, section_id)
            span = text[section.start : section.end]
            result.append(
                {
                    "schema_version": MANIFEST_SCHEMA_VERSION,
                    "manifest_row_id": manifest_row_id,
                    "document_id": document_id,
                    "section_id": section_id,
                    "subject_id": str(source["subject_id"]),
                    "hadm_id": str(source["hadm_id"]),
                    "split_group_id": str(source["subject_id"]),
                    "source_module": module,
                    "source_table": rule["source_table"],
                    "source_row_id": source_row_id,
                    "source_array_index": source["source_array_index"],
                    "jsonl_line_number": source["jsonl_line_number"],
                    "raw_row_ref": source["raw_row_ref"],
                    "text_field": rule["text_field"],
                    "note_id": note_id,
                    "note_type": note_type,
                    "parent_note_id": None,
                    "addendum_note_ids": [],
                    "event_time": times["event_time"],
                    "source_available_time": times["source_available_time"],
                    "available_time": times["available_time"],
                    "recorded_time": times["recorded_time"],
                    "time_resolution_status": times["time_resolution_status"],
                    "time_policy_id": spec.time_policy,
                    "time_resolution_reasons": list(times["time_resolution_reasons"]),
                    "evidence_phase": rule["evidence_phase"],
                    "quality_flags": list(times["time_quality_flags"]),
                    "section_name": section.name if section.name != "text" else rule["text_kind"],
                    "section_ordinal": section.ordinal,
                    "span_start": section.start,
                    "span_end": section.end,
                    "source_text_character_count": len(text),
                    "span_character_count": len(span),
                    "source_text_sha256": source["source_text_sha256"],
                    "span_sha256": _sha256_text(span),
                    "inclusion_status": "included",
                    "reason_code": "NER_ELIGIBLE_FREE_TEXT",
                    "pilot_document_selected": False,
                    "pilot_selection_rank": None,
                    "pilot_stratum": f"{rule['source_table']}:{rule['text_kind']}",
                }
            )
            manifest_ids_by_source_record[source["source_record_id"]].append(manifest_row_id)
            source_unit_counts[rule["source_table"]] += 1
    result.sort(key=lambda row: row["manifest_row_id"])
    summary = {
        "schema_version": AGGREGATION_TEXT_MANIFEST_VERSION,
        "admissions": int(aggregation.quality["expected"]["admissions"]),
        "documents": documents,
        "text_units": len(result),
        "source_document_counts": dict(sorted(source_document_counts.items())),
        "source_unit_counts": dict(sorted(source_unit_counts.items())),
        "source_character_counts": dict(sorted(source_character_counts.items())),
        "post_hoc_included": True,
        "model_calls": 0,
    }
    observed = aggregation.quality.get("observed", {})
    if summary["source_document_counts"] != observed.get("source_text_record_counts"):
        raise AggregationTextManifestError(
            "AGGREGATION_TEXT_RECORD_COUNTS_MISMATCH",
            repr(observed.get("source_text_record_counts")),
        )
    if summary["source_character_counts"] != observed.get("source_text_character_counts"):
        raise AggregationTextManifestError(
            "AGGREGATION_TEXT_CHARACTER_COUNTS_MISMATCH",
            repr(observed.get("source_text_character_counts")),
        )
    return result, summary, manifest_ids_by_source_record


def _event_links(
    aggregation: ValidatedAggregation,
    manifest_rows: list[dict[str, Any]],
    manifest_ids_by_source_record: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], int]:
    links: list[dict[str, Any]] = []
    linked_manifest_ids: set[str] = set()
    columns = [
        "event_id",
        "normalization_status",
        "concept_id",
        "preferred_name",
        "source_table",
        "source_record_id",
    ]
    parquet = pq.ParquetFile(aggregation.processed_events_path)
    for batch in parquet.iter_batches(columns=columns, batch_size=10000):
        values = batch.to_pydict()
        for index in range(batch.num_rows):
            source_record_id = values["source_record_id"][index]
            for manifest_row_id in manifest_ids_by_source_record.get(source_record_id, []):
                links.append(
                    {
                        "schema_version": TEXT_EVENT_LINK_SCHEMA_VERSION,
                        "manifest_row_id": manifest_row_id,
                        "event_id": values["event_id"][index],
                        "normalization_status": values["normalization_status"][index],
                        "concept_id": values["concept_id"][index],
                        "preferred_name": values["preferred_name"][index],
                        "source_table": values["source_table"][index],
                    }
                )
                linked_manifest_ids.add(manifest_row_id)
    links.sort(key=lambda row: (row["manifest_row_id"], row["event_id"]))
    return links, len(set(row["manifest_row_id"] for row in manifest_rows) - linked_manifest_ids)


def prepare_aggregation_text_manifest(
    aggregation_directory: Path,
    source_catalog_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Create a deterministic text manifest without invoking any model."""

    aggregation_directory = Path(aggregation_directory).resolve()
    source_catalog_path = Path(source_catalog_path).resolve()
    output_directory = Path(output_directory).resolve()
    if output_directory.exists():
        raise FileExistsError(f"output directory already exists: {output_directory}")
    try:
        aggregation = validate_aggregation_directory(aggregation_directory)
    except AggregationInputError as error:
        raise AggregationTextManifestError(error.reason_code, str(error)) from error
    catalog = _load_catalog(source_catalog_path)
    rows, summary, ids_by_source_record = _manifest_rows(aggregation, catalog)
    links, unlinked = _event_links(aggregation, rows, ids_by_source_record)
    summary["event_links"] = len(links)
    summary["text_units_without_direct_event_link"] = unlinked

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_directory.name}.", dir=output_directory.parent)
    )
    try:
        manifest_path = temporary / "text_ner_input_manifest.parquet"
        link_path = temporary / "text_unit_event_links.parquet"
        summary_path = temporary / "text_ner_input_manifest_summary.json"
        pq.write_table(
            pa.Table.from_pylist(rows, schema=MANIFEST_ARROW_SCHEMA),
            manifest_path,
            compression="zstd",
            row_group_size=5000,
        )
        pq.write_table(
            pa.Table.from_pylist(links, schema=TEXT_EVENT_LINK_ARROW_SCHEMA),
            link_path,
            compression="zstd",
            row_group_size=5000,
        )
        _json_dump(summary_path, summary)
        run_manifest = {
            "schema_version": AGGREGATION_TEXT_MANIFEST_VERSION,
            "run_id": _stable_id(
                "atrun",
                sha256_file(aggregation.manifest_path),
                aggregation.output_sha256["raw_source_records.parquet"],
                aggregation.output_sha256["processed_events.parquet"],
                sha256_file(source_catalog_path),
                _implementation_hash(),
            ),
            "status": "prepared_no_model_calls",
            "aggregation": {
                "schema_version": aggregation.manifest["aggregation_schema_version"],
                "aggregation_manifest_sha256": sha256_file(aggregation.manifest_path),
                "quality_report_sha256": sha256_file(aggregation.quality_path),
                "raw_source_records_sha256": aggregation.output_sha256[
                    "raw_source_records.parquet"
                ],
                "processed_events_sha256": aggregation.output_sha256[
                    "processed_events.parquet"
                ],
                "traceable_events_sha256": aggregation.output_sha256[
                    "traceable_events.parquet"
                ],
                "events": int(aggregation.quality["expected"]["events"]),
                "admissions": int(aggregation.quality["expected"]["admissions"]),
            },
            "source_catalog_sha256": sha256_file(source_catalog_path),
            "counts": summary,
            "execution": {"model_calls": 0},
            "reproducibility": {"implementation_sha256": _implementation_hash()},
            "outputs": {
                manifest_path.name: sha256_file(manifest_path),
                link_path.name: sha256_file(link_path),
                summary_path.name: sha256_file(summary_path),
            },
        }
        _json_dump(temporary / "run_manifest.json", run_manifest)
        temporary.replace(output_directory)
        return run_manifest
    except Exception:
        resolved = temporary.resolve()
        if output_directory.parent.resolve() in resolved.parents:
            shutil.rmtree(resolved, ignore_errors=True)
        raise
