"""Clean two-stage clinical NER + relation extraction via an OpenAI-compatible API.

Design goals vs. the previous implementation:

- The model returns ``surface_text`` and attributes only; character offsets are
  grounded deterministically in Python (exact, then casefold + whitespace
  folding). The model is never asked to produce zero-based Unicode offsets, which
  was the main source of ``MENTION_SURFACE_MISMATCH`` churn.
- Relations reference the already-grounded mentions by ``local_id`` only; the
  evidence span is computed deterministically as the minimal span covering both
  endpoints. The model is never asked to produce evidence offsets.
- Long documents are split at deterministic natural boundaries before the first
  call, with a fixed chunk budget and no unbounded recursive re-splitting.
- Every stage is resumable from append-only JSONL checkpoints keyed by document id.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from . import PIPELINE_VERSION

# ---------------------------------------------------------------------------
# Frozen vocabulary (mirrors data_pipeline/text_ner/annotation_contracts.py)
# ---------------------------------------------------------------------------

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
LATERALITY_VALUES = ("left", "right", "bilateral", "midline", "not_stated", "not_applicable")
SEVERITY_VALUES = ("mild", "moderate", "severe", "not_stated", "not_applicable")
TREND_VALUES = ("new", "increased", "decreased", "stable", "resolved", "not_stated", "not_applicable")
RELATION_TYPES = (
    "located_at",
    "has_measurement",
    "has_temporal_context",
    "compared_with",
    "suggestive_of",
    "device_positioned_at",
    "recommendation_for",
    "test_for",
)

# Deterministic endpoint entity-type constraints applied after grounding.
RELATION_TYPE_RULES: dict[str, dict[str, str]] = {
    "located_at": {"target": "anatomical_site"},
    "has_measurement": {"target": "measurement"},
    "has_temporal_context": {"target": "temporal_expression"},
    "compared_with": {},
    "suggestive_of": {"target": "clinical_problem"},
    "device_positioned_at": {"source": "device", "target": "anatomical_site"},
    "recommendation_for": {"source": "procedure_or_test"},
    "test_for": {"source": "procedure_or_test", "target": "clinical_problem"},
}

# Bare adjectives/adverbs that must never be standalone entities.
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

# Body-function / contour / silhouette / exam-description terms that must not be
# tagged `anatomical_site` (they are findings or functions, not body locations).
ANATOMICAL_SITE_STOPWORDS = (
    "function",
    "functioning",
    "contour",
    "silhouette",
    "sound",
    "murmur",
    "pmi",
    "motility",
    "perfusion",
    "patency",
    "caliber",
    "drainage",
)

# Relations whose evidence span exceeds this many characters are treated as
# cross-paragraph false positives and dropped.
MAX_EVIDENCE_CHARS = 300

# A single relation API call sees at most this many mentions, keeping the model's
# relation-list output bounded and avoiding OUTPUT_TRUNCATED on dense sections.
MAX_RELATION_MENTIONS_PER_CALL = 50

# Lexical cues that must appear in the evidence for a relation type to survive.
# Types not listed here are not lexically gated.
RELATION_EVIDENCE_HINTS: dict[str, tuple[str, ...]] = {
    "compared_with": (
        "compared", "similar", "prior", "previously", "stable", "unchanged",
        "worse", "worsen", "better", "improved", "increased", "decreased",
        "larger", "smaller", "enlarged", "reduced", "new", "progression",
        "since", "than",
    ),
    "suggestive_of": (
        "suggest", "consistent", "concern", "likely", "indicate", "worrisome",
        "suspicious", "compatible", "eval", "evaluate", "concerning",
        "concerning for",
    ),
    "test_for": (
        "test", "assay", "culture", "screen", "detect", "rule out", "ruled out",
        " for ", "workup", "negative", "positive",
    ),
    "recommendation_for": (
        "recommend", "plan", "start", "initiate", "will", "should", "advise",
        "treat", "need", "consider", "continue", "begin",
    ),
}


def _evidence_matches_relation(relation_type: str, evidence_text: str) -> bool:
    if relation_type == "has_measurement":
        return any(character.isdigit() for character in evidence_text)
    hints = RELATION_EVIDENCE_HINTS.get(relation_type)
    if hints is None:
        return True
    folded = evidence_text.casefold()
    return any(hint in folded for hint in hints)

MENTION_DEFAULTS = {
    "assertion": "present",
    "temporality": "current",
    "experiencer": "patient",
    "laterality": "not_stated",
    "severity": "not_stated",
    "trend": "not_stated",
}

# Pricing in CNY per 1,000,000 tokens (DeepSeek V4 flash). Estimation only.
PRICING_CNY_PER_1M = {
    "prompt_cache_hit": 0.02,
    "prompt_cache_miss": 1.0,
    "output": 2.0,
}

ENVIRONMENT_KEYS = (
    "TEXT_NER_API_KEY",
    "TEXT_NER_BASE_URL",
    "TEXT_NER_MODEL",
    "TEXT_NER_MODEL_VERSION",
    "TEXT_NER_PROVIDER",
)

DEFAULT_CHUNK_CHARS = 3000
DEFAULT_OVERLAP_CHARS = 200
DEFAULT_MENTION_MAX_TOKENS = 6000
DEFAULT_RELATION_MAX_TOKENS = 8000
DEFAULT_REQUESTS_PER_MINUTE = 30
DEFAULT_MAX_RETRIES = 3


class PipelineError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}:{sha256_text(payload)[:24]}"


def load_env_file(path: Path) -> dict[str, str]:
    """Read only the five TEXT_NER_* keys from a non-executable KEY=VALUE file."""
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError as error:
        raise PipelineError("ENV_FILE_NOT_FOUND", str(path)) from error
    values: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise PipelineError("ENV_FILE_LINE_INVALID", f"{path}:{line_number}")
        key, raw = stripped.split("=", 1)
        key = key.strip()
        if key not in ENVIRONMENT_KEYS:
            continue  # tolerate other subsystems' keys
        if key in values:
            raise PipelineError("ENV_FILE_KEY_DUPLICATE", f"{path}:{line_number}: {key}")
        value = raw.strip()
        if value[:1] in {"'", '"'} and len(value) >= 2 and value[-1] == value[0]:
            value = value[1:-1]
        values[key] = value
    return values


@dataclass(frozen=True)
class ApiSettings:
    api_key: str
    base_url: str
    model: str
    model_version: str
    provider: str

    @classmethod
    def resolve(cls, env_file: Path | None) -> "ApiSettings":
        file_values = load_env_file(env_file) if env_file is not None else {}
        merged = {key: os.environ.get(key, "").strip() for key in ENVIRONMENT_KEYS}
        for key in ENVIRONMENT_KEYS:
            if not merged[key]:
                merged[key] = file_values.get(key, "")
        provider = merged["TEXT_NER_PROVIDER"] or "openai-compatible"
        missing = [
            key for key in ENVIRONMENT_KEYS[:4] if not merged[key]
        ]
        if missing:
            raise PipelineError("API_ENV_MISSING", ",".join(missing))
        base_url = merged["TEXT_NER_BASE_URL"].rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise PipelineError("API_BASE_URL_INVALID", base_url)
        return cls(
            api_key=merged["TEXT_NER_API_KEY"],
            base_url=base_url,
            model=merged["TEXT_NER_MODEL"],
            model_version=merged["TEXT_NER_MODEL_VERSION"],
            provider=provider,
        )


# ---------------------------------------------------------------------------
# Document building from the accepted aggregation package
# ---------------------------------------------------------------------------

TEXT_FIELDS = {
    ("hosp.labevents", "comments", "laboratory_comment"),
    ("hosp.microbiologyevents", "comments", "microbiology_comment"),
    ("ed.triage", "chiefcomplaint", "chief_complaint"),
    ("note.radiology", "text", "radiology_report"),
    ("note.discharge", "text", "discharge_summary"),
}

DOCUMENT_COLUMNS = [
    "doc_id",
    "chunk_index",
    "chunk_count",
    "subject_id",
    "hadm_id",
    "source_table",
    "source_text_field",
    "source_text_kind",
    "source_text_sha256",
    "event_time",
    "chunk_start",
    "chunk_end",
    "chunk_text",
]


def _has_alphanumeric(value: str) -> bool:
    return any(character.isalnum() for character in value)


def chunk_text(text: str, max_chars: int, overlap: int) -> list[tuple[int, int]]:
    """Split into deterministic chunks, preferring paragraph/newline/sentence/space."""
    if max_chars <= overlap + 1:
        raise PipelineError("CHUNK_CONFIG_INVALID", f"{max_chars=} {overlap=}")
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
                end = boundary + (2 if text[boundary : boundary + 2] in {"\n\n", ". "} else 1)
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


def _event_time(record: Mapping[str, Any]) -> str | None:
    for key in ("charttime", "storetime", "chartdate"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def build_documents(
    aggregation_directory: Path,
    output_directory: Path,
    *,
    max_chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> dict[str, Any]:
    raw_path = Path(aggregation_directory) / "raw_source_records.parquet"
    if not raw_path.is_file():
        raise PipelineError("AGGREGATION_MISSING", str(raw_path))
    output_directory = Path(output_directory)
    if output_directory.exists():
        raise FileExistsError(f"output directory already exists: {output_directory}")

    parquet = pq.ParquetFile(raw_path)
    columns = [
        "source_record_id",
        "subject_id",
        "hadm_id",
        "source_table",
        "source_text_field",
        "source_text_kind",
        "source_text",
        "source_text_sha256",
        "clinical_readable_record_json",
    ]
    missing = set(columns) - set(parquet.schema_arrow.names)
    if missing:
        raise PipelineError("AGGREGATION_COLUMNS_MISSING", ",".join(sorted(missing)))

    rows: list[dict[str, Any]] = []
    doc_chunk_counts: Counter[str] = Counter()
    source_doc_counts: Counter[str] = Counter()
    source_char_counts: Counter[str] = Counter()
    for batch in parquet.iter_batches(columns=columns, batch_size=20000):
        values = batch.to_pydict()
        for index in range(batch.num_rows):
            table = values["source_table"][index]
            field = values["source_text_field"][index]
            kind = values["source_text_kind"][index]
            if (table, field, kind) not in TEXT_FIELDS:
                continue
            text = values["source_text"][index]
            if not isinstance(text, str) or not _has_alphanumeric(text):
                continue
            declared_hash = values["source_text_sha256"][index]
            if sha256_text(text) != declared_hash:
                raise PipelineError(
                    "SOURCE_TEXT_HASH_MISMATCH", values["source_record_id"][index]
                )
            doc_id = values["source_record_id"][index]
            record = {}
            raw_record = values["clinical_readable_record_json"][index]
            if isinstance(raw_record, str):
                try:
                    parsed = json.loads(raw_record)
                    if isinstance(parsed, dict):
                        record = parsed
                except json.JSONDecodeError:
                    record = {}
            spans = chunk_text(text, max_chunk_chars, overlap_chars)
            if not spans:
                continue
            source_doc_counts[table] += 1
            source_char_counts[table] += len(text)
            for chunk_index, (start, end) in enumerate(spans):
                rows.append(
                    {
                        "doc_id": doc_id,
                        "chunk_index": chunk_index,
                        "chunk_count": len(spans),
                        "subject_id": str(values["subject_id"][index]),
                        "hadm_id": str(values["hadm_id"][index]),
                        "source_table": table,
                        "source_text_field": field,
                        "source_text_kind": kind,
                        "source_text_sha256": declared_hash,
                        "event_time": _event_time(record),
                        "chunk_start": start,
                        "chunk_end": end,
                        "chunk_text": text[start:end],
                    }
                )
            doc_chunk_counts[doc_id] += len(spans)

    rows.sort(key=lambda row: (row["doc_id"], row["chunk_index"]))
    summary = {
        "schema_version": PIPELINE_VERSION,
        "kind": "documents",
        "documents": len(doc_chunk_counts),
        "chunks": len(rows),
        "source_document_counts": dict(sorted(source_doc_counts.items())),
        "source_character_counts": dict(sorted(source_char_counts.items())),
        "max_chunk_chars": max_chunk_chars,
        "overlap_chars": overlap_chars,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    output_directory.mkdir(parents=True)
    schema = pa.schema(
        [
            ("doc_id", pa.string()),
            ("chunk_index", pa.int64()),
            ("chunk_count", pa.int64()),
            ("subject_id", pa.string()),
            ("hadm_id", pa.string()),
            ("source_table", pa.string()),
            ("source_text_field", pa.string()),
            ("source_text_kind", pa.string()),
            ("source_text_sha256", pa.string()),
            ("event_time", pa.string()),
            ("chunk_start", pa.int64()),
            ("chunk_end", pa.int64()),
            ("chunk_text", pa.string()),
        ],
        metadata={b"schema": PIPELINE_VERSION.encode("ascii")},
    )
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), output_directory / "documents.parquet")
    (output_directory / "documents_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def load_documents(output_directory: Path) -> list[dict[str, Any]]:
    path = Path(output_directory) / "documents.parquet"
    if not path.is_file():
        raise PipelineError("DOCUMENTS_MISSING", "run `prepare` first")
    table = pq.read_table(path)
    rows = table.to_pylist()
    rows.sort(key=lambda row: (row["doc_id"], row["chunk_index"]))
    return rows


def group_documents(rows: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["doc_id"], []).append(row)
    for chunks in grouped.values():
        chunks.sort(key=lambda row: row["chunk_index"])
    return grouped


# ---------------------------------------------------------------------------
# Deterministic span grounding
# ---------------------------------------------------------------------------

def _exact_occurrences(text: str, surface: str) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    search_from = 0
    while True:
        start = text.find(surface, search_from)
        if start < 0:
            return result
        result.append((start, start + len(surface)))
        search_from = start + 1


def _casefold_whitespace_occurrences(text: str, surface: str) -> list[tuple[int, int]]:
    def fold(value: str) -> tuple[str, list[int], list[int]]:
        normalized: list[str] = []
        starts: list[int] = []
        ends: list[int] = []
        previous_ws = False
        for index, character in enumerate(value):
            if character.isspace():
                if previous_ws:
                    ends[-1] = index + 1
                else:
                    normalized.append(" ")
                    starts.append(index)
                    ends.append(index + 1)
                previous_ws = True
                continue
            previous_ws = False
            for folded in character.casefold():
                normalized.append(folded)
                starts.append(index)
                ends.append(index + 1)
        return "".join(normalized), starts, ends

    norm_text, source_starts, source_ends = fold(text)
    norm_surface, _, _ = fold(surface)
    norm_surface = norm_surface.strip()
    if not norm_surface:
        return []
    occurrences: set[tuple[int, int]] = set()
    search_from = 0
    while True:
        start = norm_text.find(norm_surface, search_from)
        if start < 0:
            return sorted(occurrences)
        end = start + len(norm_surface)
        occurrences.add((source_starts[start], source_ends[end - 1]))
        search_from = start + 1


def ground_surface(text: str, surface: str) -> tuple[int, int, bool] | None:
    """Ground a model surface to an exact source span, or return None if ambiguous/absent."""
    if not surface:
        return None
    exact = _exact_occurrences(text, surface)
    if len(exact) == 1:
        return exact[0][0], exact[0][1], False
    if len(exact) > 1:
        return None
    folded = _casefold_whitespace_occurrences(text, surface)
    if len(folded) == 1:
        start, end = folded[0]
        return start, end, text[start:end] != surface
    return None


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

def _make_client(settings: ApiSettings):
    from openai import OpenAI

    return OpenAI(api_key=settings.api_key, base_url=settings.base_url)


def _json_fence_strip(content: str) -> str:
    stripped = content.strip()
    lines = stripped.splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip().lower() in {"```json", "```"}
        and lines[-1].strip() == "```"
    ):
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _parse_json_object(content: str) -> dict[str, Any]:
    normalized = _json_fence_strip(content)
    value = json.loads(normalized)
    if not isinstance(value, dict):
        raise ValueError("root is not an object")
    return value


def _chat(
    client,
    settings: ApiSettings,
    system_prompt: str,
    user_payload: dict[str, Any],
    *,
    max_tokens: int,
    temperature: float = 0.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    # `thinking` is a DeepSeek-specific field; other OpenAI-compatible providers
    # (e.g. Alibaba Bailian) reject or ignore it, so send it only for DeepSeek.
    extra_body = {"thinking": {"type": "disabled"}} if settings.provider == "deepseek" else None
    response = client.chat.completions.create(
        model=settings.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    user_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ),
            },
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        extra_body=extra_body,
    )
    choice = response.choices[0]
    usage = {
        "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(response.usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(response.usage, "total_tokens", 0) or 0,
        "prompt_cache_hit_tokens": getattr(response.usage, "prompt_cache_hit_tokens", 0) or 0,
        "prompt_cache_miss_tokens": getattr(response.usage, "prompt_cache_miss_tokens", 0) or 0,
    }
    finish_reason = choice.finish_reason
    content = choice.message.content
    if finish_reason == "length":
        raise PipelineError("OUTPUT_TRUNCATED", f"finish_reason=length")
    if not isinstance(content, str) or not content.strip():
        raise PipelineError("EMPTY_CONTENT", f"finish_reason={finish_reason}")
    try:
        parsed = _parse_json_object(content)
    except (json.JSONDecodeError, ValueError) as error:
        raise PipelineError("INVALID_JSON", str(error)) from error
    return parsed, usage


def _is_free_tier_quota_error(error: Any) -> bool:
    """True when an API 403 signals the free-tier quota is exhausted."""
    if getattr(error, "status_code", None) != 403:
        return False
    text = f"{getattr(error, 'message', '')} {getattr(error, 'body', '')}".casefold()
    return any(
        keyword in text
        for keyword in ("freetieronly", "allocationquota", "free tier", "insufficient quota", "quota")
    )


def call_with_retry(
    client,
    settings: ApiSettings,
    system_prompt: str,
    user_payload: dict[str, Any],
    *,
    max_tokens: int,
    maximum_retries: int,
    interval_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
    report: Callable[[str], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Call the model with bounded retries for transient and contract errors."""
    from openai import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        RateLimitError,
    )

    usage_total: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    attempt = 0
    while True:
        attempt += 1
        try:
            parsed, usage = _chat(
                client, settings, system_prompt, user_payload, max_tokens=max_tokens
            )
            for key in usage_total:
                usage_total[key] += usage.get(key, 0)
            return parsed, usage_total, attempt
        except RateLimitError as error:
            if report:
                report(f"    rate limited (attempt {attempt}); backing off")
            sleep(interval_seconds * 2 ** (attempt - 1))
            if attempt > maximum_retries:
                raise PipelineError("RATE_LIMITED", str(getattr(error, "status_code", "?"))) from error
        except (APIConnectionError, APITimeoutError) as error:
            if report:
                report(f"    transport error (attempt {attempt}); retrying")
            sleep(interval_seconds)
            if attempt > maximum_retries:
                raise PipelineError("TRANSPORT_ERROR", str(error)) from error
        except APIStatusError as error:
            if _is_free_tier_quota_error(error):
                raise PipelineError(
                    "FREE_TIER_QUOTA_EXHAUSTED",
                    f"status={error.status_code}; free-tier quota exhausted",
                ) from error
            if error.status_code >= 500:
                if report:
                    report(f"    server error {error.status_code} (attempt {attempt}); retrying")
                sleep(interval_seconds)
                if attempt > maximum_retries:
                    raise PipelineError("SERVER_ERROR", str(error.status_code)) from error
            else:
                raise PipelineError("API_STATUS_ERROR", f"{error.status_code} {error.message}") from error
        except PipelineError as error:
            if error.reason_code in {"EMPTY_CONTENT", "INVALID_JSON", "OUTPUT_TRUNCATED"}:
                if report:
                    report(f"    {error.reason_code} (attempt {attempt}); retrying")
                sleep(interval_seconds)
                if attempt > maximum_retries:
                    raise
                # Attach a payload-free correction request on contract retries.
                user_payload = dict(user_payload)
                if error.reason_code == "OUTPUT_TRUNCATED":
                    instruction = (
                        "The previous output exceeded the token limit and was truncated. "
                        "Return a more concise JSON object: omit every attribute whose value "
                        "equals its default, and include only mentions you are confident about."
                    )
                else:
                    instruction = (
                        "Return the complete JSON object required by the system prompt "
                        "and no other text. Every surface_text must be a verbatim substring."
                    )
                user_payload["_correction"] = {"reason": error.reason_code, "instruction": instruction}
                continue
            raise


# ---------------------------------------------------------------------------
# JSONL checkpoint helpers
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    result: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise PipelineError("CHECKPOINT_INVALID", f"{path}:{line_number}: {error}") from error
            if not isinstance(value, dict):
                raise PipelineError("CHECKPOINT_INVALID", f"{path}:{line_number}: not object")
            result.append(value)
    return result


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _checkpoint_index(path: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in _load_jsonl(path):
        doc_id = row.get("doc_id")
        if isinstance(doc_id, str):
            index[doc_id] = row
    return index


# ---------------------------------------------------------------------------
# Mention extraction
# ---------------------------------------------------------------------------

def _validate_and_fill_mention(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    surface = raw.get("surface_text")
    if not isinstance(surface, str) or not surface.strip():
        return None
    if surface.strip().casefold() in BARE_ADJECTIVE_STOPLIST:
        return None
    entity_type = raw.get("entity_type")
    if entity_type not in ENTITY_TYPES:
        return None
    if entity_type == "anatomical_site":
        folded = surface.casefold()
        if any(word in folded for word in ANATOMICAL_SITE_STOPWORDS):
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


def _extract_mentions_for_chunk(
    client,
    settings,
    system_prompt: str,
    doc: Mapping[str, Any],
    *,
    max_tokens: int,
    maximum_retries: int,
    interval_seconds: float,
    report: Callable[[str], None] | None,
) -> tuple[list[dict[str, Any]], dict[str, int], int]:
    chunk_text_value = doc["chunk_text"]
    payload = {
        "doc_id": doc["doc_id"],
        "chunk_index": doc["chunk_index"],
        "chunk_count": doc["chunk_count"],
        "section_text_sha256": sha256_text(chunk_text_value),
        "section_text": chunk_text_value,
    }
    parsed, usage, attempts = call_with_retry(
        client,
        settings,
        system_prompt,
        payload,
        max_tokens=max_tokens,
        maximum_retries=maximum_retries,
        interval_seconds=interval_seconds,
        report=report,
    )
    raw_mentions = parsed.get("mentions")
    if not isinstance(raw_mentions, list):
        raise PipelineError("MENTIONS_NOT_LIST", type(raw_mentions).__name__)
    grounded: list[dict[str, Any]] = []
    for raw in raw_mentions:
        if not isinstance(raw, dict):
            continue
        mention = _validate_and_fill_mention(raw)
        if mention is None:
            continue
        located = ground_surface(chunk_text_value, mention["surface_text"])
        if located is None:
            continue
        start, end, rewritten = located
        if rewritten:
            mention["surface_text"] = chunk_text_value[start:end]
        mention["chunk_span_start"] = start
        mention["chunk_span_end"] = end
        mention["document_span_start"] = doc["chunk_start"] + start
        mention["document_span_end"] = doc["chunk_start"] + end
        grounded.append(mention)
    return grounded, usage, attempts


def _merge_mentions(chunk_mentions: Sequence[Sequence[dict[str, Any]]]) -> list[dict[str, Any]]:
    seen: set[tuple[int, int, str]] = set()
    merged: list[dict[str, Any]] = []
    for mentions in chunk_mentions:
        for mention in mentions:
            key = (
                mention["document_span_start"],
                mention["document_span_end"],
                mention["entity_type"],
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(mention)
    merged.sort(key=lambda mention: (mention["document_span_start"], mention["document_span_end"]))
    for index, mention in enumerate(merged, start=1):
        mention["local_id"] = f"m{index}"
    return merged


class _TokenBucket:
    """Thread-safe token bucket capping the GLOBAL request rate.

    ``burst`` tokens are available immediately (so ``burst`` workers can fire
    concurrently); refills at ``requests_per_minute`` thereafter. Used only when
    ``workers > 1`` so concurrent workers collectively respect the configured
    rate instead of the sequential ``time.sleep`` pacing.
    """

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


def run_mentions(
    output_directory: Path,
    *,
    env_file: Path | None,
    mention_prompt: Path,
    max_docs: int | None = None,
    sample_per_source: int | None = None,
    source_tables: list[str] | None = None,
    max_tokens: int = DEFAULT_MENTION_MAX_TOKENS,
    requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
    maximum_retries: int = DEFAULT_MAX_RETRIES,
    retry_failed: bool = False,
    workers: int = 1,
    report: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    grouped = group_documents(load_documents(output_directory))
    settings = ApiSettings.resolve(env_file)
    system_prompt = Path(mention_prompt).read_text(encoding="utf-8")
    client = _make_client(settings)

    results_path = Path(output_directory) / "mention_results.jsonl"
    failures_path = Path(output_directory) / "mention_failures.jsonl"
    done = _checkpoint_index(results_path)
    failed = _checkpoint_index(failures_path)

    candidate_docs = list(grouped.keys())
    candidate_docs.sort()
    if source_tables is not None:
        wanted = set(source_tables)
        candidate_docs = [
            doc_id for doc_id in candidate_docs
            if grouped[doc_id][0]["source_table"] in wanted
        ]
    if sample_per_source is not None:
        by_source: dict[str, list[str]] = {}
        for doc_id in candidate_docs:
            if doc_id in done:
                continue
            by_source.setdefault(grouped[doc_id][0]["source_table"], []).append(doc_id)
        selected: list[str] = []
        for source in sorted(by_source):
            selected.extend(by_source[source][:sample_per_source])
        candidate_docs = sorted(selected)
    elif max_docs is not None:
        candidate_docs = [doc_id for doc_id in candidate_docs if doc_id not in done][:max_docs]

    if retry_failed:
        pending = [doc_id for doc_id in candidate_docs if doc_id in failed and doc_id not in done]
    else:
        pending = [doc_id for doc_id in candidate_docs if doc_id not in done]

    interval = 60.0 / max(1, requests_per_minute)
    usage_total: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    successful = 0
    failed_count = 0
    model_calls = 0
    stop_reason: str | None = None
    limiter = _TokenBucket(requests_per_minute, burst=workers) if workers > 1 else None

    if report:
        report(
            f"[mentions] documents={len(grouped)} | pending={len(pending)} | "
            f"workers={workers} | rate={requests_per_minute}/min | model={settings.model}"
        )

    def process_doc(doc_id: str) -> tuple[str, Any]:
        """Process one doc (all its chunks sequentially); returns (kind, payload)."""
        chunks = grouped[doc_id]
        chunk_mentions: list[list[dict[str, Any]]] = []
        doc_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        doc_model_calls = 0
        for chunk in chunks:
            if limiter is not None:
                limiter.acquire()
            try:
                mentions, usage, attempts = _extract_mentions_for_chunk(
                    client,
                    settings,
                    system_prompt,
                    chunk,
                    max_tokens=max_tokens,
                    maximum_retries=maximum_retries,
                    interval_seconds=interval,
                    report=None,
                )
            except PipelineError as error:
                if error.reason_code == "FREE_TIER_QUOTA_EXHAUSTED":
                    return ("stop", None)
                return ("fail", {
                    "doc_id": doc_id,
                    "source_table": chunks[0]["source_table"],
                    "reason_code": error.reason_code,
                    "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                })
            chunk_mentions.append(mentions)
            doc_model_calls += attempts
            for key in doc_usage:
                doc_usage[key] += usage.get(key, 0)
            if report:
                report(
                    f"  doc {doc_id[:20]} chunk {chunk['chunk_index']+1}/{chunk['chunk_count']} "
                    f"-> {len(mentions)} mentions"
                )
        merged = _merge_mentions(chunk_mentions)
        row = {
            "schema_version": PIPELINE_VERSION,
            "doc_id": doc_id,
            "subject_id": chunks[0]["subject_id"],
            "hadm_id": chunks[0]["hadm_id"],
            "source_table": chunks[0]["source_table"],
            "source_text_field": chunks[0]["source_text_field"],
            "source_text_kind": chunks[0]["source_text_kind"],
            "source_text_sha256": chunks[0]["source_text_sha256"],
            "event_time": chunks[0]["event_time"],
            "extractor_name": f"{settings.provider}/{settings.model}",
            "extractor_version": settings.model_version,
            "mentions": merged,
            "usage": doc_usage,
            "model_calls": doc_model_calls,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        return ("ok", row)

    def handle(kind: str, payload: Any) -> None:
        """Single-threaded: append checkpoints and update counters."""
        nonlocal successful, failed_count, model_calls, stop_reason
        if kind == "stop":
            stop_reason = "free_tier_quota_exhausted"
            return
        if kind == "fail":
            failed_count += 1
            _append_jsonl(failures_path, payload)
            if report:
                report(f"  doc {payload['doc_id'][:20]} FAILED ({payload['reason_code']})")
            return
        row = payload
        _append_jsonl(results_path, row)
        successful += 1
        model_calls += row["model_calls"]
        for key in usage_total:
            usage_total[key] += row["usage"].get(key, 0)
        if report:
            report(f"  doc {row['doc_id'][:20]} OK -> {len(row['mentions'])} grounded mentions")

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(process_doc, doc_id) for doc_id in pending]
            for future in as_completed(futures):
                kind, payload = future.result()
                handle(kind, payload)
    else:
        for doc_id in pending:
            kind, payload = process_doc(doc_id)
            handle(kind, payload)
            if stop_reason:
                if report:
                    report("[API] 免费额度已用尽，批次停止；已完成的 checkpoint 保持有效")
                break

    return {
        "schema_version": PIPELINE_VERSION,
        "stage": "mentions",
        "documents": len(grouped),
        "pending": len(pending),
        "successful": successful,
        "failed": failed_count,
        "model_calls": model_calls,
        "stop_reason": stop_reason,
        "usage": usage_total,
        "checkpoint": str(results_path),
        "failures": str(failures_path),
    }


# ---------------------------------------------------------------------------
# Relation extraction
# ---------------------------------------------------------------------------

def _validate_relation(raw: Mapping[str, Any], valid_ids: set[str]) -> dict[str, Any] | None:
    source = raw.get("source_mention_id")
    target = raw.get("target_mention_id")
    relation_type = raw.get("relation_type")
    if source not in valid_ids or target not in valid_ids:
        return None
    if source == target:
        return None
    if relation_type not in RELATION_TYPES:
        return None
    return {"source_mention_id": source, "target_mention_id": target, "relation_type": relation_type}


def _ground_relation(
    raw: Mapping[str, Any],
    valid_ids: set[str],
    mention_by_local: Mapping[str, dict[str, Any]],
    doc: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Validate a raw model relation and ground its evidence span, or return None."""
    relation = _validate_relation(raw, valid_ids)
    if relation is None:
        return None
    source = mention_by_local[relation["source_mention_id"]]
    target = mention_by_local[relation["target_mention_id"]]
    # Deterministic endpoint type conformance.
    rules = RELATION_TYPE_RULES.get(relation["relation_type"], {})
    src_req = rules.get("source")
    tgt_req = rules.get("target")
    if src_req and source["entity_type"] != src_req:
        return None
    if tgt_req and target["entity_type"] != tgt_req:
        return None
    # compared_with compares an entity against a historical/reference entity
    # of the same kind, never a study or a list of unrelated co-mentions.
    if relation["relation_type"] == "compared_with" and source["entity_type"] != target["entity_type"]:
        return None
    # Negated (absent) endpoints do not support affirmative relations.
    if source["assertion"] == "absent" or target["assertion"] == "absent":
        return None
    # Drop self-referential located_at where the finding already contains the site.
    if relation["relation_type"] == "located_at" and target["surface_text"] in source["surface_text"]:
        return None
    source_start = source["document_span_start"] - doc["chunk_start"]
    source_end = source["document_span_end"] - doc["chunk_start"]
    target_start = target["document_span_start"] - doc["chunk_start"]
    target_end = target["document_span_end"] - doc["chunk_start"]
    start = min(source_start, target_start)
    end = max(source_end, target_end)
    # Drop cross-paragraph false positives by evidence length.
    if (end - start) > MAX_EVIDENCE_CHARS:
        return None
    evidence_text = doc["chunk_text"][start:end]
    # Drop cross-section relations (blank line inside the evidence).
    if "\n\n" in evidence_text:
        return None
    # Drop relations whose wording does not carry the relation's lexical cue.
    if not _evidence_matches_relation(relation["relation_type"], evidence_text):
        return None
    relation["evidence_text"] = evidence_text
    relation["evidence_start"] = doc["chunk_start"] + start
    relation["evidence_end"] = doc["chunk_start"] + end
    return relation


def _extract_relations_for_chunk(
    client,
    settings,
    system_prompt: str,
    doc: Mapping[str, Any],
    mentions: Sequence[dict[str, Any]],
    *,
    max_tokens: int,
    maximum_retries: int,
    interval_seconds: float,
    report: Callable[[str], None] | None,
) -> tuple[list[dict[str, Any]], dict[str, int], int]:
    chunk_mentions = [
        mention
        for mention in mentions
        if doc["chunk_start"] <= mention["document_span_start"]
        and mention["document_span_end"] <= doc["chunk_end"]
    ]
    chunk_mentions.sort(key=lambda mention: mention["local_id"])
    if len(chunk_mentions) < 2:
        return [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, 0

    mention_by_local = {mention["local_id"]: mention for mention in chunk_mentions}
    windows = [
        chunk_mentions[index : index + MAX_RELATION_MENTIONS_PER_CALL]
        for index in range(0, len(chunk_mentions), MAX_RELATION_MENTIONS_PER_CALL)
    ]
    relations: list[dict[str, Any]] = []
    usage_total: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    attempts_total = 0

    for window in windows:
        valid_ids = {mention["local_id"] for mention in window}
        if len(valid_ids) < 2:
            continue
        payload = {
            "doc_id": doc["doc_id"],
            "chunk_index": doc["chunk_index"],
            "section_text": doc["chunk_text"],
            "mentions": [
                {
                    "local_id": mention["local_id"],
                    "surface_text": mention["surface_text"],
                    "entity_type": mention["entity_type"],
                    "assertion": mention["assertion"],
                }
                for mention in window
            ],
        }
        parsed, usage, attempts = call_with_retry(
            client,
            settings,
            system_prompt,
            payload,
            max_tokens=max_tokens,
            maximum_retries=maximum_retries,
            interval_seconds=interval_seconds,
            report=report,
        )
        attempts_total += attempts
        for key in usage_total:
            usage_total[key] += usage.get(key, 0)
        raw_relations = parsed.get("relations")
        if not isinstance(raw_relations, list):
            raise PipelineError("RELATIONS_NOT_LIST", type(raw_relations).__name__)
        for raw in raw_relations:
            if not isinstance(raw, dict):
                continue
            relation = _ground_relation(raw, valid_ids, mention_by_local, doc)
            if relation is not None:
                relations.append(relation)

    # Deduplicate across windows.
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for relation in relations:
        key = (relation["source_mention_id"], relation["target_mention_id"], relation["relation_type"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(relation)
    return deduped, usage_total, attempts_total


def run_relations(
    output_directory: Path,
    *,
    env_file: Path | None,
    relation_prompt: Path,
    max_docs: int | None = None,
    max_tokens: int = DEFAULT_RELATION_MAX_TOKENS,
    requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
    maximum_retries: int = DEFAULT_MAX_RETRIES,
    retry_failed: bool = False,
    report: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    grouped = group_documents(load_documents(output_directory))
    mention_index = _checkpoint_index(Path(output_directory) / "mention_results.jsonl")
    settings = ApiSettings.resolve(env_file)
    system_prompt = Path(relation_prompt).read_text(encoding="utf-8")
    client = _make_client(settings)

    results_path = Path(output_directory) / "relation_results.jsonl"
    failures_path = Path(output_directory) / "relation_failures.jsonl"
    done = _checkpoint_index(results_path)
    failed = _checkpoint_index(failures_path)

    candidate_docs = [doc_id for doc_id in mention_index if len(mention_index[doc_id]["mentions"]) >= 2]
    candidate_docs.sort()
    if max_docs is not None:
        candidate_docs = [doc_id for doc_id in candidate_docs if doc_id not in done][:max_docs]

    if retry_failed:
        pending = [doc_id for doc_id in candidate_docs if doc_id in failed and doc_id not in done]
    else:
        pending = [doc_id for doc_id in candidate_docs if doc_id not in done]

    interval = 60.0 / max(1, requests_per_minute)
    usage_total: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    successful = 0
    failed_count = 0
    model_calls = 0
    stop_reason: str | None = None

    if report:
        report(
            f"[relations] eligible={len(candidate_docs)} | pending={len(pending)} | "
            f"rate={requests_per_minute}/min | model={settings.model}"
        )

    for position, doc_id in enumerate(pending, start=1):
        chunks = grouped[doc_id]
        mentions = mention_index[doc_id]["mentions"]
        relations: list[dict[str, Any]] = []
        doc_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        doc_failed = False
        failure_reason: str | None = None
        for chunk in chunks:
            try:
                chunk_relations, usage, attempts = _extract_relations_for_chunk(
                    client,
                    settings,
                    system_prompt,
                    chunk,
                    mentions,
                    max_tokens=max_tokens,
                    maximum_retries=maximum_retries,
                    interval_seconds=interval,
                    report=None,
                )
            except PipelineError as error:
                if error.reason_code == "FREE_TIER_QUOTA_EXHAUSTED":
                    stop_reason = "free_tier_quota_exhausted"
                    break
                doc_failed = True
                failure_reason = error.reason_code
                break
            relations.extend(chunk_relations)
            model_calls += attempts
            for key in usage_total:
                usage_total[key] += usage.get(key, 0)
            for key in doc_usage:
                doc_usage[key] += usage.get(key, 0)
            time.sleep(interval)

        if stop_reason:
            if report:
                report("[API] 免费额度已用尽，批次停止；已完成的 checkpoint 保持有效")
            break
        if doc_failed:
            failed_count += 1
            _append_jsonl(
                failures_path,
                {
                    "doc_id": doc_id,
                    "source_table": chunks[0]["source_table"],
                    "reason_code": failure_reason,
                    "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                },
            )
            if report:
                report(f"  doc {doc_id[:20]} FAILED ({failure_reason})")
            continue

        # Deduplicate relations (evidence spans were attached per chunk).
        seen: set[tuple[str, str, str]] = set()
        final_relations: list[dict[str, Any]] = []
        for relation in relations:
            key = (relation["source_mention_id"], relation["target_mention_id"], relation["relation_type"])
            if key in seen:
                continue
            seen.add(key)
            final_relations.append(relation)
        final_relations.sort(key=lambda relation: (relation["source_mention_id"], relation["target_mention_id"]))

        row = {
            "schema_version": PIPELINE_VERSION,
            "doc_id": doc_id,
            "source_table": chunks[0]["source_table"],
            "extractor_name": f"{settings.provider}/{settings.model}",
            "extractor_version": settings.model_version,
            "relations": final_relations,
            "usage": doc_usage,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        _append_jsonl(results_path, row)
        successful += 1
        if report:
            report(f"  doc {doc_id[:20]} OK -> {len(final_relations)} relations")

    return {
        "schema_version": PIPELINE_VERSION,
        "stage": "relations",
        "eligible": len(candidate_docs),
        "pending": len(pending),
        "successful": successful,
        "failed": failed_count,
        "model_calls": model_calls,
        "stop_reason": stop_reason,
        "usage": usage_total,
        "checkpoint": str(results_path),
        "failures": str(failures_path),
    }


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

ENTITY_ARROW_SCHEMA = pa.schema(
    [
        ("mention_id", pa.string()),
        ("doc_id", pa.string()),
        ("local_id", pa.string()),
        ("subject_id", pa.string()),
        ("hadm_id", pa.string()),
        ("source_table", pa.string()),
        ("source_text_field", pa.string()),
        ("source_text_kind", pa.string()),
        ("surface_text", pa.string()),
        ("document_span_start", pa.int64()),
        ("document_span_end", pa.int64()),
        ("entity_type", pa.string()),
        ("assertion", pa.string()),
        ("temporality", pa.string()),
        ("experiencer", pa.string()),
        ("laterality", pa.string()),
        ("severity", pa.string()),
        ("trend", pa.string()),
        ("normalization_status", pa.string()),
        ("concept_id", pa.string()),
        ("preferred_name", pa.string()),
        ("terminology", pa.string()),
        ("event_time", pa.string()),
        ("extraction_method", pa.string()),
        ("extractor_name", pa.string()),
        ("extractor_version", pa.string()),
        ("source_text_sha256", pa.string()),
        ("review_status", pa.string()),
        ("quality_flags", pa.list_(pa.string())),
    ],
    metadata={b"schema": "entity-mention-v2/1.0.0".encode("ascii")},
)

RELATION_ARROW_SCHEMA = pa.schema(
    [
        ("relation_id", pa.string()),
        ("doc_id", pa.string()),
        ("subject_id", pa.string()),
        ("hadm_id", pa.string()),
        ("source_table", pa.string()),
        ("source_mention_id", pa.string()),
        ("target_mention_id", pa.string()),
        ("relation_type", pa.string()),
        ("evidence_text", pa.string()),
        ("evidence_start", pa.int64()),
        ("evidence_end", pa.int64()),
        ("relation_basis", pa.string()),
        ("extraction_method", pa.string()),
        ("extractor_name", pa.string()),
        ("extractor_version", pa.string()),
        ("source_text_sha256", pa.string()),
        ("review_status", pa.string()),
        ("quality_flags", pa.list_(pa.string())),
    ],
    metadata={b"schema": "text-relation-v2/1.0.0".encode("ascii")},
)


def compile_sidecars(output_directory: Path) -> dict[str, Any]:
    grouped = group_documents(load_documents(output_directory))
    mention_index = _checkpoint_index(Path(output_directory) / "mention_results.jsonl")
    relation_index = _checkpoint_index(Path(output_directory) / "relation_results.jsonl")

    entity_rows: list[dict[str, Any]] = []
    for doc_id in sorted(mention_index):
        row = mention_index[doc_id]
        for mention in row["mentions"]:
            entity_rows.append(
                {
                    "mention_id": f"{doc_id}:{mention['local_id']}",
                    "doc_id": doc_id,
                    "local_id": mention["local_id"],
                    "subject_id": row.get("subject_id"),
                    "hadm_id": row.get("hadm_id"),
                    "source_table": row.get("source_table"),
                    "source_text_field": row.get("source_text_field"),
                    "source_text_kind": row.get("source_text_kind"),
                    "surface_text": mention["surface_text"],
                    "document_span_start": mention["document_span_start"],
                    "document_span_end": mention["document_span_end"],
                    "entity_type": mention["entity_type"],
                    "assertion": mention["assertion"],
                    "temporality": mention["temporality"],
                    "experiencer": mention["experiencer"],
                    "laterality": mention["laterality"],
                    "severity": mention["severity"],
                    "trend": mention["trend"],
                    "normalization_status": "unattempted",
                    "concept_id": None,
                    "preferred_name": None,
                    "terminology": None,
                    "event_time": row.get("event_time"),
                    "extraction_method": "openai_compatible_api",
                    "extractor_name": row.get("extractor_name"),
                    "extractor_version": row.get("extractor_version"),
                    "source_text_sha256": row.get("source_text_sha256"),
                    "review_status": "unreviewed_model_output",
                    "quality_flags": [],
                }
            )

    relation_rows: list[dict[str, Any]] = []
    for doc_id in sorted(relation_index):
        row = relation_index[doc_id]
        subject_id = mention_index[doc_id].get("subject_id") if doc_id in mention_index else None
        hadm_id = mention_index[doc_id].get("hadm_id") if doc_id in mention_index else None
        sha = mention_index[doc_id].get("source_text_sha256") if doc_id in mention_index else None
        for relation in row["relations"]:
            relation_rows.append(
                {
                    "relation_id": f"{doc_id}:{relation['source_mention_id']}:{relation['target_mention_id']}:{relation['relation_type']}",
                    "doc_id": doc_id,
                    "subject_id": subject_id,
                    "hadm_id": hadm_id,
                    "source_table": row.get("source_table"),
                    "source_mention_id": f"{doc_id}:{relation['source_mention_id']}",
                    "target_mention_id": f"{doc_id}:{relation['target_mention_id']}",
                    "relation_type": relation["relation_type"],
                    "evidence_text": relation.get("evidence_text"),
                    "evidence_start": relation.get("evidence_start"),
                    "evidence_end": relation.get("evidence_end"),
                    "relation_basis": "text_explicit",
                    "extraction_method": "openai_compatible_api",
                    "extractor_name": row.get("extractor_name"),
                    "extractor_version": row.get("extractor_version"),
                    "source_text_sha256": sha,
                    "review_status": "unreviewed_model_output",
                    "quality_flags": [],
                }
            )

    sidecar_dir = Path(output_directory) / "sidecars"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    entity_path = sidecar_dir / "entity_mentions.parquet"
    relation_path = sidecar_dir / "text_relations.parquet"
    pq.write_table(pa.Table.from_pylist(entity_rows, schema=ENTITY_ARROW_SCHEMA), entity_path)
    pq.write_table(pa.Table.from_pylist(relation_rows, schema=RELATION_ARROW_SCHEMA), relation_path)

    summary = {
        "schema_version": PIPELINE_VERSION,
        "kind": "compile",
        "documents": len(grouped),
        "documents_with_mentions": len(mention_index),
        "documents_with_relations": len(relation_index),
        "entity_mentions": len(entity_rows),
        "text_relations": len(relation_rows),
        "entity_path": str(entity_path),
        "relation_path": str(relation_path),
        "compiled_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (Path(output_directory) / "compile_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def status(output_directory: Path) -> dict[str, Any]:
    grouped = group_documents(load_documents(output_directory))
    mention_index = _checkpoint_index(Path(output_directory) / "mention_results.jsonl")
    relation_index = _checkpoint_index(Path(output_directory) / "relation_results.jsonl")
    mention_failed = _checkpoint_index(Path(output_directory) / "mention_failures.jsonl")
    relation_failed = _checkpoint_index(Path(output_directory) / "relation_failures.jsonl")
    # Unresolved failures only: a doc that later succeeded on retry is not a failure.
    mention_unresolved = len(set(mention_failed) - set(mention_index))
    relation_unresolved = len(set(relation_failed) - set(relation_index))
    mention_tokens = sum(
        row.get("usage", {}).get("total_tokens", 0) for row in mention_index.values()
    )
    relation_tokens = sum(
        row.get("usage", {}).get("total_tokens", 0) for row in relation_index.values()
    )
    return {
        "documents": len(grouped),
        "mentions_done": len(mention_index),
        "mentions_failed": mention_unresolved,
        "relations_done": len(relation_index),
        "relations_failed": relation_unresolved,
        "mention_tokens": mention_tokens,
        "relation_tokens": relation_tokens,
        "total_tokens": mention_tokens + relation_tokens,
    }
