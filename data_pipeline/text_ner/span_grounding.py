"""Deterministically ground model-proposed spans back to exact source text."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Iterable, Mapping


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
    match_kind: str,
) -> tuple[tuple[int, int], str, int] | None:
    candidate_list = list(candidates)
    if not candidate_list:
        return None
    if len(candidate_list) == 1:
        return candidate_list[0], f"unique_{match_kind}_occurrence", 1
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
    return (
        (start, end),
        f"unique_nearest_{match_kind}_occurrence",
        len(candidate_list),
    )


def _casefold_whitespace_with_mapping(
    value: str,
) -> tuple[str, list[int], list[int]]:
    normalized: list[str] = []
    source_starts: list[int] = []
    source_ends: list[int] = []
    previous_was_whitespace = False
    for index, character in enumerate(value):
        if character.isspace():
            if previous_was_whitespace:
                source_ends[-1] = index + 1
            else:
                normalized.append(" ")
                source_starts.append(index)
                source_ends.append(index + 1)
            previous_was_whitespace = True
            continue
        previous_was_whitespace = False
        folded = character.casefold()
        for normalized_character in folded:
            normalized.append(normalized_character)
            source_starts.append(index)
            source_ends.append(index + 1)
    return "".join(normalized), source_starts, source_ends


def _casefold_whitespace_occurrences(
    text: str, surface: str
) -> list[tuple[int, int]]:
    normalized_text, source_starts, source_ends = (
        _casefold_whitespace_with_mapping(text)
    )
    normalized_surface, _, _ = _casefold_whitespace_with_mapping(surface)
    normalized_surface = normalized_surface.strip()
    if not normalized_surface:
        return []
    occurrences: set[tuple[int, int]] = set()
    search_from = 0
    while True:
        start = normalized_text.find(normalized_surface, search_from)
        if start < 0:
            return sorted(occurrences)
        end = start + len(normalized_surface)
        occurrences.add((source_starts[start], source_ends[end - 1]))
        search_from = start + 1


def _ground_item_span(
    item: dict[str, Any],
    *,
    section_text: str,
    surface_field: str,
    start_field: str,
    end_field: str,
    item_kind: str,
    candidate_filter: Callable[[int, int], bool] | None = None,
) -> dict[str, Any] | None:
    surface = item[surface_field]
    original_start = item[start_field]
    original_end = item[end_field]
    current_is_allowed = candidate_filter is None or candidate_filter(
        original_start, original_end
    )
    if (
        0 <= original_start < original_end <= len(section_text)
        and section_text[original_start:original_end] == surface
        and current_is_allowed
    ):
        return None
    exact_candidates = _exact_occurrences(section_text, surface)
    if candidate_filter is not None:
        exact_candidates = [
            (start, end)
            for start, end in exact_candidates
            if candidate_filter(start, end)
        ]
    match_kind = "exact"
    candidate_list = exact_candidates
    if not candidate_list:
        candidate_list = _casefold_whitespace_occurrences(section_text, surface)
        if candidate_filter is not None:
            candidate_list = [
                (start, end)
                for start, end in candidate_list
                if candidate_filter(start, end)
            ]
        match_kind = "casefold_whitespace"
    selected = _select_grounded_span(
        candidate_list,
        original_start=original_start,
        original_end=original_end,
        match_kind=match_kind,
    )
    if selected is None:
        return None
    (grounded_start, grounded_end), rule, candidate_count = selected
    item[start_field] = grounded_start
    item[end_field] = grounded_end
    grounded_surface = section_text[grounded_start:grounded_end]
    surface_rewritten = grounded_surface != surface
    if surface_rewritten:
        item[surface_field] = grounded_surface
    return {
        "item_kind": item_kind,
        "local_id": item["local_id"],
        "original_start": original_start,
        "original_end": original_end,
        "grounded_start": grounded_start,
        "grounded_end": grounded_end,
        "candidate_count": candidate_count,
        "rule": rule,
        "surface_rewritten_from_source": surface_rewritten,
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
        source = mention_by_id.get(relation["source_mention_id"])
        target = mention_by_id.get(relation["target_mention_id"])
        candidate_filter: Callable[[int, int], bool] | None = None
        if source is not None and target is not None:
            required_start = min(
                source["section_span_start"], target["section_span_start"]
            )
            required_end = max(source["section_span_end"], target["section_span_end"])
            candidate_filter = (
                lambda start, end, required_start=required_start, required_end=required_end: (
                    start <= required_start and end >= required_end
                )
            )
        repair = _ground_item_span(
            relation,
            section_text=section_text,
            surface_field="evidence_text",
            start_field="section_evidence_start",
            end_field="section_evidence_end",
            item_kind="relation",
            candidate_filter=candidate_filter,
        )
        if repair is not None:
            repairs.append(repair)
    return grounded, repairs
