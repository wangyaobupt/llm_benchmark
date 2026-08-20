"""Resolve medication names to generic ingredients."""

from __future__ import annotations

import re

from .mappings import DRUG_INGREDIENTS
from .text import collapse_ws, lookup_key

_SALT = re.compile(
    r"\b(hydrochloride|hcl|tartrate|succinate|sulfate|sulphate|acetate|"
    r"mesylate|besylate|fumarate|bitartrate|phosphate)\b",
    re.IGNORECASE,
)
_PAREN = re.compile(r"\([^)]*\)")


def drug_display(name: str) -> str:
    collapsed = collapse_ws(name) or ""
    if not collapsed:
        return ""
    if collapsed.isupper() or collapsed.islower():
        titled = collapsed.title()
        return titled.replace("'S", "'s")
    return collapsed


def resolve_drug_ingredients(name: str) -> tuple[str, ...]:
    collapsed = collapse_ws(name) or ""
    if not collapsed:
        return ()
    key = lookup_key(collapsed)
    if key and key in DRUG_INGREDIENTS:
        return DRUG_INGREDIENTS[key]
    no_paren = collapse_ws(_PAREN.sub(" ", collapsed)) or ""
    no_paren_key = lookup_key(no_paren)
    if no_paren_key and no_paren_key in DRUG_INGREDIENTS:
        return DRUG_INGREDIENTS[no_paren_key]
    for inner in _PAREN.findall(collapsed):
        piece = inner.strip("()")
        piece_key = lookup_key(piece)
        if piece_key and piece_key in DRUG_INGREDIENTS:
            return DRUG_INGREDIENTS[piece_key]
    stripped = collapse_ws(_SALT.sub(" ", no_paren)) or ""
    stripped_key = lookup_key(stripped)
    if stripped_key and stripped_key in DRUG_INGREDIENTS:
        return DRUG_INGREDIENTS[stripped_key]
    display = drug_display(collapsed)
    return (display,) if display else ()
