"""Accept remaining review rows, then merge surface forms of the same concept."""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .abbrev import expand_for_display
from .drugs import resolve_drug_ingredients
from .exams import exam_display_name
from .mappings import SYMPTOM_ALIASES
from .propose import (
    propose_allergy,
    propose_drug,
    propose_exam,
    propose_rhythm,
    propose_symptom,
    propose_unit,
)
from .symptoms import _alias_table
from .synonyms import append_decisions, compile_table_from_decisions, load_jsonl, write_synonym_table
from .text import collapse_ws, lookup_key

_HYPHEN = re.compile(r"[-_]+")
_BRITISH = (
    ("distension", "distention"),
    ("oedema", "edema"),
    ("dyspnoea", "dyspnea"),
    ("haemorrhage", "hemorrhage"),
    ("haem", "hem"),
)


def _decision_from_proposal(row: dict[str, Any], proposal: dict[str, Any], note: str) -> dict[str, Any]:
    action = str(proposal.get("proposed_action") or "accept")
    return {
        "action": action,
        "domain": proposal.get("domain") or row.get("domain"),
        "field": proposal.get("field") or row.get("field"),
        "source": collapse_ws(row.get("source")) or row.get("source"),
        "lookup_key": lookup_key(row.get("source")),
        "standard": proposal.get("proposed_standard"),
        "concept_id": proposal.get("proposed_concept_id"),
        "frequency": row.get("frequency"),
        "reviewer": "agent_auto_accept",
        "note": note,
    }


def accept_remaining(queue_path: Path, decisions_path: Path) -> int:
    latest = {
        (str(row.get("domain") or "symptom"), str(row.get("lookup_key"))): row
        for row in load_jsonl(decisions_path)
        if row.get("lookup_key")
    }
    catalog = _alias_table(None)
    pending: list[dict[str, Any]] = []
    for row in load_jsonl(queue_path):
        source = collapse_ws(row.get("source")) or ""
        key = lookup_key(source)
        domain = str(row.get("domain") or "symptom")
        if not key or (domain, key) in latest:
            continue
        proposal = None
        if domain == "symptom":
            proposal = propose_symptom({**row, "source": source}, catalog)
        elif domain == "radiology":
            proposal = propose_exam({**row, "source": source})
        elif domain == "unit":
            proposal = propose_unit({**row, "source": source})
        elif domain == "drug":
            proposal = propose_drug({**row, "source": source})
        elif domain == "allergy":
            proposal = propose_allergy({**row, "source": source})
        elif domain == "rhythm":
            proposal = propose_rhythm({**row, "source": source})
        elif domain == "lab":
            display = expand_for_display(source)
            proposal = {
                "domain": "lab",
                "field": row.get("field") or "lab.label",
                "proposed_action": "accept",
                "proposed_standard": display,
                "proposed_concept_id": f"lab:{lookup_key(display)}",
            }
        if not proposal:
            continue
        item = _decision_from_proposal(row, proposal, "auto_accept_remaining")
        pending.append(item)
        latest[(str(item.get("domain") or domain), str(item["lookup_key"]))] = item
    append_decisions(decisions_path, pending)
    return len(pending)


def _symptom_merge_key(text: str, catalog: dict[str, tuple[str, str]]) -> str:
    display = expand_for_display(text)
    key = lookup_key(display) or ""
    key = _HYPHEN.sub(" ", key)
    key = collapse_ws(key) or ""
    for british, american in _BRITISH:
        key = key.replace(british, american)
    if key.endswith("es") and key[:-2] in catalog:
        return lookup_key(catalog[key[:-2]][0]) or key[:-2]
    if key.endswith("s") and key[:-1] in catalog:
        return lookup_key(catalog[key[:-1]][0]) or key[:-1]
    mapped = catalog.get(key)
    if mapped:
        return lookup_key(mapped[0]) or key
    return key


def _pick_symptom_canonical(
    group: list[dict[str, Any]],
    catalog: dict[str, tuple[str, str]],
) -> tuple[str, str]:
    merge_key = _symptom_merge_key(str(group[0].get("standard") or group[0].get("source") or ""), catalog)
    if merge_key in SYMPTOM_ALIASES:
        return SYMPTOM_ALIASES[merge_key]
    if merge_key in catalog:
        return catalog[merge_key]
    for row in group:
        standard = collapse_ws(row.get("standard")) or ""
        if lookup_key(standard) == merge_key and standard:
            return standard, str(row.get("concept_id") or f"symptom:{merge_key}")
    display = expand_for_display(str(group[0].get("standard") or group[0].get("source") or ""))
    return display, str(group[0].get("concept_id") or f"symptom:{merge_key}")


def _catalog_with_accepted(latest: dict[str, dict[str, Any]]) -> dict[str, tuple[str, str]]:
    extra: dict[str, tuple[str, str]] = {}
    for row in latest.values():
        if row.get("action") != "accept" or row.get("domain") not in {None, "symptom"}:
            continue
        standard = collapse_ws(row.get("standard"))
        concept_id = row.get("concept_id")
        if not standard or not concept_id:
            continue
        pair = (str(standard), str(concept_id))
        source_key = lookup_key(row.get("source"))
        standard_key = lookup_key(standard)
        if source_key:
            extra[source_key] = pair
        if standard_key:
            extra[standard_key] = pair
    return _alias_table(extra)


def merge_similar(decisions_path: Path, table_path: Path) -> int:
    latest = {
        (str(row.get("domain") or "symptom"), str(row.get("lookup_key"))): row
        for row in load_jsonl(decisions_path)
        if row.get("lookup_key")
    }
    catalog = _catalog_with_accepted({str(key[1]): row for key, row in latest.items() if key[0] == "symptom"})
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in latest.values():
        if row.get("action") != "accept" or not row.get("standard"):
            continue
        domain = str(row.get("domain") or "symptom")
        source = str(row.get("source") or "")
        standard = str(row.get("standard") or "")
        if domain == "symptom":
            merge_key = _symptom_merge_key(standard or source, catalog)
        elif domain == "radiology":
            merge_key = lookup_key(exam_display_name(source) or standard) or ""
        elif domain == "drug":
            ingredients = resolve_drug_ingredients(source)
            merge_key = lookup_key(" | ".join(ingredients) if ingredients else standard) or ""
        elif domain == "allergy":
            merge_key = lookup_key(expand_for_display(source) or standard) or ""
        elif domain == "rhythm":
            merge_key = lookup_key(expand_for_display(source) or standard) or ""
        else:
            merge_key = lookup_key(standard) or ""
        if merge_key:
            groups[(domain, merge_key)].append(row)

    pending: list[dict[str, Any]] = []
    for (domain, _merge_key), group in groups.items():
        if domain == "symptom":
            canonical, concept_id = _pick_symptom_canonical(group, catalog)
        elif domain == "radiology":
            canonical = exam_display_name(str(group[0].get("source") or "")) or str(group[0].get("standard") or "")
            concept_id = f"exam:{lookup_key(canonical)}"
        elif domain == "drug":
            ingredients = resolve_drug_ingredients(str(group[0].get("source") or ""))
            canonical = " | ".join(ingredients) if ingredients else str(group[0].get("standard") or "")
            concept_id = f"drug:{lookup_key(ingredients[0]) if ingredients else canonical}"
        elif domain == "allergy":
            canonical = expand_for_display(str(group[0].get("standard") or group[0].get("source") or ""))
            if lookup_key(canonical) in {"no known allergies"}:
                canonical, concept_id = "No known allergies", "allergy:nka"
            else:
                concept_id = f"allergy:{lookup_key(canonical)}"
        elif domain == "rhythm":
            canonical = str(group[0].get("standard") or expand_for_display(str(group[0].get("source") or "")))
            concept_id = f"rhythm:{lookup_key(canonical)}"
        else:
            continue
        if not canonical:
            continue
        for row in group:
            if row.get("standard") == canonical and row.get("concept_id") == concept_id:
                continue
            pending.append(
                {
                    "action": "accept",
                    "domain": domain,
                    "field": row.get("field"),
                    "source": row.get("source"),
                    "lookup_key": row.get("lookup_key"),
                    "standard": canonical,
                    "concept_id": concept_id,
                    "frequency": row.get("frequency"),
                    "reviewer": "agent_merge_similar",
                    "note": "merge_same_concept",
                }
            )
    append_decisions(decisions_path, pending)
    compiled = compile_table_from_decisions(load_jsonl(decisions_path))
    write_synonym_table(table_path, compiled)
    return len(pending)


def run(*, queue_path: Path, decisions_path: Path, table_path: Path) -> dict[str, int]:
    accepted = accept_remaining(queue_path, decisions_path)
    merged = merge_similar(decisions_path, table_path)
    compiled = compile_table_from_decisions(load_jsonl(decisions_path))
    return {
        "auto_accepted": accepted,
        "merged": merged,
        "table_rows": len(compiled),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-accept remaining review rows and merge synonyms")
    parser.add_argument(
        "--queue",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/random10k_dev20_v1.0.5/review_queue.jsonl"),
    )
    parser.add_argument(
        "--decisions",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/synonym_decisions.jsonl"),
    )
    parser.add_argument(
        "--table",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/reviewed_synonyms.jsonl"),
    )
    args = parser.parse_args(argv)
    stats = run(queue_path=args.queue, decisions_path=args.decisions, table_path=args.table)
    print(
        f"auto_accepted={stats['auto_accepted']} merged={stats['merged']} "
        f"table_rows={stats['table_rows']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
