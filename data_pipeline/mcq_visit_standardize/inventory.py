"""Build a de-identified term inventory from frozen visit rows."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .text import collapse_ws


def add_inventory_from_visit(visit: dict[str, Any], counts: dict[str, Counter[str]]) -> None:
    def add(field: str, value: Any) -> None:
        text = collapse_ws(value)
        if text:
            counts.setdefault(field, Counter())[text] += 1

    add("chief_complaint", visit.get("chief_complaint"))
    add("ed_chief_complaint", visit.get("ed_chief_complaint"))
    add("allergies", visit.get("allergies"))
    add("rhythm", visit.get("rhythm"))
    add("primary_service", visit.get("primary_service"))
    add("primary_diagnosis_name", visit.get("primary_diagnosis_name"))
    for name in visit.get("other_diagnoses") or []:
        add("other_diagnoses", name)
    for item in visit.get("medications") or []:
        add("medications.drug", item.get("drug"))
    for item in visit.get("medrecon") or []:
        add("medrecon.name", item.get("name"))
    labs = (visit.get("investigations") or {}).get("laboratory") or []
    for item in labs:
        add("lab.label", item.get("label"))
        for row in item.get("results") or []:
            add("lab.valueuom", row.get("valueuom"))
    for item in (visit.get("investigations") or {}).get("radiology") or []:
        add("radiology.exam_name", item.get("exam_name"))


def inventory_rows(counts: dict[str, Counter[str]]) -> list[dict[str, Any]]:
    rows = []
    for field, counter in sorted(counts.items()):
        for source, frequency in counter.most_common():
            rows.append({"field": field, "source": source, "frequency": int(frequency)})
    return rows


def review_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str, str]] = Counter()
    for item in items:
        counter[(item["domain"], item["field"], item["source"])] += 1
    rows = []
    for (domain, field, source), frequency in counter.most_common():
        rows.append(
            {
                "domain": domain,
                "field": field,
                "source": source,
                "frequency": int(frequency),
                "status": "unresolved",
            }
        )
    return rows
