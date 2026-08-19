"""Privacy boundary: forbidden fields, payload minimization, text privacy checks.

Implements design doc §4.3 (forbidden external-API fields) and the low-level text
checks reused by the 12 program validations (§10).
"""
from __future__ import annotations

import re
from typing import Any

# Fields that must never appear (recursively) in any external model payload.
FORBIDDEN_API_FIELDS = frozenset({
    "subject_id", "hadm_id", "stay_id", "note_id",
    "primary_icd_code", "primary_icd_version", "primary_diagnosis_name",
    "other_diagnoses", "investigation_reports", "medication_prescriptions",
    "procedures", "discharge_record",
})

_DEID_RE = re.compile(r"\[\*\*[^*]*\*\*\]")
_DATE_YMD_RE = re.compile(r"\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b")
_DATE_DMY_RE = re.compile(r"\b\d{1,2}[-/]\d{1,2}[-/](?:19|20)\d{2}\b")
_DATE_MONTH_RE = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b", re.IGNORECASE)
_LINKAGE_RE = re.compile(r"\b\d{6,}\b|\b(?:subject|hadm|stay|mrn|hospital)[\s_-]*id\b|\b(?:mr|medical record) ?number\b", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

# Posterior-leak keywords (diagnosis / results / treatment / admission facts that
# are NOT condition features and must not be invented into the stem). Heuristic;
# the generation prompt also forbids these, and the auto reviewer double-checks.
_POSTERIOR_RE = re.compile(
    r"\b(?:diagnos[a-z]*|confirm[a-z]*|reveal[a-z]*|found to have|"
    r"result(?:ed|s)? (?:show|reveal)|treated? with|admitted? to|"
    r"discharged?|prescribed?|undergo(?:ing)?|on [a-z]+ therapy)\b",
    re.IGNORECASE,
)


def find_forbidden_fields(payload: Any, path: str = "$") -> list[str]:
    """Recursively find forbidden field names (case-insensitive) in a payload."""
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            p = f"{path}.{key}" if path else key
            if isinstance(key, str) and key.casefold() in FORBIDDEN_API_FIELDS:
                found.append(p)
            found.extend(find_forbidden_fields(value, p))
    elif isinstance(payload, list):
        for i, value in enumerate(payload):
            found.extend(find_forbidden_fields(value, f"{path}[{i}]"))
    return found


def assert_no_forbidden_fields(payload: Any) -> None:
    found = find_forbidden_fields(payload)
    if found:
        raise ValueError(
            "forbidden fields in external payload: " + ", ".join(found)
        )


def contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def contains_exact_date(text: str) -> bool:
    s = text or ""
    return bool(_DATE_YMD_RE.search(s) or _DATE_DMY_RE.search(s) or _DATE_MONTH_RE.search(s))


def contains_deidentification_placeholder(text: str) -> bool:
    return bool(_DEID_RE.search(text or ""))


def contains_linkage_identifier(text: str) -> bool:
    return bool(_LINKAGE_RE.search(text or ""))


def contains_posterior_fact(text: str) -> bool:
    return bool(_POSTERIOR_RE.search(text or ""))


def shingle_jaccard(a: str, b: str, k: int = 5) -> float:
    """k-word shingle Jaccard similarity between two strings."""
    def shingles(s: str) -> set:
        toks = (s or "").casefold().split()
        if len(toks) < k:
            return {tuple(toks)} if toks else set()
        return {tuple(toks[i:i + k]) for i in range(len(toks) - k + 1)}
    sa, sb = shingles(a), shingles(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
