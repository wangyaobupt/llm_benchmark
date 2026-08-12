"""Deterministic span-preserving section parsing for radiology reports."""

from __future__ import annotations

from dataclasses import dataclass
import re


HEADING_PATTERN = re.compile(
    r"(?m)^[ \t]*(?P<heading>[A-Z][A-Z0-9 /_()\-]{1,60}):[ \t]*"
)


@dataclass(frozen=True)
class TextSection:
    name: str
    ordinal: int
    start: int
    end: int


def _normalized_heading(value: str) -> str:
    return " ".join(value.strip().split()).casefold().replace(" ", "_")


def split_radiology_sections(text: str) -> list[TextSection]:
    """Return exhaustive, non-overlapping source spans without changing text."""
    if not text:
        return []
    matches = list(HEADING_PATTERN.finditer(text))
    if not matches:
        return [TextSection("full_report", 0, 0, len(text))]

    sections: list[TextSection] = []
    ordinal = 0
    first_start = matches[0].start()
    if text[:first_start].strip():
        sections.append(TextSection("preamble", ordinal, 0, first_start))
        ordinal += 1
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append(
            TextSection(
                _normalized_heading(match.group("heading")),
                ordinal,
                match.start(),
                end,
            )
        )
        ordinal += 1
    return sections
