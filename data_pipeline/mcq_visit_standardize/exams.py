"""Normalize MIMIC radiology exam_name strings to readable English.

Plain films follow ``Abdominal X-ray, Supine and Erect Views``.
CT/MRI/US keep region, laterality, and contrast. Operating-room location
is dropped; portable is kept when it is the view.
"""

from __future__ import annotations

import re
from typing import Any

from .mappings import EXAM_ALIASES
from .text import collapse_ws, is_redacted, lookup_key

_DEVICE_PORT = "implantable_port"
_PUNCT_SPACE = re.compile(r"\s+([,;:])")
_MULTI_COMMA = re.compile(r"\s*,\s*")

_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"w\s*/\s*&\s*w/\s*o\s+contrast", "with and without contrast"),
    (r"w/\s*o\s*&\s*w/\s*contrast", "with and without contrast"),
    (r"w\s*&\s*w/\s*o\s+contrast", "with and without contrast"),
    (r"w\s*&\s*w/\s*o\s*c(?:ontrast)?", "with and without contrast"),
    (r"w&\s*w/\s*o\s*c(?:ontrast)?", "with and without contrast"),
    (r"w/\s*o\s+contrast", "without contrast"),
    (r"without\s+contrast", "without contrast"),
    (r"with\s+contrast", "with contrast"),
    (r"w/\s*contrast", "with contrast"),
    (r"w/\s*o\s*c\b", "without contrast"),
    (r"w/\s*oc\b", "without contrast"),
    (r"w/\s*c\b", "with contrast"),
    (r",?\s*addl sections", ""),
    (r",?\s*&?\s*recons?\b", ""),
    (r"\bw/3d(?:\s+rend(?:ering)?)?\b", ""),
    (r"\b3d rend(?:ering)?\b", ""),
    (r"\beg:\s*parotids\b", ""),
    (r"\bcta\b", "ct angiography"),
    (r"\bctu\b", "ct urography"),
    (r"\bctc\b", "ct colonography"),
    (r"\bmrcp\b", "mrcp"),
    (r"\bmra\b", "mr angiography"),
    (r"\bmrv\b", "mr venography"),
    (r"\bmri\b", "mri"),
    (r"\bmr\b", "mri"),
    (r"\bct\b", "ct"),
    (r"\bu\.s\.?", "ultrasound"),
    (r"\bus\b", "ultrasound"),
    (r"\bcxr\b", "chest x-ray"),
    (r"\bx-?ray\b", "x-ray"),
    (r"\bkub\b", "kub"),
    (r"\bercp\b", "ercp"),
    (r"\bpicc\b", "picc"),
    (r"\bfluoro\b", "fluoroscopy"),
    (r"\babd\s*and\s*pelvis\b", "abdomen and pelvis"),
    (r"\babd\s*&\s*pelvis\b", "abdomen and pelvis"),
    (r"\babd/pel(?:vis)?\b", "abdomen and pelvis"),
    (r"\babd\b", "abdomen"),
    (r"\bc-spine\b", "cervical spine"),
    (r"\bcervical\s+spine\b", "cervical spine"),
    (r"\bc\s+spine\b", "cervical spine"),
    (r"\bl-spine\b", "lumbar spine"),
    (r"\blumbar\s+spine\b", "lumbar spine"),
    (r"\bl\s+spine\b", "lumbar spine"),
    (r"\bt-spine\b", "thoracic spine"),
    (r"\bthoracic\s+spine\b", "thoracic spine"),
    (r"\bt\s+spine\b", "thoracic spine"),
    (r"\blumbo-sacral\s+spine\b", "lumbosacral spine"),
    (r"\blow(?:er)?\s+ext(?:remity)?\b", "lower extremity"),
    (r"\bup(?:per)?\s+ext(?:remity)?\b", "upper extremity"),
    (r"\bbilat(?:eral)?\b", "bilateral"),
    (r"\bunilat(?:eral)?\b", "unilateral"),
    (r"\bextext\b", "extremity"),
    (r"\bbil\b", "bilateral"),
    (r"\bart\b", "arterial"),
    (r"\bext(?:remity)?\b", "extremity"),
    (r"\bdiag/therap\b", "diagnostic or therapeutic"),
    (r"\bw imaging\b", "with imaging"),
    (r"\bpa\s*and\s*lat\b", "pa and lateral"),
    (r"\bpa\s*&\s*lat\b", "pa and lateral"),
    (r"\bap\s*and\s*lat\b", "ap and lateral"),
    (r"\bap\s*&\s*lat\b", "ap and lateral"),
    (r"\s*&\s*", " and "),
    (r"\blat\b", "lateral"),
    (r"\bobl(?:ique)?s?\b", "oblique"),
    (r"\bdecub\b", "decubitus"),
    (r"\bmin\b", "minimum"),
    (r"\bplct\b", "placement"),
    (r"\bplmt\b", "placement"),
    (r"\bbx\b", "biopsy"),
    (r"\bguid\b", "guidance"),
    (r"\bdopp(?:ler)?\b", "doppler"),
    (r"\bdup(?:lex)?\b", "duplex"),
    (r"\bven\b", "venous"),
    (r"\bsgl\b", "single"),
    (r"\bw/\s*fluoro\b", "with fluoroscopy"),
    (r"\bperc\b", "percutaneous"),
    (r"\bcath\b", "catheter"),
    (r"\binj\b", "injection"),
    (r"\bcompl(?:ete)?\b", "complete"),
    (r"\blimit(?:ed)?\b", "limited"),
)

_COMPILED = [(re.compile(pattern), replacement) for pattern, replacement in _REPLACEMENTS]

_KEEP_CASE = {
    "ct": "CT",
    "mri": "MRI",
    "mrcp": "MRCP",
    "ercp": "ERCP",
    "picc": "PICC",
    "pa": "PA",
    "ap": "AP",
    "kub": "KUB",
    "dvt": "DVT",
    "iv": "IV",
    "gi": "GI",
    "aaa": "AAA",
}

_HAS_CROSS_SECTION = re.compile(
    r"\b(?:ct|mri|ultrasound|angiography|fluoroscopy|mrcp|ercp|picc)\b"
)
_VIEW_WORDS = frozenset(
    {
        "pa",
        "ap",
        "lateral",
        "oblique",
        "mortise",
        "supine",
        "erect",
        "portable",
        "single",
        "decubitus",
        "view",
        "views",
        "pre-op",
        "inlet",
        "outlet",
        "frog",
        "neutral",
        "axillary",
        "waters",
        "caldwell",
        "flex",
        "extension",
    }
)
_SMALL = frozenset({"and", "or", "of", "with", "without", "to", "for"})
_BODIES: tuple[tuple[str, str], ...] = (
    ("lumbosacral spine", "lumbar spine"),
    ("lumbar spine", "lumbar spine"),
    ("cervical spine", "cervical spine"),
    ("thoracic spine", "thoracic spine"),
    ("tibia/fibula", "tibia/fibula"),
    ("abdomen", "abdominal"),
    ("abdominal", "abdominal"),
    ("shoulder", "shoulder"),
    ("forearm", "forearm"),
    ("humerus", "humerus"),
    ("clavicle", "clavicle"),
    ("fingers", "finger"),
    ("finger", "finger"),
    ("pelvis", "pelvis"),
    ("chest", "chest"),
    ("ankle", "ankle"),
    ("wrist", "wrist"),
    ("elbow", "elbow"),
    ("femur", "femur"),
    ("hand", "hand"),
    ("knee", "knee"),
    ("foot", "foot"),
    ("hips", "hip"),
    ("hip", "hip"),
    ("ribs", "rib"),
    ("rib", "rib"),
    ("toes", "toe"),
    ("toe", "toe"),
)


def _protect_device_port(text: str) -> str:
    text = re.sub(r"\bw/\s*o\s+port\b", f"without {_DEVICE_PORT}", text)
    text = re.sub(r"\bwithout\s+port\b", f"without {_DEVICE_PORT}", text)
    text = re.sub(r"\b(?:w/|with)\s+port\b", f"with {_DEVICE_PORT}", text)
    return text


def _strip_or_and_mark_portable(text: str) -> str:
    text = _protect_device_port(text)
    text = re.sub(r"\bin\s+o\.?r\.?", " ", text)
    text = re.sub(r"\bin\s+or\b", " ", text)
    text = re.sub(r"\bport\.\s*", "portable ", text)
    text = re.sub(r"\bport\b", "portable", text)
    return text.replace(_DEVICE_PORT, "port")


def _apply_replacements(text: str) -> str:
    for pattern, replacement in _COMPILED:
        text = pattern.sub(replacement, text)
    text = re.sub(r",(?=\S)", ", ", text)
    return text


def _modality_first(text: str) -> str:
    match = re.match(
        r"^(?P<body>.+?)\s+(?P<mod>ultrasound|ct|mri)(?P<rest>.*)$",
        text,
    )
    if not match:
        return text
    body = match.group("body").strip()
    if re.match(r"^(ct|mri|ultrasound)\b", body):
        return text
    return collapse_ws(f"{match.group('mod')} {body} {match.group('rest')}") or text


def _infer_ultrasound(text: str) -> str:
    if _HAS_CROSS_SECTION.search(text):
        return text
    if re.search(r"\b(?:veins|venous|duplex|doppler|carotid series)\b", text):
        return f"ultrasound {text}"
    return text


def _take_laterality(text: str) -> tuple[str, str]:
    found: list[str] = []

    def _keep(match: re.Match[str]) -> str:
        found.append(match.group(1))
        return " "

    text = re.sub(r"\b(left|right|bilateral)\b", _keep, text)
    text = re.sub(r"\bunilateral\b", " ", text)
    side = ""
    if "bilateral" in found:
        side = "bilateral"
    elif "left" in found and "right" not in found:
        side = "left"
    elif "right" in found and "left" not in found:
        side = "right"
    return side, collapse_ws(text) or ""


def _view_clause(raw: str) -> str:
    text = collapse_ws(raw) or ""
    text = re.sub(r"\bonly\b", " ", text)
    text = collapse_ws(text) or ""
    if not text:
        return ""
    tokens = [tok.strip(",") for tok in text.replace(",", " ").split()]
    has_view = any(tok in _VIEW_WORDS for tok in tokens)
    if has_view and not any(tok in {"view", "views"} for tok in tokens):
        multi = "," in text or " and " in text
        text = f"{text} {'views' if multi else 'view'}"
    return text


def _format_xray(text: str) -> str:
    if _HAS_CROSS_SECTION.search(text) or re.search(r"\bx-ray\b", text):
        if re.search(r"\bchest x-ray\b", text) and not _HAS_CROSS_SECTION.search(text):
            return "chest x-ray"
        return text
    if re.match(r"^trauma\s*#\s*3\b", text):
        return "chest x-ray, trauma view"
    if re.match(r"^trauma\s*#\s*2\b", text):
        return "chest and pelvis x-ray, trauma views"
    original = text
    laterality, text = _take_laterality(text)
    paren = re.search(r"\(([^)]*)\)", text)
    views: list[str] = []
    if paren:
        views.append(paren.group(1))
        text = collapse_ws(text[: paren.start()] + " " + text[paren.end() :]) or ""
        text = re.sub(r"\bportable\b", " ", text)
        text = collapse_ws(text) or ""
    body_label = None
    for pattern, label in _BODIES:
        if re.search(rf"\b{re.escape(pattern)}\b", text):
            body_label = label
            text = re.sub(rf"\b{re.escape(pattern)}\b", " ", text)
            break
    leftover = collapse_ws(text) or ""
    leftover = re.sub(r"\b(?:\d+\s+)?exam\b", " ", leftover)
    leftover = collapse_ws(leftover) or ""
    if leftover and re.search(r"\b(?:line|tube|placement)\b", leftover):
        leftover = collapse_ws(re.sub(r"\bportable\b", " ", leftover)) or leftover
    if leftover == "portable" and not views:
        views.append("portable")
    elif leftover:
        views.append(leftover)
    if not body_label:
        return original
    head = f"{laterality} {body_label} x-ray".strip()
    clause = _view_clause(" ".join(views))
    if clause:
        return f"{head}, {clause}"
    return head


def _cap_token(word: str, *, first: bool = False, title: bool = False) -> str:
    prefix = ""
    suffix = ""
    core = word
    while core and core[0] in "([":
        prefix += core[0]
        core = core[1:]
    while core and core[-1] in ")].,;:":
        suffix = core[-1] + suffix
        core = core[:-1]
    lower = core.casefold()
    if lower == "x-ray":
        return f"{prefix}X-ray{suffix}"
    mapped = _KEEP_CASE.get(lower)
    if mapped:
        return f"{prefix}{mapped}{suffix}"
    if title:
        if lower in _SMALL and not first:
            return f"{prefix}{lower}{suffix}"
        if core:
            return f"{prefix}{core[:1].upper()}{core[1:]}{suffix}"
        return word
    if first and core:
        return f"{prefix}{core[:1].upper()}{core[1:]}{suffix}"
    return f"{prefix}{core}{suffix}" if core else word


def _display(text: str) -> str:
    cleaned = collapse_ws(text) or ""
    cleaned = _PUNCT_SPACE.sub(r"\1", cleaned)
    cleaned = _MULTI_COMMA.sub(", ", cleaned)
    cleaned = cleaned.replace("( ", "(").replace(" )", ")")
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = collapse_ws(cleaned) or ""
    if ", " in cleaned:
        head, tail = cleaned.split(", ", 1)
        head_words = [
            _cap_token(word, first=index == 0, title=True) for index, word in enumerate(head.split())
        ]
        out_tail = [
            _cap_token(word, first=index == 0, title=True) for index, word in enumerate(tail.split())
        ]
        return f"{' '.join(head_words)}, {' '.join(out_tail)}"
    words = [_cap_token(word, first=index == 0) for index, word in enumerate(cleaned.split())]
    return " ".join(words)


def exam_display_name(source: str) -> str:
    collapsed = collapse_ws(source)
    if not collapsed:
        return ""
    text = collapsed.casefold()
    text = _strip_or_and_mark_portable(text)
    text = _apply_replacements(text)
    text = collapse_ws(text) or ""
    text = _infer_ultrasound(text)
    text = _modality_first(text)
    text = _format_xray(text)
    return _display(text)


def standardize_exam_name(source: Any) -> tuple[str | None, str]:
    collapsed = collapse_ws(source)
    if collapsed is None:
        return None, "not_applicable"
    if is_redacted(collapsed):
        return None, "not_applicable"
    display = exam_display_name(collapsed)
    original_key = lookup_key(collapsed)
    if original_key and original_key in EXAM_ALIASES:
        alias = EXAM_ALIASES[original_key]
        if display and lookup_key(display) != lookup_key(alias) and ", " in display:
            return display, "mapped/normalized"
        return alias, "mapped/exact"
    display_key = lookup_key(display)
    if display_key and display_key in EXAM_ALIASES:
        return EXAM_ALIASES[display_key], "mapped/exact"
    if not display:
        return None, "unresolved"
    return display, "mapped/normalized"
