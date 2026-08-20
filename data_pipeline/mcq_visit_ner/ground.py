"""Ground model surface_text to an exact substring of the source field."""

from __future__ import annotations


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
    """Return (start, end, rewritten) or None if absent/ambiguous.

    ``rewritten`` is True when the grounded source slice differs from the
    model surface (case/whitespace folding). Callers must then replace
    ``surface_text`` with ``text[start:end]``.
    """
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
