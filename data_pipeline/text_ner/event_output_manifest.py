"""Build an all-free-text NER manifest anchored to an accepted event output."""

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

from .contracts import MANIFEST_ARROW_SCHEMA, MANIFEST_SCHEMA_VERSION
from .sections import TextSection, split_radiology_sections


EVENT_OUTPUT_TEXT_MANIFEST_VERSION = "event-output-text-ner-input/1.0.0"
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


class EventOutputTextManifestError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _implementation_hash() -> str:
    module_directory = Path(__file__).resolve().parent
    paths = [
        module_directory / "event_output_manifest.py",
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
        raise EventOutputTextManifestError("TEXT_CHUNK_SIZE_INVALID", str(maximum))
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
            raise EventOutputTextManifestError("TEXT_CHUNK_NO_PROGRESS", str(start))
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
        raise EventOutputTextManifestError(
            "TEXT_SOURCE_CATALOG_VERSION_INVALID", str(value.get("schema_version"))
        )
    if not isinstance(value.get("sources"), list) or not value["sources"]:
        raise EventOutputTextManifestError("TEXT_SOURCE_CATALOG_EMPTY", str(path))
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
            raise EventOutputTextManifestError(
                "TEXT_SOURCE_CATALOG_FIELD_MISSING", ",".join(sorted(missing))
            )
        table = source["source_table"].split(".", 1)[-1]
        path_key = (source["source_module"], table)
        if path_key not in SOURCE_BY_PATH:
            raise EventOutputTextManifestError(
                "TEXT_SOURCE_NOT_IN_EVENT_CATALOG", ".".join(path_key)
            )
        key = (*path_key, source["text_field"])
        if key in keys:
            raise EventOutputTextManifestError("TEXT_SOURCE_DUPLICATE", ".".join(key))
        keys.add(key)
    return value


def _resolve_inputs(event_output: Path) -> tuple[Path, Path, dict[str, Any]]:
    workflow_path = event_output / "workflow_manifest.json"
    normalized_path = event_output / "normalization" / "normalized_events.parquet"
    if not workflow_path.is_file() or not normalized_path.is_file():
        raise EventOutputTextManifestError("EVENT_OUTPUT_INCOMPLETE", str(event_output))
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    if not workflow.get("acceptance", {}).get("can_start_text_ner"):
        raise EventOutputTextManifestError("EVENT_OUTPUT_NOT_ACCEPTED_FOR_NER", str(event_output))
    source_name = workflow.get("inputs", {}).get("source_jsonl")
    if not source_name:
        raise EventOutputTextManifestError("EVENT_OUTPUT_SOURCE_JSONL_MISSING", str(workflow_path))
    source_path = (event_output.parent / source_name).resolve()
    if not source_path.is_file():
        raise EventOutputTextManifestError("EVENT_OUTPUT_SOURCE_JSONL_NOT_FOUND", str(source_path))
    if _sha256_file(source_path) != workflow["inputs"]["source_jsonl_sha256"]:
        raise EventOutputTextManifestError("EVENT_OUTPUT_SOURCE_JSONL_HASH_MISMATCH", str(source_path))
    return source_path, normalized_path, workflow


def _manifest_rows(
    source_path: Path, catalog: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rules: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for rule in catalog["sources"]:
        rules[(rule["source_module"], rule["source_table"].split(".", 1)[1])].append(rule)
    maximum = int(catalog["max_chunk_characters"])
    result: list[dict[str, Any]] = []
    documents = 0
    admissions = 0
    source_document_counts: Counter[str] = Counter()
    source_unit_counts: Counter[str] = Counter()
    source_character_counts: Counter[str] = Counter()
    with source_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            admission = json.loads(line)
            admissions += 1
            subject_id = str(admission["subject_id"])
            hadm_id = str(admission["hadm_id"])
            for (module, table), table_rules in rules.items():
                for index, row in enumerate(admission.get(module, {}).get(table, [])):
                    for rule in table_rules:
                        text = str(row.get(rule["text_field"]) or "")
                        if not text.strip():
                            continue
                        spec = SOURCE_BY_PATH[(module, table)]
                        source_row_id = build_source_row_id(spec, row)
                        document_id = _stable_id(
                            "doc", source_row_id, rule["text_field"]
                        )
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
                                "sec",
                                document_id,
                                section.ordinal,
                                section.name,
                                section.start,
                                section.end,
                            )
                            manifest_row_id = _stable_id("mrow", document_id, section_id)
                            span = text[section.start : section.end]
                            quality_flags = list(times["time_quality_flags"])
                            result.append(
                                {
                                    "schema_version": MANIFEST_SCHEMA_VERSION,
                                    "manifest_row_id": manifest_row_id,
                                    "document_id": document_id,
                                    "section_id": section_id,
                                    "subject_id": subject_id,
                                    "hadm_id": hadm_id,
                                    "split_group_id": subject_id,
                                    "source_module": module,
                                    "source_table": rule["source_table"],
                                    "source_row_id": source_row_id,
                                    "source_array_index": index,
                                    "jsonl_line_number": line_number,
                                    "raw_row_ref": f"{source_path.name}#L{line_number}/{module}.{table}[{index}]",
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
                                    "quality_flags": quality_flags,
                                    "section_name": section.name if section.name != "text" else rule["text_kind"],
                                    "section_ordinal": section.ordinal,
                                    "span_start": section.start,
                                    "span_end": section.end,
                                    "source_text_character_count": len(text),
                                    "span_character_count": len(span),
                                    "source_text_sha256": _sha256_text(text),
                                    "span_sha256": _sha256_text(span),
                                    "inclusion_status": "included",
                                    "reason_code": "NER_ELIGIBLE_FREE_TEXT",
                                    "pilot_document_selected": False,
                                    "pilot_selection_rank": None,
                                    "pilot_stratum": f"{rule['source_table']}:{rule['text_kind']}",
                                }
                            )
                            source_unit_counts[rule["source_table"]] += 1
    result.sort(key=lambda row: row["manifest_row_id"])
    summary = {
        "schema_version": EVENT_OUTPUT_TEXT_MANIFEST_VERSION,
        "admissions": admissions,
        "documents": documents,
        "text_units": len(result),
        "source_document_counts": dict(sorted(source_document_counts.items())),
        "source_unit_counts": dict(sorted(source_unit_counts.items())),
        "source_character_counts": dict(sorted(source_character_counts.items())),
        "post_hoc_included": True,
        "model_calls": 0,
    }
    return result, summary


def _event_links(
    normalized_path: Path, manifest_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    ids_by_key: dict[tuple[int, str, str, int], list[str]] = defaultdict(list)
    for row in manifest_rows:
        key = (
            row["jsonl_line_number"],
            row["source_module"],
            row["source_table"],
            row["source_array_index"],
        )
        ids_by_key[key].append(row["manifest_row_id"])
    links: list[dict[str, Any]] = []
    linked_manifest_ids: set[str] = set()
    columns = [
        "event_id",
        "normalization_status",
        "concept_id",
        "preferred_name",
        "source_module",
        "source_table",
        "source_array_index",
        "jsonl_line_number",
    ]
    parquet = pq.ParquetFile(normalized_path)
    for batch in parquet.iter_batches(columns=columns, batch_size=10000):
        values = batch.to_pydict()
        for index in range(batch.num_rows):
            key = (
                values["jsonl_line_number"][index],
                values["source_module"][index],
                values["source_table"][index],
                values["source_array_index"][index],
            )
            for manifest_row_id in ids_by_key.get(key, []):
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


def prepare_event_output_text_manifest(
    event_output_directory: Path,
    source_catalog_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Create a deterministic text manifest without invoking any model."""

    event_output_directory = Path(event_output_directory).resolve()
    source_catalog_path = Path(source_catalog_path).resolve()
    output_directory = Path(output_directory).resolve()
    if output_directory.exists():
        raise FileExistsError(f"output directory already exists: {output_directory}")
    source_path, normalized_path, workflow = _resolve_inputs(event_output_directory)
    catalog = _load_catalog(source_catalog_path)
    rows, summary = _manifest_rows(source_path, catalog)
    if summary["admissions"] != workflow["stages"]["cleaning"]["counts"]["admissions"]:
        raise EventOutputTextManifestError(
            "EVENT_OUTPUT_ADMISSION_COUNT_MISMATCH", str(summary["admissions"])
        )
    links, unlinked = _event_links(normalized_path, rows)
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
            "schema_version": EVENT_OUTPUT_TEXT_MANIFEST_VERSION,
            "run_id": _stable_id(
                "etrun",
                workflow["run_id"],
                _sha256_file(source_path),
                _sha256_file(normalized_path),
                _sha256_file(source_catalog_path),
                _implementation_hash(),
            ),
            "status": "prepared_no_model_calls",
            "event_output": {
                "workflow_run_id": workflow["run_id"],
                "workflow_manifest_sha256": _sha256_file(event_output_directory / "workflow_manifest.json"),
                "normalized_events_sha256": _sha256_file(normalized_path),
                "normalized_events": workflow["stages"]["normalization"]["counts"]["events"],
            },
            "source": {
                "filename": source_path.name,
                "sha256": _sha256_file(source_path),
                "catalog_sha256": _sha256_file(source_catalog_path),
            },
            "counts": summary,
            "execution": {"model_calls": 0},
            "reproducibility": {"implementation_sha256": _implementation_hash()},
            "outputs": {
                manifest_path.name: _sha256_file(manifest_path),
                link_path.name: _sha256_file(link_path),
                summary_path.name: _sha256_file(summary_path),
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
