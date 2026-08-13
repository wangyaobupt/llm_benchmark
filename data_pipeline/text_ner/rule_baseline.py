"""Conservative non-model baseline for deterministic method-pipeline tests."""

from __future__ import annotations

import re
from typing import Any

from .annotation_contracts import SECTION_ANNOTATION_SCHEMA_VERSION
from .annotation_validation import SectionAnnotationValidator


MEASUREMENT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:\d+(?:\.\d+)?|\.\d+)\s*"
    r"(?:mmHg|mm|cm|mg|mcg|g|kg|mL|ml|L|bpm|%)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
TEMPORAL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:today|tonight|currently|now)\b", re.IGNORECASE), "current"),
    (
        re.compile(r"\b(?:yesterday|previously|prior|remote)\b", re.IGNORECASE),
        "historical",
    ),
    (
        re.compile(r"\b(?:tomorrow|subsequently|next\s+(?:day|week|month))\b", re.IGNORECASE),
        "future_planned",
    ),
)


def _mention(
    local_id: str,
    text: str,
    start: int,
    end: int,
    entity_type: str,
    temporality: str,
) -> dict[str, Any]:
    return {
        "local_id": local_id,
        "surface_text": text[start:end],
        "section_span_start": start,
        "section_span_end": end,
        "entity_type": entity_type,
        "assertion": "present",
        "temporality": temporality,
        "experiencer": "patient",
        "laterality": "not_applicable",
        "severity": "not_applicable",
        "trend": "not_applicable",
        "normalization_status": "unattempted",
        "concept_id": None,
        "preferred_name": None,
        "terminology": None,
        "quality_flags": [],
    }


def rule_baseline_annotation(task: dict[str, Any]) -> dict[str, Any]:
    """Extract only high-precision measurements and explicit temporal tokens.

    This baseline deliberately does not guess symptoms, problems, findings, anatomy,
    procedures, devices, medications, or relations.
    """

    text = task["section_text"]
    candidates: list[tuple[int, int, str, str]] = []
    for match in MEASUREMENT_PATTERN.finditer(text):
        candidates.append((match.start(), match.end(), "measurement", "current"))
    for pattern, temporality in TEMPORAL_PATTERNS:
        for match in pattern.finditer(text):
            candidates.append(
                (match.start(), match.end(), "temporal_expression", temporality)
            )
    candidates = sorted(set(candidates), key=lambda item: (item[0], item[1], item[2]))
    mentions = [
        _mention(f"m{index}", text, start, end, entity_type, temporality)
        for index, (start, end, entity_type, temporality) in enumerate(
            candidates, start=1
        )
    ]
    annotation = {
        "schema_version": SECTION_ANNOTATION_SCHEMA_VERSION,
        "manifest_row_id": task["manifest_row_id"],
        "document_id": task["document_id"],
        "section_id": task["section_id"],
        "section_text_sha256": task["section_text_sha256"],
        "mentions": mentions,
        "relations": [],
    }
    SectionAnnotationValidator().validate(
        annotation,
        {
            "manifest_row_id": task["manifest_row_id"],
            "document_id": task["document_id"],
            "section_id": task["section_id"],
            "span_sha256": task["section_text_sha256"],
        },
        text,
    )
    return annotation
