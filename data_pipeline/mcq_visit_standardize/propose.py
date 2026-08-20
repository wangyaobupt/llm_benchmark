"""Build agent proposals for the review UI. Does not write mappings until a human accepts."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from data_pipeline.mcq_visit_extract.atomic import atomic_write_jsonl

from .abbrev import expand_for_display
from .drugs import resolve_drug_ingredients
from .exams import exam_display_name, standardize_exam_name
from .mappings import NKA_KEYS, RHYTHM_ALIASES, UNIT_ALIAS_TABLE
from .symptoms import _alias_table, split_complaint
from .synonyms import concept_id_from_standard, load_jsonl
from .text import collapse_ws, is_redacted, lookup_key

_NARRATIVE = re.compile(
    r"\b(presents with|year[- ]old|\byo\b|was seen|admission note|history of present|discharged from)\b",
    re.IGNORECASE,
)


def _catalog_by_key() -> dict[str, tuple[str, str]]:
    return _alias_table(None)


def propose_symptom(row: dict[str, Any], catalog: dict[str, tuple[str, str]]) -> dict[str, Any] | None:
    source = collapse_ws(row.get("source"))
    if not source:
        return None
    if "," in source or ";" in source:
        return None
    key = lookup_key(source)
    if not key:
        return None
    display = expand_for_display(source)
    expanded_key = lookup_key(display)
    if expanded_key and expanded_key in catalog:
        standard, concept_id = catalog[expanded_key]
        if standard != source:
            return _proposal(
                row,
                standard,
                concept_id,
                "展开电子病历缩写后命中已有概念；标准名用完整英文，不用缩写",
                "high",
            )
        return _proposal(row, standard, concept_id, "与已有标准名/同义词一致（含大小写）", "high")
    if expanded_key and expanded_key != key:
        return _proposal(
            row,
            display,
            concept_id_from_standard(display),
            "展开电子病历缩写为完整英文（B/L→bilateral，R/L→right/left），保留侧别与部位，不用缩写",
            "high",
        )
    if key in catalog:
        standard, concept_id = catalog[key]
        return _proposal(row, standard, concept_id, "与已有标准名/同义词一致（含大小写）", "high")
    if key.endswith("s") and key[:-1] in catalog:
        standard, concept_id = catalog[key[:-1]]
        return _proposal(row, standard, concept_id, "复数形式，对应已有单数概念", "high")
    if is_redacted(source) or key in {"unknown-cc", "cc"}:
        return {
            **_base(row),
            "proposed_standard": None,
            "proposed_concept_id": None,
            "proposed_action": "not_applicable",
            "reason": "脱敏、未知主诉或非症状标签，不立概念",
            "confidence": "high",
        }
    if len(key) <= 2:
        if key == "v":
            return _proposal(row, "Vomiting", "symptom:vomiting", "可能是 N/V 切开后的 V，请确认", "low")
        if key == "n":
            return _proposal(row, "Nausea", "symptom:nausea", "可能是 N/V 切开后的 N，请确认", "low")
        return {
            **_base(row),
            "proposed_standard": None,
            "proposed_concept_id": None,
            "proposed_action": "not_applicable",
            "reason": "过短，疑为切开残片或无法单独成概念",
            "confidence": "low",
        }
    words = key.split()
    if _NARRATIVE.search(source) or source.startswith('"') or len(words) > 12 or len(source) > 80:
        return {
            **_base(row),
            "proposed_standard": None,
            "proposed_concept_id": None,
            "proposed_action": "not_applicable",
            "reason": "叙事/过长，不是单条主诉概念",
            "confidence": "high",
        }
    standard = display
    if key == lookup_key(standard) or lookup_key(display) != key:
        return _proposal(
            row,
            standard,
            concept_id_from_standard(standard),
            "短主诉规范为完整英文（含大小写与缩写展开），不因频次低而跳过",
            "medium",
        )
    return None


def propose_exam(row: dict[str, Any]) -> dict[str, Any] | None:
    source = collapse_ws(row.get("source"))
    if not source:
        return None
    standard, status = standardize_exam_name(source)
    if status == "not_applicable":
        return {
            **_base(row, domain="radiology", field=row.get("field") or "radiology.exam_name"),
            "proposed_standard": None,
            "proposed_concept_id": None,
            "proposed_action": "not_applicable",
            "reason": "脱敏或空检查名，不作为影像概念",
            "confidence": "high",
        }
    display = standard or exam_display_name(source)
    if not display:
        return None
    if lookup_key(display) == lookup_key(source):
        return None
    return _proposal(
        row,
        display,
        f"exam:{lookup_key(display)}",
        "影像检查名规范为可读英文：去掉便携/手术室技术后缀，保留部位、对比剂与侧别",
        "high",
        domain="radiology",
        field=row.get("field") or "radiology.exam_name",
    )


def propose_unit(row: dict[str, Any]) -> dict[str, Any] | None:
    source = collapse_ws(row.get("source"))
    if not source:
        return None
    if lookup_key(source) in {"n/a", "na", "none"}:
        return {
            **_base(row, domain="unit", field=row.get("field") or "lab.valueuom"),
            "proposed_standard": None,
            "proposed_concept_id": None,
            "proposed_action": "not_applicable",
            "reason": "非单位（N/A），建议标为不适用而不是一种单位",
            "confidence": "high",
        }
    mapped = UNIT_ALIAS_TABLE.get(lookup_key(source) or "")
    if mapped and lookup_key(mapped) != lookup_key(source):
        return _proposal(
            row,
            mapped,
            f"unit:{lookup_key(mapped)}",
            "单位别名统一写法",
            "high",
            domain="unit",
            field=row.get("field") or "lab.valueuom",
        )
    return _proposal(
        row,
        source,
        f"unit:{lookup_key(source)}",
        "保留原单位写法",
        "medium",
        domain="unit",
        field=row.get("field") or "lab.valueuom",
    )


def propose_drug(row: dict[str, Any]) -> dict[str, Any] | None:
    source = collapse_ws(row.get("source"))
    if not source:
        return None
    if is_redacted(source):
        return {
            **_base(row, domain="drug", field=row.get("field") or "medications"),
            "proposed_standard": None,
            "proposed_concept_id": None,
            "proposed_action": "not_applicable",
            "reason": "脱敏药名，不立概念",
            "confidence": "high",
        }
    ingredients = resolve_drug_ingredients(source)
    if not ingredients:
        return None
    standard = " | ".join(ingredients)
    return _proposal(
        row,
        standard,
        f"drug:{lookup_key(ingredients[0])}",
        "商品名/盐型/大小写合并到通用名；无表则规范大小写",
        "high",
        domain="drug",
        field=row.get("field") or "medications",
    )


def propose_allergy(row: dict[str, Any]) -> dict[str, Any] | None:
    source = collapse_ws(row.get("source"))
    if not source:
        return None
    key = lookup_key(source) or ""
    if is_redacted(source):
        return {
            **_base(row, domain="allergy", field="allergies"),
            "proposed_standard": None,
            "proposed_concept_id": None,
            "proposed_action": "not_applicable",
            "reason": "脱敏过敏记录，不立概念",
            "confidence": "high",
        }
    if key in NKA_KEYS:
        return _proposal(
            row,
            "No known allergies",
            "allergy:nka",
            "无已知过敏",
            "high",
            domain="allergy",
            field="allergies",
        )
    display = expand_for_display(source)
    return _proposal(
        row,
        display,
        f"allergy:{lookup_key(display)}",
        "过敏原名称规范大小写并展开缩写",
        "medium",
        domain="allergy",
        field="allergies",
    )


def propose_rhythm(row: dict[str, Any]) -> dict[str, Any] | None:
    source = collapse_ws(row.get("source"))
    if not source:
        return None
    key = lookup_key(source) or ""
    mapped = RHYTHM_ALIASES.get(key)
    standard = mapped or expand_for_display(source)
    if not standard:
        return None
    return _proposal(
        row,
        standard,
        f"rhythm:{lookup_key(standard)}",
        "心律名称合并别名并规范英文",
        "high",
        domain="rhythm",
        field="rhythm",
    )


def propose_lab_label(row: dict[str, Any], canonical: str) -> dict[str, Any]:
    return _proposal(
        row,
        canonical,
        f"lab:{lookup_key(canonical)}",
        "同一化验名称仅大小写不同，建议统一到频次更高的写法",
        "high",
        domain="lab",
        field="lab.label",
    )


def _base(row: dict[str, Any], domain: str | None = None, field: str | None = None) -> dict[str, Any]:
    source = collapse_ws(row.get("source")) or str(row.get("source") or "")
    return {
        "domain": domain or row.get("domain") or "symptom",
        "field": field or row.get("field"),
        "source": source,
        "lookup_key": lookup_key(source),
        "frequency": int(row.get("frequency") or 0),
    }


def _proposal(
    row: dict[str, Any],
    standard: str,
    concept_id: str,
    reason: str,
    confidence: str,
    domain: str | None = None,
    field: str | None = None,
) -> dict[str, Any]:
    return {
        **_base(row, domain=domain, field=field),
        "proposed_standard": standard,
        "proposed_concept_id": concept_id,
        "proposed_action": "accept",
        "reason": reason,
        "confidence": confidence,
    }


def build_proposals(queue_path: Path, inventory_path: Path | None = None) -> list[dict[str, Any]]:
    catalog = _catalog_by_key()
    proposals: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(item: dict[str, Any] | None) -> None:
        if not item:
            return
        key = (str(item.get("domain")), str(item.get("lookup_key")))
        if key in seen or not key[1]:
            return
        seen.add(key)
        proposals.append(item)

    for row in load_jsonl(queue_path):
        domain = row.get("domain")
        if domain == "symptom":
            add(propose_symptom(row, catalog))
        elif domain == "unit":
            add(propose_unit(row))
        elif domain == "drug":
            add(propose_drug(row))
        elif domain == "allergy":
            add(propose_allergy(row))
        elif domain == "rhythm":
            add(propose_rhythm(row))
        elif domain == "radiology":
            add(propose_exam(row))

    if inventory_path and inventory_path.is_file():
        labels_by_key: dict[str, list[dict[str, Any]]] = {}
        for row in load_jsonl(inventory_path):
            field = row.get("field")
            if field in {"chief_complaint", "ed_chief_complaint"}:
                parts = split_complaint(row.get("source") or "")
                if len(parts) <= 1:
                    add(propose_symptom({**row, "domain": "symptom", "field": field}, catalog))
                    continue
                for part in parts:
                    add(
                        propose_symptom(
                            {**row, "source": part, "domain": "symptom", "field": field},
                            catalog,
                        )
                    )
            elif field == "radiology.exam_name":
                add(propose_exam({**row, "domain": "radiology", "field": field}))
            elif field == "lab.label":
                key = lookup_key(row.get("source")) or ""
                labels_by_key.setdefault(key, []).append(row)
            elif field == "lab.valueuom":
                add(propose_unit({**row, "domain": "unit", "field": field}))
        for key, rows in labels_by_key.items():
            surfaces = {(r.get("source"), r.get("frequency")) for r in rows}
            if len(surfaces) < 2:
                continue
            canonical = max(rows, key=lambda r: int(r.get("frequency") or 0)).get("source")
            for row in rows:
                if row.get("source") != canonical:
                    add(propose_lab_label({**row, "domain": "lab"}, str(canonical)))
    proposals.sort(key=lambda row: (-int(row.get("frequency") or 0), str(row.get("domain")), str(row.get("source"))))
    return proposals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate review proposals for synonyms")
    parser.add_argument(
        "--queue",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/random10k_dev20_v1.0.9/review_queue.jsonl"),
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/random10k_dev20_v1.0.9/term_inventory.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/agent_proposals.jsonl"),
    )
    args = parser.parse_args(argv)
    rows = build_proposals(args.queue, args.inventory)
    atomic_write_jsonl(args.output, rows)
    print(f"proposals={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
