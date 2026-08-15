"""Deterministic overlapping chunks for section-level mention extraction."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence


class TextChunkingError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


@dataclass(frozen=True)
class TextChunkingPolicy:
    enabled: bool
    maximum_input_characters: int
    target_core_characters: int
    overlap_characters: int
    minimum_core_characters: int
    maximum_split_depth: int
    truncation_output_token_multiplier: float
    maximum_output_tokens: int

    def audit_metadata(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "maximum_input_characters": self.maximum_input_characters,
            "target_core_characters": self.target_core_characters,
            "overlap_characters": self.overlap_characters,
            "minimum_core_characters": self.minimum_core_characters,
            "maximum_split_depth": self.maximum_split_depth,
            "truncation_output_token_multiplier": (
                self.truncation_output_token_multiplier
            ),
            "maximum_output_tokens": self.maximum_output_tokens,
        }


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    context_start: int
    context_end: int
    core_start: int
    core_end: int
    depth: int

    @property
    def context_character_count(self) -> int:
        return self.context_end - self.context_start

    @property
    def core_character_count(self) -> int:
        return self.core_end - self.core_start

    def audit_metadata(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "context_start": self.context_start,
            "context_end": self.context_end,
            "core_start": self.core_start,
            "core_end": self.core_end,
            "depth": self.depth,
            "context_character_count": self.context_character_count,
            "core_character_count": self.core_character_count,
        }


def load_text_chunking_policy(config: Mapping[str, Any]) -> TextChunkingPolicy:
    raw = config.get("mention_chunking")
    if not isinstance(raw, Mapping):
        raise TextChunkingError(
            "TEXT_CHUNKING_CONFIG_MISSING", "mention_chunking"
        )
    expected = {
        "enabled",
        "maximum_input_characters",
        "target_core_characters",
        "overlap_characters",
        "minimum_core_characters",
        "maximum_split_depth",
        "truncation_output_token_multiplier",
        "maximum_output_tokens",
    }
    unknown = set(raw) - expected
    missing = expected - set(raw)
    if unknown:
        raise TextChunkingError(
            "TEXT_CHUNKING_CONFIG_FIELD_UNKNOWN", ",".join(sorted(unknown))
        )
    if missing:
        raise TextChunkingError(
            "TEXT_CHUNKING_CONFIG_FIELD_MISSING", ",".join(sorted(missing))
        )
    enabled = raw["enabled"]
    integers = {
        key: raw[key]
        for key in (
            "maximum_input_characters",
            "target_core_characters",
            "overlap_characters",
            "minimum_core_characters",
            "maximum_split_depth",
            "maximum_output_tokens",
        )
    }
    if not isinstance(enabled, bool):
        raise TextChunkingError("TEXT_CHUNKING_CONFIG_INVALID", "enabled")
    if any(
        not isinstance(value, int) or isinstance(value, bool)
        for value in integers.values()
    ):
        raise TextChunkingError("TEXT_CHUNKING_CONFIG_INVALID", "integer field")
    if any(value <= 0 for value in integers.values()):
        raise TextChunkingError("TEXT_CHUNKING_CONFIG_INVALID", "positive integer")
    multiplier = raw["truncation_output_token_multiplier"]
    if (
        not isinstance(multiplier, (int, float))
        or isinstance(multiplier, bool)
        or float(multiplier) <= 1.0
    ):
        raise TextChunkingError(
            "TEXT_CHUNKING_CONFIG_INVALID",
            "truncation_output_token_multiplier",
        )
    if integers["target_core_characters"] > integers["maximum_input_characters"]:
        raise TextChunkingError(
            "TEXT_CHUNKING_CONFIG_INVALID",
            "target_core_characters exceeds maximum_input_characters",
        )
    if integers["overlap_characters"] >= integers["target_core_characters"]:
        raise TextChunkingError(
            "TEXT_CHUNKING_CONFIG_INVALID",
            "overlap_characters must be smaller than target_core_characters",
        )
    if integers["minimum_core_characters"] * 2 > integers[
        "target_core_characters"
    ]:
        raise TextChunkingError(
            "TEXT_CHUNKING_CONFIG_INVALID",
            "minimum_core_characters is too large",
        )
    return TextChunkingPolicy(
        enabled=enabled,
        maximum_input_characters=integers["maximum_input_characters"],
        target_core_characters=integers["target_core_characters"],
        overlap_characters=integers["overlap_characters"],
        minimum_core_characters=integers["minimum_core_characters"],
        maximum_split_depth=integers["maximum_split_depth"],
        truncation_output_token_multiplier=float(multiplier),
        maximum_output_tokens=integers["maximum_output_tokens"],
    )


def _chunk_id(
    text_identity: str,
    context_start: int,
    context_end: int,
    core_start: int,
    core_end: int,
    depth: int,
) -> str:
    material = (
        f"{text_identity}:{context_start}:{context_end}:"
        f"{core_start}:{core_end}:{depth}"
    )
    digest = hashlib.sha256(material.encode("ascii")).hexdigest()[:16]
    return f"chunk:{digest}"


def _text_identity(text: str, namespace: str) -> str:
    text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return hashlib.sha256(
        (namespace + "\x00" + text_sha256).encode("utf-8")
    ).hexdigest()


def _preferred_boundary(
    text: str,
    *,
    lower_bound: int,
    desired: int,
    upper_bound: int,
) -> int:
    if desired >= upper_bound:
        return upper_bound
    search_lower = max(lower_bound, desired - max(200, (desired - lower_bound) // 2))
    for delimiter in ("\n\n", "\r\n\r\n", "\n", ". ", "; ", ", ", " "):
        position = text.rfind(delimiter, search_lower, desired + 1)
        if position >= search_lower:
            boundary = position + len(delimiter)
            if lower_bound <= boundary <= upper_bound:
                return boundary
    return desired


def _make_chunk(
    text_length: int,
    *,
    text_identity: str,
    core_start: int,
    core_end: int,
    overlap: int,
    depth: int,
) -> TextChunk:
    context_start = max(0, core_start - overlap)
    context_end = min(text_length, core_end + overlap)
    return TextChunk(
        chunk_id=_chunk_id(
            text_identity,
            context_start,
            context_end,
            core_start,
            core_end,
            depth,
        ),
        context_start=context_start,
        context_end=context_end,
        core_start=core_start,
        core_end=core_end,
        depth=depth,
    )


def plan_initial_chunks(
    text: str,
    policy: TextChunkingPolicy,
    *,
    namespace: str = "",
) -> list[TextChunk]:
    length = len(text)
    text_identity = _text_identity(text, namespace)
    if not policy.enabled or length <= policy.maximum_input_characters:
        return [
            _make_chunk(
                length,
                text_identity=text_identity,
                core_start=0,
                core_end=length,
                overlap=0,
                depth=0,
            )
        ]
    core_ranges: list[tuple[int, int]] = []
    start = 0
    while start < length:
        remaining = length - start
        if remaining <= policy.target_core_characters:
            core_ranges.append((start, length))
            break
        desired = start + policy.target_core_characters
        boundary = _preferred_boundary(
            text,
            lower_bound=start + policy.minimum_core_characters,
            desired=desired,
            upper_bound=length,
        )
        if length - boundary < policy.minimum_core_characters:
            boundary = length
        core_ranges.append((start, boundary))
        start = boundary
    return [
        _make_chunk(
            length,
            text_identity=text_identity,
            core_start=core_start,
            core_end=core_end,
            overlap=policy.overlap_characters,
            depth=0,
        )
        for core_start, core_end in core_ranges
    ]


def whole_text_chunk(text: str, *, namespace: str = "") -> TextChunk:
    text_identity = _text_identity(text, namespace)
    return _make_chunk(
        len(text),
        text_identity=text_identity,
        core_start=0,
        core_end=len(text),
        overlap=0,
        depth=0,
    )


def split_chunk_after_truncation(
    text: str,
    chunk: TextChunk,
    policy: TextChunkingPolicy,
    *,
    namespace: str = "",
) -> list[TextChunk]:
    if chunk.depth >= policy.maximum_split_depth:
        return []
    if chunk.core_character_count < policy.minimum_core_characters * 2:
        return []
    desired = chunk.core_start + chunk.core_character_count // 2
    boundary = _preferred_boundary(
        text,
        lower_bound=chunk.core_start + policy.minimum_core_characters,
        desired=desired,
        upper_bound=chunk.core_end - policy.minimum_core_characters,
    )
    if not (
        chunk.core_start + policy.minimum_core_characters
        <= boundary
        <= chunk.core_end - policy.minimum_core_characters
    ):
        boundary = desired
    if boundary <= chunk.core_start or boundary >= chunk.core_end:
        return []
    depth = chunk.depth + 1
    text_identity = _text_identity(text, namespace)
    return [
        _make_chunk(
            len(text),
            text_identity=text_identity,
            core_start=chunk.core_start,
            core_end=boundary,
            overlap=policy.overlap_characters,
            depth=depth,
        ),
        _make_chunk(
            len(text),
            text_identity=text_identity,
            core_start=boundary,
            core_end=chunk.core_end,
            overlap=policy.overlap_characters,
            depth=depth,
        ),
    ]


def build_chunk_request(
    request: Mapping[str, Any], text: str, chunk: TextChunk
) -> dict[str, Any]:
    chunk_text = text[chunk.context_start : chunk.context_end]
    result = dict(request)
    result["section_text"] = chunk_text
    result["section_text_sha256"] = hashlib.sha256(
        chunk_text.encode("utf-8")
    ).hexdigest()
    return result


def merge_chunk_annotations(
    parent_request: Mapping[str, Any],
    chunk_results: Sequence[
        tuple[TextChunk, Mapping[str, Any], Sequence[Mapping[str, Any]]]
    ],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Map child-local mentions to parent offsets and apply core ownership."""

    retained: list[
        tuple[TextChunk, dict[str, Any], list[dict[str, Any]]]
    ] = []
    chunk_summaries: list[dict[str, Any]] = []
    for chunk, annotation, repairs in chunk_results:
        retained_ids: set[str] = set()
        retained_mentions: list[dict[str, Any]] = []
        for raw_mention in annotation["mentions"]:
            mention = deepcopy(dict(raw_mention))
            global_start = chunk.context_start + mention["section_span_start"]
            global_end = chunk.context_start + mention["section_span_end"]
            if not (chunk.core_start <= global_start < chunk.core_end):
                continue
            mention["section_span_start"] = global_start
            mention["section_span_end"] = global_end
            retained_ids.add(mention["local_id"])
            retained_mentions.append(mention)
        retained_repairs = [
            deepcopy(dict(repair))
            for repair in repairs
            if repair.get("item_kind") == "mention"
            and repair.get("local_id") in retained_ids
        ]
        retained.append((chunk, {"mentions": retained_mentions}, retained_repairs))
        chunk_summaries.append(
            {
                **chunk.audit_metadata(),
                "model_mention_count": len(annotation["mentions"]),
                "retained_mention_count": len(retained_mentions),
                "discarded_overlap_mention_count": (
                    len(annotation["mentions"]) - len(retained_mentions)
                ),
                "span_repair_count": len(repairs),
            }
        )

    candidates: list[tuple[TextChunk, dict[str, Any], list[dict[str, Any]]]] = []
    for chunk, annotation, repairs in retained:
        repairs_by_id: dict[str, list[dict[str, Any]]] = {}
        for repair in repairs:
            repairs_by_id.setdefault(str(repair["local_id"]), []).append(repair)
        for mention in annotation["mentions"]:
            candidates.append(
                (chunk, mention, repairs_by_id.get(str(mention["local_id"]), []))
            )
    candidates.sort(
        key=lambda value: (
            value[1]["section_span_start"],
            value[1]["section_span_end"],
            value[1]["entity_type"],
            value[0].chunk_id,
            value[1]["local_id"],
        )
    )
    merged_mentions: list[dict[str, Any]] = []
    merged_repairs: list[dict[str, Any]] = []
    exact_keys: set[tuple[int, int, str]] = set()
    for chunk, mention, repairs in candidates:
        exact_key = (
            mention["section_span_start"],
            mention["section_span_end"],
            mention["entity_type"],
        )
        if exact_key in exact_keys:
            continue
        exact_keys.add(exact_key)
        old_local_id = mention["local_id"]
        new_local_id = f"m{len(merged_mentions) + 1}"
        mention["local_id"] = new_local_id
        merged_mentions.append(mention)
        for repair in repairs:
            converted = dict(repair)
            converted["local_id"] = new_local_id
            for field in (
                "original_start",
                "original_end",
                "grounded_start",
                "grounded_end",
            ):
                converted[field] = chunk.context_start + int(converted[field])
            converted["chunk_id"] = chunk.chunk_id
            converted["chunk_local_id"] = old_local_id
            merged_repairs.append(converted)

    annotation = {
        "schema_version": parent_request["response_schema_version"],
        "manifest_row_id": parent_request["manifest_row_id"],
        "document_id": parent_request["document_id"],
        "section_id": parent_request["section_id"],
        "section_text_sha256": parent_request["section_text_sha256"],
        "mentions": merged_mentions,
        "relations": [],
    }
    return annotation, merged_repairs, chunk_summaries
