"""Mine investigation rules from the methodology decision corpus (W7a)."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from .presentation import load_presentation_facts
from .ranking import benjamini_hochberg, contingency, fisher_greater, statistics


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = REPO_ROOT / "data/derived/investigation_timepoint/corpus_1000"
DEFAULT_EVENTS = (
    REPO_ROOT
    / "data/test_1000_0812/event_pipeline_output/aggregation/processed_events.parquet"
)
DEFAULT_OUTPUT = DEFAULT_CORPUS / "mining"
PROTOCOL = REPO_ROOT / "config/investigation-selection/protocol.yaml"

# First-stage construct: presenting symptoms/complaints -> investigation.
# Prior lab results are not conditions for this pass.
CONDITION_KINDS = {"symptom_reported"}


def _hash(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows) if rows else pa.table({"rule_id": pa.array([], type=pa.string())}), path)


def load_protocol_thresholds(path: Path = PROTOCOL) -> dict[str, Any]:
    protocol = yaml.safe_load(path.read_text(encoding="utf-8"))
    stats = protocol["scientific_protocol"]["statistical_policy"]
    validation = protocol["scientific_protocol"]["validation_policy"]
    return {
        "condition_subjects_min": int(stats["minimum_condition_support"]),
        "candidate_subjects_min": int(stats["minimum_candidate_support"]),
        "joint_subjects_min": int(stats["minimum_joint_support_post_fdr"]),
        "fdr_q": float(stats["fdr_q"]),
        "wilson_low_min": float(stats["wilson_lower_bound_minimum"]),
        "probability_gap_min": float(stats["probability_gap_minimum"]),
        "score_ratio_min": float(stats["score_ratio_minimum"]),
        "bootstrap_replicates": int(validation["bootstrap_replicates"]),
        "stability_min": float(validation["stability_minimum"]),
    }


def condition_token(row: Mapping[str, Any]) -> str | None:
    if row.get("event_kind") not in CONDITION_KINDS:
        return None
    name = row.get("preferred_name")
    if not isinstance(name, str):
        return None
    label = " ".join(name.strip().split())
    if len(label) < 3:
        return None
    return f"symptom_reported:name:{label.casefold()}"


def _index_rows(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(dict(row))
    return grouped


def presentation_for_decision(
    document: Mapping[str, Any],
    facts_by_hadm: Mapping[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Chief complaints are known at the first-wave freeze; they do not expire in 4h."""
    facts = facts_by_hadm.get(str(document.get("hadm_id") or ""), [])
    if document.get("decision_stage") == "first_wave":
        return facts
    index = document.get("index_time")
    if not index:
        return facts
    from datetime import datetime

    try:
        index_time = datetime.fromisoformat(str(index).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return facts
    kept = []
    for fact in facts:
        available = fact.get("available_time")
        if not available:
            continue
        try:
            available_time = datetime.fromisoformat(str(available).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue
        if available_time <= index_time:
            kept.append(fact)
    return kept


def build_family(
    documents: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    *,
    thresholds: Mapping[str, Any],
    presentation_by_hadm: Mapping[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    del evidence
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        by_class[str(document["candidate_class"])].append(document)
    facts_by_hadm = presentation_by_hadm or {}
    targets_by_decision = _index_rows(targets, "decision_id")
    family: list[dict[str, Any]] = []
    for candidate_class, class_docs in sorted(by_class.items()):
        universe_ids = [str(row["decision_id"]) for row in class_docs]
        subject_of = {str(row["decision_id"]): str(row["subject_id"]) for row in class_docs}
        condition_docs: dict[str, set[str]] = defaultdict(set)
        condition_label: dict[str, str] = {}
        for document in class_docs:
            decision_id = str(document["decision_id"])
            seen: set[str] = set()
            for ev in presentation_for_decision(document, facts_by_hadm):
                token = condition_token(ev)
                if not token or token in seen:
                    continue
                seen.add(token)
                condition_docs[token].add(decision_id)
                condition_label.setdefault(token, str(ev.get("preferred_name") or token))
        candidate_docs: dict[str, set[str]] = defaultdict(set)
        candidate_label: dict[str, str] = {}
        for document in class_docs:
            decision_id = str(document["decision_id"])
            for target in targets_by_decision.get(decision_id, []):
                candidate_id = str(target.get("candidate_id") or "")
                if not candidate_id:
                    continue
                if str(target.get("candidate_class") or document["candidate_class"]) != candidate_class:
                    continue
                candidate_docs[candidate_id].add(decision_id)
                candidate_label.setdefault(candidate_id, str(target.get("candidate_name") or candidate_id))

        def subject_count(decision_ids: Iterable[str]) -> int:
            return len({subject_of[decision_id] for decision_id in decision_ids if decision_id in subject_of})

        eligible_conditions = {
            token: docs
            for token, docs in condition_docs.items()
            if subject_count(docs) >= int(thresholds["condition_subjects_min"])
        }
        eligible_candidates = {
            candidate_id: docs
            for candidate_id, docs in candidate_docs.items()
            if subject_count(docs) >= int(thresholds["candidate_subjects_min"])
        }
        for token, x_docs in eligible_conditions.items():
            token_label = condition_label[token].casefold()
            for candidate_id, y_docs in eligible_candidates.items():
                if candidate_label[candidate_id].casefold() == token_label:
                    continue
                table = contingency(x_docs, y_docs, universe_ids)
                stats = statistics(table)
                p_value = fisher_greater(table.a, table.b, table.c, table.d)
                family.append({
                    "rule_id": "rule:" + _hash([candidate_class, token, candidate_id])[:24],
                    "family": candidate_class,
                    "condition_id": token,
                    "condition_name": condition_label[token],
                    "candidate_id": candidate_id,
                    "candidate_name": candidate_label[candidate_id],
                    "candidate_class": candidate_class,
                    "n_total": stats["n_total"],
                    "n_x": stats["n_x"],
                    "n_y": stats["n_y"],
                    "n_xy": stats["n_xy"],
                    "n_x_subjects": subject_count(x_docs),
                    "n_y_subjects": subject_count(y_docs),
                    "n_xy_subjects": subject_count(set(x_docs) & set(y_docs)),
                    "p_value": p_value,
                    **{key: stats[key] for key in ("probability", "lift", "log_rr", "shrunk_log_rr", "wilson_low", "wilson_high")},
                    "x_docs": sorted(x_docs),
                    "y_docs": sorted(y_docs),
                    "universe": universe_ids,
                    "subject_of": subject_of,
                })
    family.sort(key=lambda row: (row["family"], row["p_value"], row["rule_id"]))
    return family


def apply_fdr(family: list[dict[str, Any]], *, q_max: float) -> list[dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in family:
        by_family[row["family"]].append(row)
    kept: list[dict[str, Any]] = []
    for family_name, rows in by_family.items():
        manifest = benjamini_hochberg({row["rule_id"]: row["p_value"] for row in rows}, family=family_name)
        for row in rows:
            q_value = manifest["q_values"][row["rule_id"]]
            annotated = {**row, "q_value": q_value, "family_sha256": manifest["family_sha256"]}
            if q_value <= q_max:
                kept.append(annotated)
    return kept


def bootstrap_stability(
    rows: list[dict[str, Any]],
    *,
    replicates: int,
    seed: int = 20260819,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    out: list[dict[str, Any]] = []
    for row in rows:
        subject_of: dict[str, str] = row["subject_of"]
        subjects = sorted(set(subject_of.values()))
        decisions_by_subject: dict[str, list[str]] = defaultdict(list)
        for decision_id, subject in subject_of.items():
            decisions_by_subject[subject].append(decision_id)
        x_docs = set(row["x_docs"])
        y_docs = set(row["y_docs"])
        positive = 0
        for _ in range(replicates):
            sampled_docs: list[str] = []
            for subject in (rng.choice(subjects) for _ in range(len(subjects))):
                sampled_docs.extend(decisions_by_subject[subject])
            table = contingency(x_docs, y_docs, sampled_docs)
            if statistics(table)["shrunk_log_rr"] > 0:
                positive += 1
        out.append({**row, "bootstrap_direction_stability": positive / replicates if replicates else 0.0})
    return out


def validate_rules(
    rows: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    *,
    support_min: int,
) -> list[dict[str, Any]]:
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        by_class[str(document["candidate_class"])].append(document)
    evidence_by_decision = _index_rows(evidence, "decision_id")
    targets_by_decision = _index_rows(targets, "decision_id")
    reports: list[dict[str, Any]] = []
    for row in rows:
        class_docs = by_class.get(row["candidate_class"], [])
        if not class_docs:
            reports.append({**row, "validation_status": "inconclusive", "validation_reason": "VALIDATION_MISSING_CANDIDATE"})
            continue
        universe = [str(doc["decision_id"]) for doc in class_docs]
        subject_of = {str(doc["decision_id"]): str(doc["subject_id"]) for doc in class_docs}
        x_docs: set[str] = set()
        y_docs: set[str] = set()
        for document in class_docs:
            decision_id = str(document["decision_id"])
            tokens = {condition_token(ev) for ev in evidence_by_decision.get(decision_id, [])}
            if row["condition_id"] in tokens:
                x_docs.add(decision_id)
            for target in targets_by_decision.get(decision_id, []):
                if str(target.get("candidate_id")) == row["candidate_id"]:
                    y_docs.add(decision_id)
        if not y_docs:
            reports.append({**row, "validation_status": "inconclusive", "validation_reason": "VALIDATION_MISSING_CANDIDATE"})
            continue
        table = contingency(x_docs, y_docs, universe)
        if table.n_x == 0:
            reports.append({**row, "validation_status": "inconclusive", "validation_reason": "VALIDATION_ZERO_DENOMINATOR"})
            continue
        joint_subjects = len({subject_of[decision_id] for decision_id in set(x_docs) & set(y_docs) if decision_id in subject_of})
        if joint_subjects < support_min:
            reports.append({**row, "validation_status": "inconclusive", "validation_reason": "VALIDATION_INCONCLUSIVE", "validation_n_xy": table.n_xy, "validation_joint_subjects": joint_subjects})
            continue
        val_stats = statistics(table)
        if (row["shrunk_log_rr"] > 0) != (val_stats["shrunk_log_rr"] > 0):
            status, reason = "failed", "VALIDATION_DIRECTION_REVERSED"
        else:
            status, reason = "validated", ""
        reports.append({
            **row,
            "validation_status": status,
            "validation_reason": reason,
            "validation_n_x": val_stats["n_x"],
            "validation_n_y": val_stats["n_y"],
            "validation_n_xy": val_stats["n_xy"],
            "validation_shrunk_log_rr": val_stats["shrunk_log_rr"],
            "validation_lift": val_stats["lift"],
            "validation_joint_subjects": joint_subjects,
        })
    return reports


def _public(row: Mapping[str, Any]) -> dict[str, Any]:
    skip = {"x_docs", "y_docs", "universe", "subject_of"}
    return {key: value for key, value in row.items() if key not in skip}


def mine_corpus(
    corpus_dir: Path,
    output_dir: Path,
    *,
    events_path: Path | None = None,
    bootstrap_replicates: int | None = None,
) -> dict[str, Any]:
    thresholds = load_protocol_thresholds()
    if bootstrap_replicates is not None:
        thresholds["bootstrap_replicates"] = bootstrap_replicates
    documents = pq.read_table(corpus_dir / "decision_documents.parquet").to_pylist()
    if any(row.get("decision_stage") == "first_wave" for row in documents):
        documents = [row for row in documents if row.get("decision_stage") == "first_wave"]
    targets = pq.read_table(corpus_dir / "decision_targets.parquet").to_pylist()
    presentation = load_presentation_facts(events_path or DEFAULT_EVENTS)
    # This 1,000-admission extract is a mining sample, not a validation holdout.
    family = build_family(
        documents,
        [],
        targets,
        thresholds=thresholds,
        presentation_by_hadm=presentation,
    )
    after_fdr = apply_fdr(family, q_max=float(thresholds["fdr_q"]))
    after_joint = [row for row in after_fdr if row["n_xy_subjects"] >= int(thresholds["joint_subjects_min"])]
    bootstrapped = bootstrap_stability(
        after_joint,
        replicates=int(thresholds["bootstrap_replicates"]),
    )
    stable = [row for row in bootstrapped if row["bootstrap_direction_stability"] >= float(thresholds["stability_min"])]
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_parquet(output_dir / "rule_family.parquet", [_public(row) for row in family])
    _write_parquet(output_dir / "rule_statistics.parquet", [_public(row) for row in after_joint])
    _write_parquet(output_dir / "rule_bootstrap.parquet", [_public(row) for row in bootstrapped])
    mined = [{**_public(row), "rule_status": "mined_unvalidated"} for row in stable]
    _write_parquet(output_dir / "mined_rules.parquet", mined)
    summary = {
        "schema_version": "investigation-rule-mining/1.1.0",
        "corpus_dir": str(corpus_dir),
        "gold_count": 0,
        "condition_space": "presentation_complaint_to_investigation",
        "thresholds": thresholds,
        "presentation_hadms": len(presentation),
        "counts": {
            "mining_documents": len(documents),
            "mining_subjects": len({row["subject_id"] for row in documents}),
            "family_pairs": len(family),
            "fdr_passed": len(after_fdr),
            "joint_passed": len(after_joint),
            "bootstrap_stable": len(stable),
        },
        "note": (
            "All 1,000 admissions are used for mining; there is no validation holdout "
            "on this sample. First-stage index is the earliest labevents/radiology "
            "charttime. Candidates are specific lab labels and radiology exam_name "
            "values. Conditions are ED chief-complaint tokens. Not gold."
        ),
    }
    summary["content_sha256"] = _hash(summary)
    _write_json(output_dir / "mining_manifest.json", summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mine investigation rules from the decision corpus.")
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bootstrap-replicates", type=int)
    return parser


def main() -> int:
    args = _parser().parse_args()
    summary = mine_corpus(
        args.corpus_dir,
        args.output_dir,
        events_path=args.events,
        bootstrap_replicates=args.bootstrap_replicates,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
