"""Short visit snippets so reviewers can judge a fragment. Never attach full DS."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .io import iter_json_array
from .symptoms import split_complaint
from .text import collapse_ws, lookup_key

HPI_CHARS = 420
MAX_EXAMPLES = 3


def _excerpt(text: Any, limit: int = HPI_CHARS) -> str | None:
    collapsed = collapse_ws(text)
    if not collapsed:
        return None
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit].rstrip() + "…"


def build_context_index(visits_path: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    if not visits_path.is_file():
        return index
    for visit in iter_json_array(visits_path):
        hadm_id = str(visit.get("hadm_id") or "")
        hpi = _excerpt(visit.get("history_of_present_illness"))
        _index_complaint(index, "chief_complaint", visit.get("chief_complaint"), hpi, hadm_id)
        _index_complaint(
            index,
            "ed_chief_complaint",
            visit.get("ed_chief_complaint"),
            hpi,
            hadm_id,
        )
        exams = [
            collapse_ws(item.get("exam_name"))
            for item in (visit.get("investigations") or {}).get("radiology") or []
        ]
        exams = [name for name in exams if name]
        for name in exams:
            key = lookup_key(name)
            if not key or len(index[("radiology.exam_name", key)]) >= MAX_EXAMPLES:
                continue
            siblings = [other for other in exams if other != name][:4]
            index[("radiology.exam_name", key)].append(
                {
                    "hadm_id": hadm_id,
                    "full_field": name,
                    "hpi_excerpt": hpi,
                    "other_exams": siblings,
                }
            )
        for item in (visit.get("investigations") or {}).get("laboratory") or []:
            label = collapse_ws(item.get("label"))
            key = lookup_key(label)
            if not key or len(index[("lab.label", key)]) >= MAX_EXAMPLES:
                continue
            index[("lab.label", key)].append(
                {
                    "hadm_id": hadm_id,
                    "full_field": label,
                    "fluid": item.get("fluid"),
                    "category": item.get("category"),
                    "hpi_excerpt": hpi,
                }
            )
    return index


def _index_complaint(
    index: dict[tuple[str, str], list[dict[str, Any]]],
    field: str,
    text: Any,
    hpi: str | None,
    hadm_id: str,
) -> None:
    full = collapse_ws(text)
    if not full:
        return
    parts = split_complaint(full) or [full]
    example = {
        "hadm_id": hadm_id,
        "full_field": full,
        "hpi_excerpt": hpi,
        "matched_span": None,
    }
    for part in parts:
        key = lookup_key(part)
        if not key or len(index[(field, key)]) >= MAX_EXAMPLES:
            continue
        if any(item.get("full_field") == full for item in index[(field, key)]):
            continue
        payload = dict(example)
        payload["matched_span"] = part
        index[(field, key)].append(payload)
