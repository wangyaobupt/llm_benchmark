"""Chief-complaint and allergy concept extraction."""

from __future__ import annotations

import re
from typing import Any

from .abbrev import expand_ehr_abbreviations, expand_for_display
from .mappings import NKA_KEYS, SYMPTOM_ALIASES
from .text import collapse_ws, is_redacted, lookup_key

_NOT_SYMPTOM = frozenset(
    {
        "transfer",
        "unknown-cc",
        "unknown cc",
        "no complaints",
        "no ride home",
        "denies t/e/d",
    }
)
_NARRATIVE = re.compile(
    r"\b(presents with|year[- ]old|\byo\b|was seen|admission note|history of present|discharged from)\b",
    re.IGNORECASE,
)

_SPLIT = re.compile(r"\s*[,;]\s*")
_DENIED = re.compile(
    r"^(denies|denied|deny|no|not|without)\s+(?:any\s+)?(.+)$",
    re.IGNORECASE,
)


def split_complaint(text: str) -> list[str]:
    parts = []
    for piece in _SPLIT.split(text):
        collapsed = collapse_ws(piece)
        if collapsed:
            parts.append(collapsed)
    return parts


def _alias_table(extra: dict[str, tuple[str, str]] | None) -> dict[str, tuple[str, str]]:
    table = dict(SYMPTOM_ALIASES)
    for standard, concept_id in list(table.values()):
        key = lookup_key(standard)
        if key:
            table.setdefault(key, (standard, concept_id))
    if extra:
        table.update(extra)
    return table


def _map_symptom(source: str, aliases: dict[str, tuple[str, str]]) -> dict[str, Any]:
    key_now = lookup_key(source) or ""
    if (
        is_redacted(source)
        or key_now in _NOT_SYMPTOM
        or source.startswith('"')
        or _NARRATIVE.search(source)
        or len(source.split()) > 12
        or len(source) > 80
        or (len(key_now) <= 2 and key_now not in SYMPTOM_ALIASES and key_now not in {"nv"})
    ):
        return {
            "source": source,
            "standard": None,
            "concept_id": None,
            "polarity": "asserted",
            "status": "not_applicable",
        }
    whole = aliases.get(key_now)
    if whole is not None:
        standard, concept_id = whole
        return {
            "source": source,
            "standard": standard,
            "concept_id": concept_id,
            "polarity": "asserted",
            "status": "mapped/exact",
        }
    polarity = "asserted"
    remainder = source
    denied = _DENIED.match(source)
    if denied:
        polarity = "denied"
        remainder = denied.group(2).strip()
    expanded = expand_ehr_abbreviations(remainder)
    display = expand_for_display(remainder)
    key = lookup_key(display) or lookup_key(expanded) or lookup_key(remainder)
    mapped = aliases.get(key or "")
    if mapped is not None:
        standard, concept_id = mapped
        return {
            "source": source,
            "standard": standard,
            "concept_id": concept_id,
            "polarity": polarity,
            "status": "mapped/exact",
        }
    if lookup_key(expanded) and lookup_key(expanded) != lookup_key(remainder):
        from .synonyms import concept_id_from_standard

        return {
            "source": source,
            "standard": display,
            "concept_id": concept_id_from_standard(display),
            "polarity": polarity,
            "status": "mapped/exact",
        }
    return {
        "source": source,
        "standard": None,
        "concept_id": None,
        "polarity": polarity,
        "status": "unresolved",
    }


def complaint_concepts(
    text: Any,
    extra_aliases: dict[str, tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    collapsed = collapse_ws(text)
    if collapsed is None:
        return []
    aliases = _alias_table(extra_aliases)
    whole_key = lookup_key(collapsed)
    if whole_key in aliases and "," not in collapsed and ";" not in collapsed:
        return [_map_symptom(collapsed, aliases)]
    return [_map_symptom(part, aliases) for part in split_complaint(collapsed)]


def allergy_concepts(
    text: Any,
    extra_aliases: dict[str, tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    collapsed = collapse_ws(text)
    if collapsed is None:
        return []
    extras = extra_aliases or {}
    key = lookup_key(collapsed)
    if key in NKA_KEYS:
        return [
            {
                "source": collapsed,
                "standard": "No known allergies",
                "concept_id": "allergy:nka",
                "polarity": "asserted",
                "status": "mapped/exact",
            }
        ]
    concepts = []
    for part in re.split(r"[\n;]+", collapsed):
        piece = collapse_ws(part)
        if not piece:
            continue
        piece_key = lookup_key(piece)
        if piece_key in NKA_KEYS:
            concepts.append(
                {
                    "source": piece,
                    "standard": "No known allergies",
                    "concept_id": "allergy:nka",
                    "polarity": "asserted",
                    "status": "mapped/exact",
                }
            )
            continue
        mapped = extras.get(piece_key or "")
        if mapped is not None:
            standard, concept_id = mapped
            concepts.append(
                {
                    "source": piece,
                    "standard": standard,
                    "concept_id": concept_id,
                    "polarity": "asserted",
                    "status": "mapped/exact",
                }
            )
            continue
        concepts.append(
            {
                "source": piece,
                "standard": None,
                "concept_id": None,
                "polarity": "asserted",
                "status": "unresolved",
            }
        )
    return concepts
