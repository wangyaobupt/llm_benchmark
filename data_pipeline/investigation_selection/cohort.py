"""Versioned multi-domain cohort audit contracts for W8."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


class CohortContractError(ValueError):
    pass


@dataclass(frozen=True)
class DiagnosisMapping:
    raw_code: str
    family: str | None
    mapping_status: str
    mapping_version: str


def map_diagnosis(code: str, mapping: Mapping[str, str], *, version: str) -> DiagnosisMapping:
    raw_code = str(code).strip()
    if not raw_code:
        raise CohortContractError("diagnosis code is required")
    family = mapping.get(raw_code)
    return DiagnosisMapping(raw_code, family, "mapped" if family else "unmapped", version)


def audit_domains(rows: Iterable[Mapping[str, Any]], *, required_domains: Iterable[str]) -> tuple[dict[str, Any], ...]:
    required = tuple(dict.fromkeys(str(value) for value in required_domains))
    if len(required) != 7:
        raise CohortContractError("W8 requires exactly seven preregistered domains")
    grouped: dict[str, list[Mapping[str, Any]]] = {domain: [] for domain in required}
    for row in rows:
        domain = str(row.get("diagnosis_family", ""))
        if domain in grouped:
            grouped[domain].append(row)
    audits = []
    for domain in required:
        domain_rows = grouped[domain]
        subjects = {str(row.get("subject_ref")) for row in domain_rows if row.get("subject_ref")}
        count = len(subjects)
        audits.append({
            "domain": domain,
            "subject_count": count,
            "event_count": len(domain_rows),
            "source_coverage": {source: sum(bool(row.get("source_coverage", {}).get(source)) for row in domain_rows) for source in ("ED", "HOSP", "Note", "POE", "lab")},
            "time_constructible_count": sum(bool(row.get("time_constructible", False)) for row in domain_rows),
            "time_constructible_rate": (sum(bool(row.get("time_constructible", False)) for row in domain_rows) / len(domain_rows)) if domain_rows else 0.0,
        })
    return tuple(audits)


def select_domains(audits: Iterable[Mapping[str, Any]], *, minimum_subjects: int, minimum_time_rate: float, minimum_selected: int = 4) -> tuple[dict[str, Any], ...]:
    rows = sorted((dict(row) for row in audits), key=lambda row: str(row["domain"]))
    if minimum_subjects < 1 or not 0 <= minimum_time_rate <= 1:
        raise CohortContractError("invalid domain thresholds")
    selected = []
    for row in rows:
        eligible = row.get("subject_count", 0) >= minimum_subjects and row.get("time_constructible_rate", 0.0) >= minimum_time_rate
        selected.append({**row, "selected": eligible, "selection_reason": "MEETS_COHORT_AND_TIME_GATES" if eligible else "FAILS_COHORT_OR_TIME_GATES"})
    if sum(bool(row["selected"]) for row in selected) < minimum_selected:
        raise CohortContractError("fewer than four domains pass W8 gates")
    minimum_size = min(row["subject_count"] for row in selected if row["selected"])
    for row in selected:
        if row["selected"] and row["subject_count"] > 2 * minimum_size:
            row["selected"] = False
            row["selection_reason"] = "EXCEEDS_TWO_TIMES_MINIMUM_DOMAIN"
    if sum(bool(row["selected"]) for row in selected) < minimum_selected:
        raise CohortContractError("domain size cap leaves fewer than four selected domains")
    return tuple(selected)
