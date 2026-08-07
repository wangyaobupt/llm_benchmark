"""Phase 3: DS discharge summary chapter parsing."""

from __future__ import annotations
import re
import logging
from typing import Any

from .config import DS_SECTION_TITLES, DS_SECTIONS

logger = logging.getLogger(__name__)

# Build regex pattern for matching any known section title at line start
_title_pattern_str = r"^\s*(" + "|".join(
    re.escape(t) for t in DS_SECTION_TITLES
) + r")\s*:?\s*$"
_title_re = re.compile(_title_pattern_str, re.MULTILINE | re.IGNORECASE)


def normalize_text(text: str) -> str:
    """Normalize line endings."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def find_sections(text: str) -> dict[str, tuple[int, int]]:
    """Find all section title positions.

    Returns {title_lower: (content_start, content_end)}.
    """
    text = normalize_text(text)
    matches = list(_title_re.finditer(text))
    if not matches:
        return {}

    sections: dict[str, tuple[int, int]] = {}
    for i, m in enumerate(matches):
        title = m.group(1).lower()
        content_start = m.end()
        if i + 1 < len(matches):
            content_end = matches[i + 1].start()
        else:
            content_end = len(text)
        if title not in sections:
            sections[title] = (content_start, content_end)

    return sections


def extract_section(
    sections: dict[str, tuple[int, int]],
    text: str,
    title_variants: tuple[str, ...],
) -> str | None:
    """Extract content for a section by trying title variants."""
    for variant in title_variants:
        key = variant.lower()
        if key in sections:
            start, end = sections[key]
            content = text[start:end].strip()
            if content:
                return content
            return None
    return None


def parse_ds(text: str) -> dict[str, dict[str, Any]]:
    """Parse DS text into structured sections.

    Returns:
        {"narrative": {field: value}, "disposition": {field: value}}
    """
    sections = find_sections(text)
    result: dict[str, dict[str, Any]] = {"narrative": {}, "disposition": {}}

    for group, field, title_variants in DS_SECTIONS:
        value = extract_section(sections, text, title_variants)
        result[group][field] = value

    return result


def select_ds(notes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Select the best DS from multiple candidates.

    Selection: has non-empty Chief Complaint, then newest by
    note_seq DESC, event_time DESC, recorded_time DESC, note_id DESC.
    """
    candidates = []
    for note in notes:
        text = note.get("text") or ""
        if not text.strip():
            continue
        parsed = parse_ds(text)
        cc = parsed.get("narrative", {}).get("chief_complaint")
        if cc and cc.strip():
            note["_parsed"] = parsed
            candidates.append(note)

    if not candidates:
        for note in notes:
            text = note.get("text") or ""
            if text.strip():
                note["_parsed"] = parse_ds(text)
                candidates.append(note)

    if not candidates:
        return None

    def sort_key(n):
        ns = n.get("note_seq") or 0
        et = str(n.get("event_time")) if n.get("event_time") else ""
        rt = str(n.get("recorded_time")) if n.get("recorded_time") else ""
        ni = n.get("note_id") or ""
        return (ns, et, rt, ni)

    candidates.sort(key=sort_key)
    return candidates[-1]
