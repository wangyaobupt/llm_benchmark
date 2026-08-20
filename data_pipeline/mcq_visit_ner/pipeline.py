"""Resumable visit NER. Default is dry-run; API calls are fail-closed."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from data_pipeline.mcq_visit_extract.atomic import (
    atomic_write_json,
    atomic_write_jsonl,
    canonical_hash,
    file_sha256,
    read_jsonl,
    read_manifest,
    write_manifest,
)
from data_pipeline.mcq_visit_standardize.io import iter_json_array

from . import PIPELINE_VERSION
from .client import (
    ApiSettings,
    NerError,
    Transport,
    call_with_retry,
    enforce_execution_gates,
    sha256_text,
)
from .ground import ground_surface

DEFAULT_TEXT_FIELDS = ("discharge_note_full",)
FALLBACK_TEXT_FIELDS = (
    "chief_complaint",
    "history_of_present_illness",
    "past_medical_history",
    "physical_exam",
    "brief_hospital_course",
    "discharge_diagnosis",
    "discharge_medications",
    "discharge_record",
)
ALLOWED_FIELDS = frozenset(DEFAULT_TEXT_FIELDS + FALLBACK_TEXT_FIELDS)

ENTITY_TYPES = (
    "symptom_or_sign",
    "clinical_problem",
    "imaging_finding",
    "physical_exam_finding",
    "anatomical_site",
    "procedure_or_test",
    "device",
    "medication_or_substance",
    "measurement",
    "temporal_expression",
)
ASSERTION_VALUES = ("present", "absent", "possible", "unknown")
TEMPORALITY_VALUES = ("current", "historical", "future_planned", "unclear")
EXPERIENCER_VALUES = ("patient", "family_member", "other", "unknown")
LATERALITY_VALUES = (
    "left",
    "right",
    "bilateral",
    "midline",
    "not_stated",
    "not_applicable",
)
SEVERITY_VALUES = ("mild", "moderate", "severe", "not_stated", "not_applicable")
TREND_VALUES = (
    "new",
    "increased",
    "decreased",
    "stable",
    "resolved",
    "not_stated",
    "not_applicable",
)
MENTION_DEFAULTS = {
    "assertion": "present",
    "temporality": "current",
    "experiencer": "patient",
    "laterality": "not_stated",
    "severity": "not_stated",
    "trend": "not_stated",
}
BARE_ADJECTIVE_STOPLIST = {
    "clear",
    "enlarged",
    "mild",
    "moderate",
    "severe",
    "stable",
    "normal",
    "abnormal",
    "positive",
    "negative",
    "prominent",
    "small",
    "large",
    "minimal",
    "marked",
    "equivocal",
    "unchanged",
    "improved",
    "worsened",
}

DEFAULT_CHUNK_CHARS = 3000
DEFAULT_OVERLAP_CHARS = 200
DEFAULT_MAX_TOKENS = 2500
DEFAULT_REQUESTS_PER_MINUTE = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_WORKERS = 1
DEFAULT_TIMEOUT_SECONDS = 300
PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "mentions.md"
KNOWN_MARKER = "[S]"

KNOWN_TOP_LEVEL_FIELDS = (
    "chief_complaint",
    "ed_chief_complaint",
    "allergies",
    "primary_diagnosis_name",
    "standard_diagnosis_name",
    "rhythm",
    "standard_rhythm",
    "primary_service",
    "standard_service_name",
)
KNOWN_CONTAINER_FIELDS = (
    "chief_complaint_concepts",
    "ed_chief_complaint_concepts",
    "allergy_concepts",
    "other_diagnoses",
    "other_diagnoses_normalized",
    "ed_diagnoses",
    "ed_diagnoses_normalized",
    "investigations",
    "investigations_normalized",
    "medications",
    "medications_normalized",
    "medrecon",
    "medrecon_normalized",
    "procedures",
    "procedures_normalized",
    "poe_lab_imaging",
    "poe_lab_imaging_normalized",
)
KNOWN_VALUE_KEYS = frozenset(
    {
        "source",
        "standard",
        "source_label",
        "standard_test_name",
        "label",
        "source_exam_name",
        "standard_exam_name",
        "exam_name",
        "source_drug",
        "standard_ingredients",
        "drug",
        "name",
        "etcdescription",
        "procedure_name",
        "standard_procedure_name",
        "icd_title",
        "diagnosis_name",
        "order_type",
        "order_subtype",
    }
)


class _TokenBucket:
    """Thread-safe global request-rate cap for concurrent workers."""

    def __init__(self, requests_per_minute: int, burst: int) -> None:
        self._interval = 60.0 / max(1, requests_per_minute)
        self._burst = max(1, burst)
        self._tokens = float(self._burst)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    self._burst, self._tokens + (now - self._last) / self._interval
                )
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) * self._interval
            time.sleep(wait)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _has_alphanumeric(value: str) -> bool:
    return any(character.isalnum() for character in value)


def default_prompt_text() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _add_known_surface(result: set[str], value: object) -> None:
    if not isinstance(value, str):
        return
    surface = " ".join(value.split()).strip()
    if len(surface) < 2 or not _has_alphanumeric(surface):
        return
    if surface.replace(".", "").replace("-", "").isdigit() and len(surface) < 4:
        return
    result.add(surface)


def _collect_known_values(result: set[str], value: object, key: str | None = None) -> None:
    if isinstance(value, Mapping):
        for child_key, child_value in value.items():
            if child_key in KNOWN_VALUE_KEYS:
                if isinstance(child_value, Sequence) and not isinstance(child_value, str):
                    for item in child_value:
                        _add_known_surface(result, item)
                else:
                    _add_known_surface(result, child_value)
            if isinstance(child_value, (Mapping, list, tuple)):
                _collect_known_values(result, child_value, child_key)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str) and key in KNOWN_CONTAINER_FIELDS:
                _add_known_surface(result, item)
            else:
                _collect_known_values(result, item, key)


def known_surfaces_for_visit(visit: Mapping[str, Any]) -> tuple[str, ...]:
    """Return clinical surfaces already represented by structured visit fields."""
    result: set[str] = set()
    for field in KNOWN_TOP_LEVEL_FIELDS:
        _add_known_surface(result, visit.get(field))
    for field in KNOWN_CONTAINER_FIELDS:
        _collect_known_values(result, visit.get(field), field)
    return tuple(sorted(result, key=lambda item: (-len(item), item.casefold())))


def _surface_pattern(surface: str) -> re.Pattern[str]:
    parts = [re.escape(part) for part in surface.split()]
    body = r"\s+".join(parts)
    prefix = r"(?<!\w)" if surface[0].isalnum() else ""
    suffix = r"(?!\w)" if surface[-1].isalnum() else ""
    return re.compile(prefix + body + suffix, flags=re.IGNORECASE)


def mask_structured_surfaces(
    text: str, surfaces: Sequence[str]
) -> tuple[str, list[dict[str, Any]], int]:
    """Replace non-overlapping known spans and report residual alphanumeric chars."""
    candidates: list[tuple[int, int, str]] = []
    for surface in surfaces:
        for match in _surface_pattern(surface).finditer(text):
            candidates.append((match.start(), match.end(), surface))
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2].casefold()))
    selected: list[tuple[int, int, str]] = []
    occupied_end = -1
    for start, end, surface in candidates:
        if start < occupied_end:
            continue
        selected.append((start, end, surface))
        occupied_end = end

    pieces: list[str] = []
    cursor = 0
    spans: list[dict[str, Any]] = []
    for start, end, surface in selected:
        prefix = text[cursor:start]
        pieces.append(prefix)
        pieces.append(KNOWN_MARKER)
        spans.append({"start": start, "end": end, "surface": text[start:end]})
        cursor = end
    suffix = text[cursor:]
    pieces.append(suffix)
    model_text = "".join(pieces)
    meaningful_alnum = 0
    for line in model_text.replace(KNOWN_MARKER, "").splitlines():
        stripped = line.strip()
        if not stripped or (stripped.endswith(":") and len(stripped) <= 80):
            continue
        meaningful_alnum += sum(character.isalnum() for character in stripped)
    return model_text, spans, meaningful_alnum


def chunk_text(text: str, max_chars: int, overlap: int) -> list[tuple[int, int]]:
    if max_chars <= overlap + 1:
        raise NerError("CHUNK_CONFIG_INVALID", f"{max_chars=} {overlap=}")
    spans: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            minimum = start + max_chars // 2
            candidates = (
                text.rfind("\n\n", minimum, end),
                text.rfind("\n", minimum, end),
                text.rfind(". ", minimum, end),
                text.rfind(" ", minimum, end),
            )
            boundary = max(candidates)
            if boundary >= minimum:
                end = boundary + (
                    2 if text[boundary : boundary + 2] in {"\n\n", ". "} else 1
                )
        if end <= start:
            end = min(len(text), start + max_chars)
        if text[start:end].strip():
            spans.append((start, end))
        if end >= len(text):
            break
        next_start = end - overlap
        if next_start <= start:
            next_start = start + max_chars - overlap
        start = next_start
    return spans


def _field_text(visit: Mapping[str, Any], field: str) -> str | None:
    value = visit.get(field)
    if not isinstance(value, str) or not _has_alphanumeric(value):
        return None
    return value


def select_fields_for_visit(
    visit: Mapping[str, Any], requested: Sequence[str]
) -> list[tuple[str, str]]:
    selected: list[tuple[str, str]] = []
    for field in requested:
        text = _field_text(visit, field)
        if text is not None:
            selected.append((field, text))
    if selected:
        return selected
    if tuple(requested) == DEFAULT_TEXT_FIELDS:
        for field in FALLBACK_TEXT_FIELDS:
            text = _field_text(visit, field)
            if text is not None:
                selected.append((field, text))
    return selected


def iter_visit_documents(
    visits: Iterable[Mapping[str, Any]],
    *,
    fields: Sequence[str],
    max_chunk_chars: int,
    overlap_chars: int,
    max_visits: int | None,
) -> Iterator[dict[str, Any]]:
    seen: set[str] = set()
    emitted_visits = 0
    for visit in visits:
        hadm_id = str(visit.get("hadm_id") or "").strip()
        subject_id = str(visit.get("subject_id") or "").strip()
        if not hadm_id or not subject_id:
            raise NerError("VISIT_ID_MISSING", f"subject_id={subject_id!r} hadm_id={hadm_id!r}")
        if hadm_id in seen:
            raise NerError("VISIT_HADM_DUPLICATE", hadm_id)
        seen.add(hadm_id)
        if max_visits is not None and emitted_visits >= max_visits:
            return
        pairs = select_fields_for_visit(visit, fields)
        if not pairs:
            emitted_visits += 1
            continue
        emitted_visits += 1
        known_surfaces = known_surfaces_for_visit(visit)
        for field, text in pairs:
            spans = chunk_text(text, max_chunk_chars, overlap_chars)
            source_hash = sha256_text(text)
            for chunk_index, (start, end) in enumerate(spans):
                chunk = text[start:end]
                model_text, known_spans, residual_alnum = mask_structured_surfaces(
                    chunk, known_surfaces
                )
                yield {
                    "doc_id": f"{hadm_id}:{field}:{chunk_index}",
                    "subject_id": subject_id,
                    "hadm_id": hadm_id,
                    "field": field,
                    "chunk_index": chunk_index,
                    "chunk_count": len(spans),
                    "chunk_start": start,
                    "chunk_end": end,
                    "source_text_sha256": source_hash,
                    "chunk_text": chunk,
                    "chunk_text_sha256": sha256_text(chunk),
                    "model_text": model_text,
                    "model_text_sha256": sha256_text(model_text),
                    "known_spans": known_spans,
                    "known_span_count": len(known_spans),
                    "residual_alnum_chars": residual_alnum,
                    "skip_model": residual_alnum == 0,
                }


def _identity(
    *,
    input_path: Path,
    input_sha256: str,
    fields: Sequence[str],
    max_visits: int | None,
    max_chunk_chars: int,
    overlap_chars: int,
    prompt_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": PIPELINE_VERSION,
        "input_path": str(input_path.resolve()),
        "input_sha256": input_sha256,
        "fields": list(fields),
        "max_visits": max_visits,
        "max_chunk_chars": max_chunk_chars,
        "overlap_chars": overlap_chars,
        "prompt_sha256": prompt_sha256,
        "prompt_name": "mentions.md",
    }


def _assert_output_dir(input_path: Path, output_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    extract_dir = input_path.parent.resolve()
    if output_dir == extract_dir or extract_dir in output_dir.parents:
        raise NerError(
            "REFUSING_EXTRACT_DIR",
            "refusing to write into the extract directory",
        )
    return output_dir


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())


def _checkpoint_index(path: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        doc_id = row.get("doc_id")
        if isinstance(doc_id, str):
            index[doc_id] = row
    return index


def _write_progress(output_dir: Path, payload: Mapping[str, Any]) -> None:
    safe = {key: value for key, value in payload.items() if key != "chunk_text"}
    atomic_write_json(output_dir / "progress.json", dict(safe))


def prepare(
    *,
    input_path: Path,
    output_dir: Path,
    fields: Sequence[str] = DEFAULT_TEXT_FIELDS,
    max_visits: int | None = None,
    max_chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    prompt_text: str | None = None,
) -> dict[str, Any]:
    if not input_path.is_file():
        raise NerError("INPUT_MISSING", str(input_path))
    if input_path.name != "visits.json":
        raise NerError("INPUT_NOT_VISITS_JSON", input_path.name)
    unknown = [field for field in fields if field not in ALLOWED_FIELDS]
    if unknown:
        raise NerError("FIELD_NOT_ALLOWED", ",".join(unknown))
    output_dir = _assert_output_dir(input_path, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    prompt = prompt_text if prompt_text is not None else default_prompt_text()
    identity = _identity(
        input_path=input_path,
        input_sha256=file_sha256(input_path),
        fields=fields,
        max_visits=max_visits,
        max_chunk_chars=max_chunk_chars,
        overlap_chars=overlap_chars,
        prompt_sha256=sha256_text(prompt),
    )
    identity_sha = canonical_hash(identity)
    manifest_path = output_dir / "manifest.json"
    existing = read_manifest(manifest_path)
    if existing is not None and existing.get("identity_sha256") != identity_sha:
        raise NerError("MANIFEST_IDENTITY_MISMATCH", "refusing to mix runs; use a new output-dir")

    documents_path = output_dir / "documents.jsonl"
    if existing is not None and existing.get("prepare_status") == "complete":
        if not documents_path.is_file():
            raise NerError("DOCUMENTS_MISSING", str(documents_path))
        summary = existing.get("prepare_summary") or {}
        return {
            "schema_version": PIPELINE_VERSION,
            "stage": "prepare",
            "resumed": True,
            "output_dir": str(output_dir),
            **summary,
        }

    documents_path.unlink(missing_ok=True)
    visits = 0
    chunks = 0
    fields_used: dict[str, int] = {}
    source_chars = 0
    model_chars = 0
    known_spans = 0
    skipped_chunks = 0
    empty_visits = 0
    seen_hadm: set[str] = set()
    for visit in iter_json_array(input_path):
        if max_visits is not None and visits >= max_visits:
            break
        hadm_id = str(visit.get("hadm_id") or "").strip()
        if hadm_id:
            if hadm_id in seen_hadm:
                raise NerError("VISIT_HADM_DUPLICATE", hadm_id)
            seen_hadm.add(hadm_id)
        pairs = select_fields_for_visit(visit, fields)
        visits += 1
        if not pairs:
            empty_visits += 1
            continue
        for row in iter_visit_documents(
            [visit],
            fields=fields,
            max_chunk_chars=max_chunk_chars,
            overlap_chars=overlap_chars,
            max_visits=None,
        ):
            _append_jsonl(documents_path, row)
            chunks += 1
            fields_used[row["field"]] = fields_used.get(row["field"], 0) + 1
            source_chars += len(row["chunk_text"])
            model_chars += len(row["model_text"])
            known_spans += int(row["known_span_count"])
            skipped_chunks += int(bool(row["skip_model"]))

    summary = {
        "visits_selected": visits,
        "visits_with_text": visits - empty_visits,
        "empty_visits": empty_visits,
        "chunks": chunks,
        "field_chunk_counts": fields_used,
        "source_chars": source_chars,
        "model_chars": model_chars,
        "model_char_reduction_rate": (
            round(1 - model_chars / source_chars, 4) if source_chars else 0.0
        ),
        "known_spans": known_spans,
        "skipped_chunks": skipped_chunks,
        "api_candidate_chunks": chunks - skipped_chunks,
        "documents_path": str(documents_path),
        "prepared_at_utc": _utc_now(),
        "gold_status": "exploratory_unreviewed",
    }
    manifest = {
        "identity": identity,
        "identity_sha256": identity_sha,
        "status": "prepared",
        "prepare_status": "complete",
        "prepare_summary": summary,
        "kind": "mcq_visit_ner",
        "gold_status": "exploratory_unreviewed",
    }
    write_manifest(manifest_path, manifest)
    _write_progress(
        output_dir,
        {
            "stage": "prepare",
            "status": "complete",
            "visits_selected": visits,
            "chunks": chunks,
            "updated_at_utc": _utc_now(),
        },
    )
    return {
        "schema_version": PIPELINE_VERSION,
        "stage": "prepare",
        "resumed": False,
        "output_dir": str(output_dir),
        **summary,
    }


def load_documents(output_dir: Path) -> list[dict[str, Any]]:
    path = Path(output_dir) / "documents.jsonl"
    if not path.is_file():
        raise NerError("DOCUMENTS_MISSING", "run `prepare` first")
    rows = read_jsonl(path)
    rows.sort(key=lambda row: (row["hadm_id"], row["field"], row["chunk_index"]))
    return rows


def _validate_and_fill_mention(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    surface = raw.get("surface_text")
    if not isinstance(surface, str) or not surface.strip():
        return None
    if surface.strip().casefold() in BARE_ADJECTIVE_STOPLIST:
        return None
    entity_type = raw.get("entity_type")
    if entity_type not in ENTITY_TYPES:
        return None
    mention = {"surface_text": surface, "entity_type": entity_type}
    for field, allowed in (
        ("assertion", ASSERTION_VALUES),
        ("temporality", TEMPORALITY_VALUES),
        ("experiencer", EXPERIENCER_VALUES),
        ("laterality", LATERALITY_VALUES),
        ("severity", SEVERITY_VALUES),
        ("trend", TREND_VALUES),
    ):
        value = raw.get(field, MENTION_DEFAULTS[field])
        mention[field] = value if value in allowed else MENTION_DEFAULTS[field]
    return mention


def extract_mentions_for_chunk(
    settings: ApiSettings,
    system_prompt: str,
    doc: Mapping[str, Any],
    *,
    max_tokens: int,
    maximum_retries: int,
    interval_seconds: float,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    transport: Transport | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int], int]:
    chunk_text_value = doc["chunk_text"]
    model_text_value = doc.get("model_text", chunk_text_value)
    payload = {
        "doc_id": doc["doc_id"],
        "hadm_id": doc["hadm_id"],
        "field": doc["field"],
        "chunk_index": doc["chunk_index"],
        "chunk_count": doc["chunk_count"],
        "section_text_sha256": doc.get(
            "model_text_sha256", doc["chunk_text_sha256"]
        ),
        "source_chunk_text_sha256": doc["chunk_text_sha256"],
        "section_text": model_text_value,
        "already_structured_marker": KNOWN_MARKER,
        "already_structured_span_count": doc.get("known_span_count", 0),
    }
    parsed, usage, attempts = call_with_retry(
        settings,
        system_prompt,
        payload,
        max_tokens=max_tokens,
        maximum_retries=maximum_retries,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
        transport=transport,
    )
    raw_mentions = parsed.get("mentions")
    if not isinstance(raw_mentions, list):
        raise NerError("MENTIONS_NOT_LIST", type(raw_mentions).__name__)
    grounded: list[dict[str, Any]] = []
    dropped_ungrounded = 0
    dropped_already_structured = 0
    known_spans = doc.get("known_spans") or []
    for raw in raw_mentions:
        if not isinstance(raw, dict):
            continue
        mention = _validate_and_fill_mention(raw)
        if mention is None:
            continue
        located = ground_surface(chunk_text_value, mention["surface_text"])
        if located is None:
            dropped_ungrounded += 1
            continue
        start, end, rewritten = located
        if any(
            start < int(known.get("end", -1)) and end > int(known.get("start", -1))
            for known in known_spans
            if isinstance(known, Mapping)
        ):
            dropped_already_structured += 1
            continue
        if rewritten:
            mention["surface_text"] = chunk_text_value[start:end]
        mention["chunk_span_start"] = start
        mention["chunk_span_end"] = end
        mention["field_span_start"] = doc["chunk_start"] + start
        mention["field_span_end"] = doc["chunk_start"] + end
        grounded.append(mention)
    usage_out = dict(usage)
    usage_out["dropped_ungrounded"] = dropped_ungrounded
    usage_out["dropped_already_structured"] = dropped_already_structured
    return grounded, usage_out, attempts


def run_mentions(
    output_dir: Path,
    *,
    execute: bool,
    data_transfer_authorized: bool,
    env_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
    maximum_retries: int = DEFAULT_MAX_RETRIES,
    retry_failed: bool = False,
    all_visits: bool = False,
    workers: int = DEFAULT_WORKERS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    prompt_text: str | None = None,
    transport: Transport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    report: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    manifest_path = output_dir / "manifest.json"
    manifest = read_manifest(manifest_path)
    if manifest is None:
        raise NerError("MANIFEST_MISSING", "run `prepare` first")
    if not execute:
        raise NerError(
            "MODEL_EXECUTION_NOT_AUTHORIZED",
            "pass --execute to perform model calls",
        )
    identity = manifest.get("identity") or {}
    max_visits = identity.get("max_visits")
    if max_visits is None and not all_visits:
        raise NerError(
            "VISIT_LIMIT_REQUIRED",
            "prepare used all visits; pass --all-visits to send every remaining document, "
            "or re-prepare with --max-visits (pilot 100 first)",
        )

    settings = ApiSettings.resolve(env_file, environ=environ)
    enforce_execution_gates(
        execute=execute,
        data_transfer_authorized=data_transfer_authorized,
        settings=settings,
        environ=environ,
    )

    documents = load_documents(output_dir)
    system_prompt = prompt_text if prompt_text is not None else default_prompt_text()
    results_path = output_dir / "mention_results.jsonl"
    failures_path = output_dir / "mention_failures.jsonl"
    done = _checkpoint_index(results_path)
    failed = _checkpoint_index(failures_path)
    if retry_failed:
        pending = [row for row in documents if row["doc_id"] not in done]
    else:
        pending = [
            row
            for row in documents
            if row["doc_id"] not in done and row["doc_id"] not in failed
        ]

    workers = max(1, int(workers))
    interval = 60.0 / max(1, requests_per_minute)
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    successful = 0
    failed_count = 0
    model_calls = 0
    write_lock = threading.Lock()
    limiter = _TokenBucket(requests_per_minute, burst=workers) if workers > 1 else None
    if report:
        report(
            f"[mentions] chunks={len(documents)} pending={len(pending)} "
            f"workers={workers} rate={requests_per_minute}/min "
            f"model={settings.model} base={settings.base_url}"
        )

    def process_doc(doc: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if limiter is not None and not doc.get("skip_model"):
            limiter.acquire()
        try:
            if doc.get("skip_model"):
                mentions = []
                usage = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "dropped_ungrounded": 0,
                    "dropped_already_structured": 0,
                }
                attempts = 0
            else:
                mentions, usage, attempts = extract_mentions_for_chunk(
                    settings,
                    system_prompt,
                    doc,
                    max_tokens=max_tokens,
                    maximum_retries=maximum_retries,
                    interval_seconds=interval,
                    timeout_seconds=timeout_seconds,
                    transport=transport,
                )
        except NerError as error:
            return (
                "fail",
                {
                    "doc_id": doc["doc_id"],
                    "hadm_id": doc["hadm_id"],
                    "field": doc["field"],
                    "reason_code": error.reason_code,
                    "recorded_at_utc": _utc_now(),
                },
            )
        except TimeoutError:
            return (
                "fail",
                {
                    "doc_id": doc["doc_id"],
                    "hadm_id": doc["hadm_id"],
                    "field": doc["field"],
                    "reason_code": "API_TIMEOUT",
                    "recorded_at_utc": _utc_now(),
                },
            )
        row = {
            "schema_version": PIPELINE_VERSION,
            "doc_id": doc["doc_id"],
            "subject_id": doc["subject_id"],
            "hadm_id": doc["hadm_id"],
            "field": doc["field"],
            "chunk_index": doc["chunk_index"],
            "chunk_count": doc["chunk_count"],
            "chunk_start": doc["chunk_start"],
            "chunk_end": doc["chunk_end"],
            "source_text_sha256": doc["source_text_sha256"],
            "chunk_text_sha256": doc["chunk_text_sha256"],
            "model_text_sha256": doc.get("model_text_sha256"),
            "known_span_count": doc.get("known_span_count", 0),
            "skipped_model": bool(doc.get("skip_model")),
            "extractor_name": f"{settings.provider}/{settings.model}",
            "extractor_version": settings.model_version,
            "mentions": mentions,
            "usage": {
                key: usage.get(key, 0)
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            },
            "dropped_ungrounded": usage.get("dropped_ungrounded", 0),
            "dropped_already_structured": usage.get(
                "dropped_already_structured", 0
            ),
            "model_calls": attempts,
            "recorded_at_utc": _utc_now(),
        }
        return ("ok", row)

    def handle(kind: str, payload: dict[str, Any]) -> None:
        nonlocal successful, failed_count, model_calls
        with write_lock:
            if kind == "fail":
                failed_count += 1
                _append_jsonl(failures_path, payload)
                if report:
                    report(f"  {payload['doc_id']} FAILED ({payload['reason_code']})")
                return
            _append_jsonl(results_path, payload)
            successful += 1
            model_calls += payload["model_calls"]
            for key in usage_total:
                usage_total[key] += payload["usage"].get(key, 0)
            if report:
                report(
                    f"  {successful + failed_count}/{len(pending)} "
                    f"{payload['doc_id']} -> {len(payload['mentions'])} mentions"
                )
            _write_progress(
                output_dir,
                {
                    "stage": "mentions",
                    "status": "running",
                    "pending": len(pending),
                    "successful": successful,
                    "failed": failed_count,
                    "workers": workers,
                    "updated_at_utc": _utc_now(),
                },
            )

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(process_doc, doc) for doc in pending]
            for future in as_completed(futures):
                kind, payload = future.result()
                handle(kind, payload)
    else:
        for index, doc in enumerate(pending, start=1):
            kind, payload = process_doc(doc)
            handle(kind, payload)
            if not doc.get("skip_model") and any(
                not row.get("skip_model") for row in pending[index:]
            ):
                sleep(interval)

    remaining = len(pending) - successful - failed_count
    run_status = "complete" if remaining == 0 else "running"
    manifest["status"] = run_status
    manifest["mentions_status"] = run_status
    write_manifest(manifest_path, manifest)
    _write_progress(
        output_dir,
        {
            "stage": "mentions",
            "status": run_status,
            "successful": successful,
            "failed": failed_count,
            "updated_at_utc": _utc_now(),
        },
    )
    return {
        "schema_version": PIPELINE_VERSION,
        "stage": "mentions",
        "chunks": len(documents),
        "pending": len(pending),
        "successful": successful,
        "failed": failed_count,
        "workers": workers,
        "model_calls": model_calls,
        "usage": usage_total,
        "checkpoint": str(results_path),
        "failures": str(failures_path),
        "gold_status": "exploratory_unreviewed",
    }


def _merge_visit_mentions(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    order: list[tuple[str, str]] = []
    for row in rows:
        key = (str(row["subject_id"]), str(row["hadm_id"]))
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        for mention in row.get("mentions") or []:
            item = dict(mention)
            item["field"] = row["field"]
            grouped[key].append(item)
    compiled: list[dict[str, Any]] = []
    for subject_id, hadm_id in order:
        mentions = grouped[(subject_id, hadm_id)]
        mentions.sort(
            key=lambda item: (
                item.get("field", ""),
                item.get("field_span_start", 0),
                item.get("field_span_end", 0),
            )
        )
        seen: set[tuple[str, int, int, str]] = set()
        unique: list[dict[str, Any]] = []
        for mention in mentions:
            key = (
                str(mention.get("field")),
                int(mention.get("field_span_start", -1)),
                int(mention.get("field_span_end", -1)),
                str(mention.get("entity_type")),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(mention)
        for index, mention in enumerate(unique, start=1):
            mention["local_id"] = f"m{index}"
        compiled.append(
            {
                "schema_version": PIPELINE_VERSION,
                "subject_id": subject_id,
                "hadm_id": hadm_id,
                "mention_count": len(unique),
                "mentions": unique,
            }
        )
    return compiled


def compile_mentions(output_dir: Path) -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    results_path = output_dir / "mention_results.jsonl"
    if not results_path.is_file():
        raise NerError("RESULTS_MISSING", str(results_path))
    rows = read_jsonl(results_path)
    compiled = _merge_visit_mentions(rows)
    compiled_path = output_dir / "visit_mentions.jsonl"
    documents = load_documents(output_dir)
    expected_ids = {row["doc_id"] for row in documents}
    done_ids = {row["doc_id"] for row in rows if isinstance(row.get("doc_id"), str)}
    incomplete = sorted(expected_ids - done_ids)
    atomic_write_jsonl(compiled_path, compiled)
    type_counts: dict[str, int] = {}
    mention_total = 0
    for visit in compiled:
        for mention in visit["mentions"]:
            mention_total += 1
            entity_type = str(mention.get("entity_type") or "unknown")
            type_counts[entity_type] = type_counts.get(entity_type, 0) + 1
    summary = {
        "schema_version": PIPELINE_VERSION,
        "stage": "compile",
        "visits": len(compiled),
        "mentions": mention_total,
        "entity_type_counts": dict(sorted(type_counts.items())),
        "incomplete_docs": len(incomplete),
        "compiled_path": str(compiled_path),
        "gold_status": "exploratory_unreviewed",
        "compiled_at_utc": _utc_now(),
    }
    atomic_write_json(output_dir / "compile_summary.json", summary)
    return summary


def status(output_dir: Path) -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    manifest = read_manifest(output_dir / "manifest.json") or {}
    documents = (
        read_jsonl(output_dir / "documents.jsonl")
        if (output_dir / "documents.jsonl").is_file()
        else []
    )
    results = (
        read_jsonl(output_dir / "mention_results.jsonl")
        if (output_dir / "mention_results.jsonl").is_file()
        else []
    )
    failures = (
        read_jsonl(output_dir / "mention_failures.jsonl")
        if (output_dir / "mention_failures.jsonl").is_file()
        else []
    )
    return {
        "schema_version": PIPELINE_VERSION,
        "stage": "status",
        "status": manifest.get("status"),
        "prepare_status": manifest.get("prepare_status"),
        "mentions_status": manifest.get("mentions_status"),
        "chunks": len(documents),
        "mention_docs_done": len({row.get("doc_id") for row in results}),
        "mention_docs_failed": len({row.get("doc_id") for row in failures}),
        "max_visits": (manifest.get("identity") or {}).get("max_visits"),
        "gold_status": "exploratory_unreviewed",
        "does_not_overwrite_extract": True,
        "does_not_rewrite_ds": True,
    }


def _parse_fields(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_TEXT_FIELDS
    fields = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not fields:
        raise NerError("FIELDS_EMPTY", raw)
    return fields


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Visit discharge-summary NER via an OpenAI-compatible API. "
            "Default is dry-run (prepare only). Restricted MIMIC text is not "
            "sent unless --execute, --confirm-data-transfer-authorized, and "
            "MCQ_VISIT_NER_EXTERNAL_API_APPROVED=YES are all set."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_cmd = subparsers.add_parser("prepare", help="Chunk visits.json; no API calls")
    prepare_cmd.add_argument("--input", type=Path, required=True)
    prepare_cmd.add_argument("--output-dir", type=Path, required=True)
    prepare_cmd.add_argument("--max-visits", type=int, default=None)
    prepare_cmd.add_argument("--fields", type=str, default=None)
    prepare_cmd.add_argument("--max-chunk-chars", type=int, default=DEFAULT_CHUNK_CHARS)
    prepare_cmd.add_argument("--overlap-chars", type=int, default=DEFAULT_OVERLAP_CHARS)

    run_cmd = subparsers.add_parser(
        "run", help="Call the model on pending chunks (fail-closed)"
    )
    run_cmd.add_argument("--output-dir", type=Path, required=True)
    run_cmd.add_argument("--env-file", type=Path, default=None)
    run_cmd.add_argument("--execute", action="store_true")
    run_cmd.add_argument("--confirm-data-transfer-authorized", action="store_true")
    run_cmd.add_argument("--all-visits", action="store_true")
    run_cmd.add_argument("--retry-failed", action="store_true")
    run_cmd.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    run_cmd.add_argument(
        "--requests-per-minute", type=int, default=DEFAULT_REQUESTS_PER_MINUTE
    )
    run_cmd.add_argument("--maximum-retries", type=int, default=DEFAULT_MAX_RETRIES)
    run_cmd.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Concurrent chunk workers (default 1 = sequential). Full 10k: start at 8.",
    )
    run_cmd.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout per model call (default 300).",
    )

    subparsers.add_parser("status", help="Progress without clinical text").add_argument(
        "--output-dir", type=Path, required=True
    )
    subparsers.add_parser("compile", help="Merge grounded mentions per visit").add_argument(
        "--output-dir", type=Path, required=True
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    def reporter(message: str) -> None:
        print(message, flush=True)

    try:
        if args.command == "prepare":
            result = prepare(
                input_path=args.input,
                output_dir=args.output_dir,
                fields=_parse_fields(args.fields),
                max_visits=args.max_visits,
                max_chunk_chars=args.max_chunk_chars,
                overlap_chars=args.overlap_chars,
            )
        elif args.command == "run":
            result = run_mentions(
                args.output_dir,
                execute=args.execute,
                data_transfer_authorized=args.confirm_data_transfer_authorized,
                env_file=args.env_file,
                all_visits=args.all_visits,
                retry_failed=args.retry_failed,
                max_tokens=args.max_tokens,
                requests_per_minute=args.requests_per_minute,
                maximum_retries=args.maximum_retries,
                workers=args.workers,
                timeout_seconds=args.timeout_seconds,
                report=reporter,
            )
        elif args.command == "status":
            result = status(args.output_dir)
        elif args.command == "compile":
            result = compile_mentions(args.output_dir)
        else:
            raise SystemExit("unknown command")
    except NerError as error:
        print(f"{error.reason_code}: {error}", file=sys.stderr, flush=True)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
