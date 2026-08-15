"""Prepare full-cohort model requests and compile validated model responses."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.parquet as pq

from .aggregation_input import (
    AggregationInputError,
    load_required_source_texts,
    sha256_file as aggregation_sha256_file,
    validate_aggregation_directory,
)
from .annotation_contracts import (
    ANNOTATION_PROTOCOL_VERSION,
    ENTITY_MENTION_ARROW_SCHEMA,
    ENTITY_MENTION_SCHEMA_VERSION,
    SECTION_ANNOTATION_SCHEMA_VERSION,
    TEXT_RELATION_ARROW_SCHEMA,
    TEXT_RELATION_SCHEMA_VERSION,
)
from .annotation_validation import AnnotationValidationError, SectionAnnotationValidator
from .model_interface import (
    MODEL_ADAPTER_PROTOCOL_VERSION,
    MODEL_REQUEST_SCHEMA_VERSION,
    ModelInterfaceError,
    validate_model_request,
    validate_response_envelope,
)


FULL_EXTRACTION_PACKAGE_VERSION = "text-ner-full-extraction-package/1.0.0"
FULL_EXTRACTION_COMPILE_VERSION = "text-ner-full-extraction-compile/1.0.0"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}:{_sha256_text(payload)[:24]}"


def _json_dump(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _jsonl_dump(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ModelInterfaceError(
                    "MODEL_RESPONSE_JSON_INVALID", f"{path.name}:{line_number}: {error}"
                ) from error
            if not isinstance(value, dict):
                raise ModelInterfaceError(
                    "MODEL_RESPONSE_JSON_INVALID", f"{path.name}:{line_number}: not object"
                )
            result.append(value)
    return result


def _source_key(row: dict[str, Any]) -> tuple[int, str, str, int, str]:
    return (
        row["jsonl_line_number"],
        row["source_module"],
        row["source_table"],
        row["source_array_index"],
        row["text_field"],
    )


def _implementation_hash() -> str:
    directory = Path(__file__).resolve().parent
    paths = [
        directory / "full_extraction.py",
        directory / "aggregation_input.py",
        directory / "model_interface.py",
        directory / "annotation_validation.py",
        directory / "annotation_contracts.py",
        directory / "schemas" / "section-annotation.schema.json",
        directory / "schemas" / "model-request.schema.json",
        directory / "schemas" / "model-response.schema.json",
    ]
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda value: value.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(path.read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()


def _included_rows(manifest_path: Path) -> list[dict[str, Any]]:
    all_rows = pq.read_table(manifest_path).to_pylist()
    rows = [row for row in all_rows if row["inclusion_status"] == "included"]
    rows.sort(key=lambda row: row["manifest_row_id"])
    if not rows:
        raise ModelInterfaceError("FULL_EXTRACTION_SCOPE_EMPTY", str(manifest_path))
    if len({row["manifest_row_id"] for row in rows}) != len(rows):
        raise ModelInterfaceError("FULL_EXTRACTION_DUPLICATE_MANIFEST_ROW", str(manifest_path))
    return rows


def prepare_full_extraction_package(
    aggregation_directory: Path,
    manifest_path: Path,
    output_directory: Path,
    *,
    mention_prompt_path: Path,
    relation_prompt_path: Path,
) -> dict[str, Any]:
    """Build requests for every included manifest source without invoking a model."""

    aggregation_directory = Path(aggregation_directory).resolve()
    manifest_path = Path(manifest_path).resolve()
    output_directory = Path(output_directory).resolve()
    mention_prompt_path = Path(mention_prompt_path).resolve()
    relation_prompt_path = Path(relation_prompt_path).resolve()
    if output_directory.exists():
        raise FileExistsError(f"output directory already exists: {output_directory}")
    if not aggregation_directory.is_dir():
        raise FileNotFoundError(aggregation_directory)
    for required in (manifest_path, mention_prompt_path, relation_prompt_path):
        if not required.is_file():
            raise FileNotFoundError(required)

    rows = _included_rows(manifest_path)
    try:
        aggregation = validate_aggregation_directory(aggregation_directory)
        source_texts = load_required_source_texts(
            aggregation, (_source_key(row) for row in rows)
        )
    except AggregationInputError as error:
        raise ModelInterfaceError(error.reason_code, str(error)) from error
    prompts = {
        "mentions": mention_prompt_path.read_text(encoding="utf-8"),
        "relations": relation_prompt_path.read_text(encoding="utf-8"),
    }
    prompt_hashes = {key: _sha256_text(value) for key, value in prompts.items()}
    mention_requests: list[dict[str, Any]] = []
    relation_pending: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    for row in rows:
        try:
            source_text = source_texts[_source_key(row)]
        except KeyError as error:
            raise ModelInterfaceError(
                "FULL_EXTRACTION_SOURCE_TEXT_MISSING", row["manifest_row_id"]
            ) from error
        if _sha256_text(source_text) != row["source_text_sha256"]:
            raise ModelInterfaceError(
                "FULL_EXTRACTION_SOURCE_HASH_MISMATCH", row["manifest_row_id"]
            )
        section_text = source_text[row["span_start"] : row["span_end"]]
        if len(section_text) != row["span_character_count"]:
            raise ModelInterfaceError(
                "FULL_EXTRACTION_SECTION_LENGTH_MISMATCH", row["manifest_row_id"]
            )
        if _sha256_text(section_text) != row["span_sha256"]:
            raise ModelInterfaceError(
                "FULL_EXTRACTION_SECTION_HASH_MISMATCH", row["manifest_row_id"]
            )
        unit_id = _stable_id("xunit", row["manifest_row_id"])
        common = {
            "schema_version": MODEL_REQUEST_SCHEMA_VERSION,
            "interface_protocol_version": MODEL_ADAPTER_PROTOCOL_VERSION,
            "candidate_status": "pending_model_execution",
            "annotation_unit_id": unit_id,
            "manifest_row_id": row["manifest_row_id"],
            "document_id": row["document_id"],
            "section_id": row["section_id"],
            "source_table": row["source_table"],
            "section_name": row["section_name"],
            "section_text_sha256": row["span_sha256"],
            "response_schema_version": SECTION_ANNOTATION_SCHEMA_VERSION,
        }
        mention_requests.append(
            {
                **common,
                "request_id": _stable_id("xreq", "mentions", unit_id),
                "stage_id": "mentions",
                "prompt_sha256": prompt_hashes["mentions"],
                "section_text": section_text,
            }
        )
        relation_pending.append(
            {
                **common,
                "request_id": _stable_id("xreq", "relations", unit_id),
                "stage_id": "relations",
                "prompt_sha256": prompt_hashes["relations"],
                "dependency_status": "blocked_pending_validated_mentions",
            }
        )
        source_counts[row["source_table"]] += 1
    for request in mention_requests + relation_pending:
        validate_model_request(request)

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_directory.name}.", dir=output_directory.parent)
    )
    try:
        (temporary / "configuration" / "prompts").mkdir(parents=True)
        (temporary / "requests").mkdir()
        (temporary / "response_templates").mkdir()
        (temporary / "configuration" / "prompts" / "mentions.md").write_text(
            prompts["mentions"], encoding="utf-8", newline="\n"
        )
        (temporary / "configuration" / "prompts" / "relations.md").write_text(
            prompts["relations"], encoding="utf-8", newline="\n"
        )
        mention_path = temporary / "requests" / "mention_requests.jsonl"
        pending_path = temporary / "requests" / "relation_requests.pending.jsonl"
        _jsonl_dump(mention_path, mention_requests)
        _jsonl_dump(pending_path, relation_pending)
        mention_response_template = temporary / "response_templates" / "mention_responses.jsonl"
        relation_response_template = temporary / "response_templates" / "relation_responses.jsonl"
        _jsonl_dump(mention_response_template, [])
        _jsonl_dump(relation_response_template, [])
        summary = {
            "schema_version": FULL_EXTRACTION_PACKAGE_VERSION,
            "run_status": "prepared_no_model_calls",
            "candidate_status": "pending_model_execution",
            "included_source_tables": sorted(source_counts),
            "text_units": len(rows),
            "source_counts": dict(sorted(source_counts.items())),
            "mention_requests": len(mention_requests),
            "relation_requests_pending": len(relation_pending),
            "validated_mentions": 0,
            "validated_relations": 0,
            "model_calls": 0,
            "restricted_text": {
                "present_in_local_request_file": True,
                "git_tracking_allowed": False,
            },
        }
        summary_path = temporary / "extraction_summary.json"
        _json_dump(summary_path, summary)
        output_paths = [
            temporary / "configuration" / "prompts" / "mentions.md",
            temporary / "configuration" / "prompts" / "relations.md",
            mention_path,
            pending_path,
            mention_response_template,
            relation_response_template,
            summary_path,
        ]
        run_manifest = {
            "schema_version": FULL_EXTRACTION_PACKAGE_VERSION,
            "run_id": _stable_id(
                "xrun",
                aggregation_sha256_file(aggregation.manifest_path),
                aggregation.output_sha256["raw_source_records.parquet"],
                _sha256_file(manifest_path),
                prompt_hashes["mentions"],
                prompt_hashes["relations"],
                _implementation_hash(),
            ),
            "run_status": "prepared_no_model_calls",
            "input": {
                "aggregation_manifest_sha256": aggregation_sha256_file(
                    aggregation.manifest_path
                ),
                "raw_source_records_sha256": aggregation.output_sha256[
                    "raw_source_records.parquet"
                ],
                "input_manifest_sha256": _sha256_file(manifest_path),
                "text_units": len(rows),
                "source_counts": dict(sorted(source_counts.items())),
            },
            "interface": {
                "adapter_protocol_version": MODEL_ADAPTER_PROTOCOL_VERSION,
                "request_schema_version": MODEL_REQUEST_SCHEMA_VERSION,
                "response_schema_version": "text-ner-model-response/1.0.0",
                "annotation_schema_version": SECTION_ANNOTATION_SCHEMA_VERSION,
                "provider": None,
                "model_name": None,
                "model_version": None,
            },
            "execution": {"mode": "request_only", "model_calls": 0},
            "reproducibility": {
                "implementation_sha256": _implementation_hash(),
                "prompt_sha256": prompt_hashes,
                "request_order": "manifest_row_id",
            },
            "outputs": {
                path.relative_to(temporary).as_posix(): _sha256_file(path)
                for path in output_paths
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


def _request_maps(package_directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    mention_rows = _load_jsonl(package_directory / "requests" / "mention_requests.jsonl")
    relation_rows = _load_jsonl(
        package_directory / "requests" / "relation_requests.pending.jsonl"
    )
    for request in mention_rows + relation_rows:
        validate_model_request(request)
    mentions = {row["request_id"]: row for row in mention_rows}
    relations = {row["request_id"]: row for row in relation_rows}
    if len(mentions) != len(mention_rows) or len(relations) != len(relation_rows):
        raise ModelInterfaceError("MODEL_REQUEST_DUPLICATE", str(package_directory))
    return mentions, relations


def _validate_annotation(
    response: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    envelope = validate_response_envelope(response, request)
    annotation = envelope["annotation"]
    SectionAnnotationValidator().validate(
        annotation,
        {
            "manifest_row_id": request["manifest_row_id"],
            "document_id": request["document_id"],
            "section_id": request["section_id"],
            "span_sha256": request["section_text_sha256"],
        },
        request["section_text"],
    )
    return envelope


def _row_maps(manifest_path: Path) -> dict[str, dict[str, Any]]:
    return {row["manifest_row_id"]: row for row in _included_rows(manifest_path)}


def _mention_rows(
    responses: list[dict[str, Any]], requests: dict[str, dict[str, Any]], rows: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    output: list[dict[str, Any]] = []
    validated: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for response in responses:
        request_id = response.get("request_id")
        if request_id in seen:
            raise ModelInterfaceError("MODEL_RESPONSE_DUPLICATE", str(request_id))
        seen.add(request_id)
        request = requests.get(str(request_id))
        if request is None:
            raise ModelInterfaceError("MODEL_RESPONSE_REQUEST_UNKNOWN", str(request_id))
        envelope = _validate_annotation(response, request)
        annotation = envelope["annotation"]
        if annotation["relations"]:
            raise ModelInterfaceError("MENTION_RESPONSE_CONTAINS_RELATIONS", str(request_id))
        validated[request["annotation_unit_id"]] = envelope
        manifest = rows[request["manifest_row_id"]]
        for mention in annotation["mentions"]:
            mention_id = _stable_id(
                "mention", request["manifest_row_id"], mention["local_id"], request["section_text_sha256"]
            )
            output.append(
                {
                    "schema_version": ENTITY_MENTION_SCHEMA_VERSION,
                    "mention_id": mention_id,
                    "manifest_row_id": manifest["manifest_row_id"],
                    "document_id": manifest["document_id"],
                    "section_id": manifest["section_id"],
                    "subject_id": manifest["subject_id"],
                    "hadm_id": manifest["hadm_id"],
                    "source_row_id": manifest["source_row_id"],
                    "raw_row_ref": manifest["raw_row_ref"],
                    "source_table": manifest["source_table"],
                    "section_name": manifest["section_name"],
                    "surface_text": mention["surface_text"],
                    "section_span_start": mention["section_span_start"],
                    "section_span_end": mention["section_span_end"],
                    "document_span_start": manifest["span_start"] + mention["section_span_start"],
                    "document_span_end": manifest["span_start"] + mention["section_span_end"],
                    "entity_type": mention["entity_type"],
                    "assertion": mention["assertion"],
                    "temporality": mention["temporality"],
                    "experiencer": mention["experiencer"],
                    "laterality": mention["laterality"],
                    "severity": mention["severity"],
                    "trend": mention["trend"],
                    "normalization_status": mention["normalization_status"],
                    "concept_id": mention["concept_id"],
                    "preferred_name": mention["preferred_name"],
                    "terminology": mention["terminology"],
                    "event_time": manifest["event_time"],
                    "available_time": manifest["available_time"],
                    "evidence_phase": manifest["evidence_phase"],
                    "extraction_method": "model_interface",
                    "extractor_name": envelope["provider"] + "/" + envelope["model_name"],
                    "extractor_version": envelope["model_version"],
                    "input_sha256": request["section_text_sha256"],
                    "prompt_sha256": request["prompt_sha256"],
                    "review_status": "unreviewed_model_output",
                    "quality_flags": mention["quality_flags"],
                }
            )
    output.sort(key=lambda row: row["mention_id"])
    return output, validated


def _relation_request(
    pending: dict[str, Any], mention_request: dict[str, Any], mention_response: dict[str, Any]
) -> dict[str, Any]:
    request = {
        **pending,
        "dependency_status": "validated_mentions_available",
        "section_text": mention_request["section_text"],
        "validated_mentions": mention_response["annotation"]["mentions"],
    }
    return validate_model_request(request)


def compile_model_responses(
    package_directory: Path,
    manifest_path: Path,
    mention_responses_path: Path,
    relation_responses_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Validate supplied responses and compile typed entity/relation sidecars.

    Empty response files are valid and produce a pending, zero-row compilation.
    This function never owns or invokes a model adapter.
    """

    package_directory = Path(package_directory).resolve()
    manifest_path = Path(manifest_path).resolve()
    mention_responses_path = Path(mention_responses_path).resolve()
    relation_responses_path = Path(relation_responses_path).resolve()
    output_directory = Path(output_directory).resolve()
    if output_directory.exists():
        raise FileExistsError(f"output directory already exists: {output_directory}")
    run_manifest = json.loads((package_directory / "run_manifest.json").read_text(encoding="utf-8"))
    if _sha256_file(manifest_path) != run_manifest["input"]["input_manifest_sha256"]:
        raise ModelInterfaceError("COMPILE_MANIFEST_HASH_MISMATCH", str(manifest_path))
    mention_requests, relation_pending = _request_maps(package_directory)
    manifest_rows = _row_maps(manifest_path)
    mention_responses = _load_jsonl(mention_responses_path)
    relation_responses = _load_jsonl(relation_responses_path)
    entity_rows, validated_mentions = _mention_rows(
        mention_responses, mention_requests, manifest_rows
    )

    pending_by_unit = {row["annotation_unit_id"]: row for row in relation_pending.values()}
    mention_request_by_unit = {row["annotation_unit_id"]: row for row in mention_requests.values()}
    ready_relation_requests = {
        pending_by_unit[unit_id]["request_id"]: _relation_request(
            pending_by_unit[unit_id], mention_request_by_unit[unit_id], response
        )
        for unit_id, response in validated_mentions.items()
    }
    relation_rows: list[dict[str, Any]] = []
    completed_annotations: list[dict[str, Any]] = []
    seen_relation: set[str] = set()
    local_to_global = {
        (response["annotation"]["manifest_row_id"], mention["local_id"]): _stable_id(
            "mention",
            response["annotation"]["manifest_row_id"],
            mention["local_id"],
            response["annotation"]["section_text_sha256"],
        )
        for response in validated_mentions.values()
        for mention in response["annotation"]["mentions"]
    }
    for response in relation_responses:
        request_id = response.get("request_id")
        if request_id in seen_relation:
            raise ModelInterfaceError("MODEL_RESPONSE_DUPLICATE", str(request_id))
        seen_relation.add(request_id)
        request = ready_relation_requests.get(str(request_id))
        if request is None:
            if str(request_id) in relation_pending:
                raise ModelInterfaceError("RELATION_RESPONSE_BEFORE_VALIDATED_MENTIONS", str(request_id))
            raise ModelInterfaceError("MODEL_RESPONSE_REQUEST_UNKNOWN", str(request_id))
        envelope = _validate_annotation(response, request)
        annotation = envelope["annotation"]
        if annotation["mentions"] != request["validated_mentions"]:
            raise ModelInterfaceError("RELATION_RESPONSE_MENTIONS_CHANGED", str(request_id))
        completed_annotations.append(annotation)
        manifest = manifest_rows[request["manifest_row_id"]]
        for relation in annotation["relations"]:
            relation_rows.append(
                {
                    "schema_version": TEXT_RELATION_SCHEMA_VERSION,
                    "relation_id": _stable_id(
                        "relation", request["manifest_row_id"], relation["local_id"], request["section_text_sha256"]
                    ),
                    "manifest_row_id": manifest["manifest_row_id"],
                    "document_id": manifest["document_id"],
                    "section_id": manifest["section_id"],
                    "subject_id": manifest["subject_id"],
                    "hadm_id": manifest["hadm_id"],
                    "source_mention_id": local_to_global[(manifest["manifest_row_id"], relation["source_mention_id"])],
                    "target_mention_id": local_to_global[(manifest["manifest_row_id"], relation["target_mention_id"])],
                    "relation_type": relation["relation_type"],
                    "evidence_text": relation["evidence_text"],
                    "section_evidence_start": relation["section_evidence_start"],
                    "section_evidence_end": relation["section_evidence_end"],
                    "document_evidence_start": manifest["span_start"] + relation["section_evidence_start"],
                    "document_evidence_end": manifest["span_start"] + relation["section_evidence_end"],
                    "relation_basis": relation["relation_basis"],
                    "extraction_method": "model_interface",
                    "extractor_name": envelope["provider"] + "/" + envelope["model_name"],
                    "extractor_version": envelope["model_version"],
                    "input_sha256": request["section_text_sha256"],
                    "prompt_sha256": request["prompt_sha256"],
                    "review_status": "unreviewed_model_output",
                    "quality_flags": relation["quality_flags"],
                }
            )
    relation_rows.sort(key=lambda row: row["relation_id"])
    completed_annotations.sort(key=lambda row: row["manifest_row_id"])

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_directory.name}.", dir=output_directory.parent)
    )
    try:
        (temporary / "sidecars").mkdir()
        (temporary / "requests").mkdir()
        (temporary / "candidates").mkdir()
        entity_path = temporary / "sidecars" / "entity_mentions.parquet"
        relation_path = temporary / "sidecars" / "text_relations.parquet"
        pq.write_table(pa.Table.from_pylist(entity_rows, schema=ENTITY_MENTION_ARROW_SCHEMA), entity_path)
        pq.write_table(pa.Table.from_pylist(relation_rows, schema=TEXT_RELATION_ARROW_SCHEMA), relation_path)
        ready_path = temporary / "requests" / "relation_requests.ready.jsonl"
        _jsonl_dump(ready_path, sorted(ready_relation_requests.values(), key=lambda row: row["request_id"]))
        candidates_path = temporary / "candidates" / "section_annotations.jsonl"
        _jsonl_dump(candidates_path, completed_annotations)
        total_units = run_manifest["input"]["text_units"]
        summary = {
            "schema_version": FULL_EXTRACTION_COMPILE_VERSION,
            "compile_status": (
                "complete_unreviewed_model_output"
                if len(completed_annotations) == total_units
                else "pending_model_execution"
            ),
            "text_units": total_units,
            "mention_responses_validated": len(validated_mentions),
            "relation_requests_ready": len(ready_relation_requests),
            "relation_responses_validated": len(completed_annotations),
            "entity_mentions": len(entity_rows),
            "text_relations": len(relation_rows),
            "model_calls_performed_by_compiler": 0,
            "review_status": "unreviewed_model_output" if entity_rows or relation_rows else "not_applicable",
        }
        summary_path = temporary / "compile_summary.json"
        _json_dump(summary_path, summary)
        compile_manifest = {
            **summary,
            "source_package_run_id": run_manifest["run_id"],
            "inputs": {
                "package_manifest_sha256": _sha256_file(package_directory / "run_manifest.json"),
                "manifest_sha256": _sha256_file(manifest_path),
                "mention_responses_sha256": _sha256_file(mention_responses_path),
                "relation_responses_sha256": _sha256_file(relation_responses_path),
            },
            "outputs": {
                path.relative_to(temporary).as_posix(): _sha256_file(path)
                for path in (entity_path, relation_path, ready_path, candidates_path, summary_path)
            },
        }
        _json_dump(temporary / "compile_manifest.json", compile_manifest)
        temporary.replace(output_directory)
        return compile_manifest
    except Exception:
        resolved = temporary.resolve()
        if output_directory.parent.resolve() in resolved.parents:
            shutil.rmtree(resolved, ignore_errors=True)
        raise
