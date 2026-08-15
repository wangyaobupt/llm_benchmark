"""Deterministically ground model-proposed spans back to exact source text."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping


def _exact_occurrences(text: str, surface: str) -> list[tuple[int, int]]:
    occurrences: list[tuple[int, int]] = []
    search_from = 0
    while True:
        start = text.find(surface, search_from)
        if start < 0:
            return occurrences
        occurrences.append((start, start + len(surface)))
        search_from = start + 1


def _select_grounded_span(
    candidates: Iterable[tuple[int, int]],
    *,
    original_start: int,
    original_end: int,
) -> tuple[tuple[int, int], str, int] | None:
    candidate_list = list(candidates)
    if not candidate_list:
        return None
    if len(candidate_list) == 1:
        return candidate_list[0], "unique_exact_occurrence", 1
    scored = [
        (
            abs(start - original_start) + abs(end - original_end),
            start,
            end,
        )
        for start, end in candidate_list
    ]
    minimum_distance = min(item[0] for item in scored)
    nearest = [item for item in scored if item[0] == minimum_distance]
    if len(nearest) != 1:
        return None
    _, start, end = nearest[0]
    return (start, end), "unique_nearest_exact_occurrence", len(candidate_list)


def _ground_item_span(
    item: dict[str, Any],
    *,
    section_text: str,
    surface_field: str,
    start_field: str,
    end_field: str,
    item_kind: str,
    candidates: Iterable[tuple[int, int]] | None = None,
) -> dict[str, Any] | None:
    surface = item[surface_field]
    original_start = item[start_field]
    original_end = item[end_field]
    candidate_list = None if candidates is None else list(candidates)
    if (
        0 <= original_start < original_end <= len(section_text)
        and section_text[original_start:original_end] == surface
        and (
            candidate_list is None
            or (original_start, original_end) in candidate_list
        )
    ):
        return None
    selected = _select_grounded_span(
        _exact_occurrences(section_text, surface)
        if candidate_list is None
        else candidate_list,
        original_start=original_start,
        original_end=original_end,
    )
    if selected is None:
        return None
    (grounded_start, grounded_end), rule, candidate_count = selected
    item[start_field] = grounded_start
    item[end_field] = grounded_end
    return {
        "item_kind": item_kind,
        "local_id": item["local_id"],
        "original_start": original_start,
        "original_end": original_end,
        "grounded_start": grounded_start,
        "grounded_end": grounded_end,
        "candidate_count": candidate_count,
        "rule": rule,
    }


def ground_annotation_spans(
    annotation: Mapping[str, Any], section_text: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return a grounded copy and payload-free repair provenance.

    Only literal, case-sensitive source matches are eligible. A repeated surface is
    repaired only when the model-proposed offsets identify one uniquely nearest
    occurrence. Ties and absent surfaces remain unchanged for strict validation.
    """

    grounded = deepcopy(dict(annotation))
    repairs: list[dict[str, Any]] = []
    for mention in grounded["mentions"]:
        repair = _ground_item_span(
            mention,
            section_text=section_text,
            surface_field="surface_text",
            start_field="section_span_start",
            end_field="section_span_end",
            item_kind="mention",
        )
        if repair is not None:
            repairs.append(repair)

    mention_by_id = {
        mention["local_id"]: mention for mention in grounded["mentions"]
    }
    for relation in grounded["relations"]:
        surface = relation["evidence_text"]
        candidates = _exact_occurrences(section_text, surface)
        source = mention_by_id.get(relation["source_mention_id"])
        target = mention_by_id.get(relation["target_mention_id"])
        if source is not None and target is not None:
            required_start = min(
                source["section_span_start"], target["section_span_start"]
            )
            required_end = max(source["section_span_end"], target["section_span_end"])
            candidates = [
                (start, end)
                for start, end in candidates
                if start <= required_start and end >= required_end
            ]
        repair = _ground_item_span(
            relation,
            section_text=section_text,
            surface_field="evidence_text",
            start_field="section_evidence_start",
            end_field="section_evidence_end",
            item_kind="relation",
            candidates=candidates,
        )
        if repair is not None:
            repairs.append(repair)
    return grounded, repairs
