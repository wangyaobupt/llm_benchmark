"""Apply abbreviation/split rules to remaining low-frequency chief complaints
and correct already-accepted rows that violate those rules.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .exams import exam_display_name
from .propose import propose_exam, propose_symptom
from .symptoms import _alias_table
from .synonyms import (
    append_decision,
    compile_table_from_decisions,
    load_jsonl,
    write_synonym_table,
)
from .text import collapse_ws, lookup_key

SYMPTOM_CORRECTIONS: dict[str, dict[str, Any]] = {
    "___": {"action": "not_applicable", "standard": None, "concept_id": None},
    "bph": {
        "action": "accept",
        "standard": "Benign prostatic hyperplasia",
        "concept_id": "symptom:benign_prostatic_hyperplasia",
    },
    "esrd": {
        "action": "accept",
        "standard": "End-stage renal disease",
        "concept_id": "symptom:end_stage_renal_disease",
    },
    "nstemi": {
        "action": "accept",
        "standard": "Non-ST-elevation myocardial infarction",
        "concept_id": "symptom:non_st_elevation_myocardial_infarction",
    },
    "stemi": {
        "action": "accept",
        "standard": "ST-elevation myocardial infarction",
        "concept_id": "symptom:st_elevation_myocardial_infarction",
    },
    "pe": {
        "action": "accept",
        "standard": "Pulmonary embolism",
        "concept_id": "symptom:pulmonary_embolism",
    },
    "uti": {
        "action": "accept",
        "standard": "Urinary tract infection",
        "concept_id": "symptom:urinary_tract_infection",
    },
    "abnormal ekg": {
        "action": "accept",
        "standard": "Abnormal electrocardiogram",
        "concept_id": "symptom:abnormal_electrocardiogram",
    },
    "l flank pain": {
        "action": "accept",
        "standard": "Left flank pain",
        "concept_id": "symptom:left_flank_pain",
    },
    "l hip pain": {
        "action": "accept",
        "standard": "Left hip pain",
        "concept_id": "symptom:left_hip_pain",
    },
    "l leg pain": {
        "action": "accept",
        "standard": "Left leg pain",
        "concept_id": "symptom:left_leg_pain",
    },
    "r flank pain": {
        "action": "accept",
        "standard": "Right flank pain",
        "concept_id": "symptom:right_flank_pain",
    },
    "r foot pain": {
        "action": "accept",
        "standard": "Right foot pain",
        "concept_id": "symptom:right_foot_pain",
    },
    "r hip pain": {
        "action": "accept",
        "standard": "Right hip pain",
        "concept_id": "symptom:right_hip_pain",
    },
    "r leg pain": {
        "action": "accept",
        "standard": "Right leg pain",
        "concept_id": "symptom:right_leg_pain",
    },
    "rlq abdominal pain": {
        "action": "accept",
        "standard": "Right lower quadrant abdominal pain",
        "concept_id": "symptom:right_lower_quadrant_abdominal_pain",
    },
    "ruq abdominal pain": {
        "action": "accept",
        "standard": "Right upper quadrant abdominal pain",
        "concept_id": "symptom:right_upper_quadrant_abdominal_pain",
    },
    "ruq pain": {
        "action": "accept",
        "standard": "Right upper quadrant pain",
        "concept_id": "symptom:right_upper_quadrant_pain",
    },
    "s/p fall": {
        "action": "accept",
        "standard": "Status post fall",
        "concept_id": "symptom:status_post_fall",
    },
    "sob": {
        "action": "accept",
        "standard": "Shortness of breath",
        "concept_id": "symptom:dyspnea",
    },
    "shortness of breath": {
        "action": "accept",
        "standard": "Shortness of breath",
        "concept_id": "symptom:dyspnea",
    },
    "wound eval": {
        "action": "accept",
        "standard": "Wound evaluation",
        "concept_id": "symptom:wound_evaluation",
    },
    "chest pain (cardiac features)": {
        "action": "accept",
        "standard": "Chest pain (cardiac features)",
        "concept_id": "symptom:chest_pain",
    },
    "leg swelling": {
        "action": "accept",
        "standard": "Leg swelling",
        "concept_id": "symptom:leg_swelling",
    },
    "left sided weakness": {
        "action": "accept",
        "standard": "Left-sided weakness",
        "concept_id": "symptom:left_sided_weakness",
    },
    "right sided abdominal pain": {
        "action": "accept",
        "standard": "Right-sided abdominal pain",
        "concept_id": "symptom:right_sided_abdominal_pain",
    },
    "nausea/vomiting": {
        "action": "accept",
        "standard": "Nausea and vomiting",
        "concept_id": "symptom:nausea_vomiting",
    },
    "transfer": {"action": "not_applicable", "standard": None, "concept_id": None},
    "abd pain, transfer": {"action": "not_applicable", "standard": None, "concept_id": None},
    "abdominal pain, nausea, vomiting": {
        "action": "not_applicable",
        "standard": None,
        "concept_id": None,
    },
    "fever, cough": {"action": "not_applicable", "standard": None, "concept_id": None},
    "nausea, vomiting": {"action": "not_applicable", "standard": None, "concept_id": None},
}


def _decision(
    *,
    action: str,
    domain: str,
    field: str,
    source: str,
    standard: str | None,
    concept_id: str | None,
    frequency: Any = None,
    note: str,
) -> dict[str, Any]:
    return {
        "action": action,
        "domain": domain,
        "field": field,
        "source": source,
        "lookup_key": lookup_key(source),
        "standard": standard,
        "concept_id": concept_id,
        "frequency": frequency,
        "reviewer": "agent_rule_pass",
        "note": note,
    }


def run(
    *,
    queue_path: Path,
    inventory_path: Path,
    decisions_path: Path,
    table_path: Path,
) -> dict[str, int]:
    catalog = _alias_table(None)
    existing = load_jsonl(decisions_path)
    latest = {str(row.get("lookup_key")): row for row in existing if row.get("lookup_key")}
    written = 0

    def add(row: dict[str, Any]) -> None:
        nonlocal written
        key = row.get("lookup_key")
        if not key:
            return
        prev = latest.get(str(key))
        if prev and prev.get("action") == row.get("action") and prev.get("standard") == row.get("standard"):
            return
        append_decision(decisions_path, row)
        latest[str(key)] = row
        written += 1

    for key, fix in SYMPTOM_CORRECTIONS.items():
        prev = latest.get(key)
        source = (prev or {}).get("source") or key
        field = (prev or {}).get("field") or "chief_complaint"
        add(
            _decision(
                action=str(fix["action"]),
                domain="symptom",
                field=str(field),
                source=str(source),
                standard=fix.get("standard"),
                concept_id=fix.get("concept_id"),
                frequency=(prev or {}).get("frequency"),
                note="audit_accepted_symptom",
            )
        )

    syn_rows = load_jsonl(table_path)
    for row in syn_rows:
        if row.get("domain") != "radiology":
            continue
        source = collapse_ws(row.get("source")) or ""
        standard = collapse_ws(row.get("standard")) or ""
        if "radiography" not in standard.casefold() or "x-ray" in standard.casefold():
            continue
        now = exam_display_name(source)
        if not now or lookup_key(now) == lookup_key(standard):
            continue
        add(
            _decision(
                action="accept",
                domain="radiology",
                field="radiology.exam_name",
                source=source,
                standard=now,
                concept_id=f"exam:{lookup_key(now)}",
                note="audit_old_radiography_to_xray_views",
            )
        )

    for row in load_jsonl(queue_path):
        field = row.get("field")
        if field not in {"chief_complaint", "ed_chief_complaint"}:
            continue
        source = collapse_ws(row.get("source")) or ""
        key = lookup_key(source)
        if not key or key in latest:
            continue
        proposal = propose_symptom({**row, "domain": "symptom", "field": field}, catalog)
        if not proposal:
            continue
        action = proposal.get("proposed_action") or "accept"
        add(
            _decision(
                action=str(action),
                domain="symptom",
                field=str(field),
                source=source,
                standard=proposal.get("proposed_standard"),
                concept_id=proposal.get("proposed_concept_id"),
                frequency=row.get("frequency"),
                note="low_frequency_rule_pass",
            )
        )

    if inventory_path.is_file():
        for row in load_jsonl(inventory_path):
            if row.get("field") != "radiology.exam_name":
                continue
            source = collapse_ws(row.get("source")) or ""
            key = lookup_key(source)
            if not key or key in latest:
                continue
            proposal = propose_exam({**row, "domain": "radiology", "field": "radiology.exam_name"})
            if not proposal or proposal.get("proposed_action") == "not_applicable":
                continue
            add(
                _decision(
                    action="accept",
                    domain="radiology",
                    field="radiology.exam_name",
                    source=source,
                    standard=proposal.get("proposed_standard"),
                    concept_id=proposal.get("proposed_concept_id"),
                    frequency=row.get("frequency"),
                    note="low_frequency_exam_rule_pass",
                )
            )

    compiled = compile_table_from_decisions(load_jsonl(decisions_path))
    write_synonym_table(table_path, compiled)
    return {"new_decisions": written, "table_rows": len(compiled)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply remaining CC review and audit accepted rows")
    parser.add_argument(
        "--queue",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/random10k_dev20_v1.0.5/review_queue.jsonl"),
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/random10k_dev20_v1.0.5/term_inventory.jsonl"),
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
    stats = run(
        queue_path=args.queue,
        inventory_path=args.inventory,
        decisions_path=args.decisions,
        table_path=args.table,
    )
    print(
        f"new_decisions={stats['new_decisions']} table_rows={stats['table_rows']} "
        f"table={args.table}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
