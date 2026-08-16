"""Generic single-class benchmark task framework.

A task provides a candidate frame (hadm_id -> candidate) plus a stem template;
this module computes the behavioral gold (selectivity / PSR / likelihood),
validates it on independent patients, and builds MCQ questions.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from benchmark_common.stats import (
    wilson_lower, binomial_greater_pvalue, benjamini_hochberg,
)


def build_single_class_gold(
    events: pd.DataFrame,
    cond: pd.DataFrame,
    candidate_frame: pd.DataFrame,
    class_name: str,
    gold_semantics: str = "selectivity",
    min_condition_support: int = 10,
    max_baseline_share: float = 0.5,
    min_candidate_support: int = 20,
    fdr_q: float = 0.10,
    score_ratio_minimum: float = 1.5,
    min_share_gap: float = 0.05,
    min_gold_share: float = 0.0,
    psr_nco_min: int = 10,
    psr_p_min: float = 0.005,
    psr_r: float = 1.0,
) -> list[dict]:
    merged = cond.merge(candidate_frame, on="hadm_id", how="inner")
    pair = (merged.groupby(["condition", "candidate"], dropna=True)
                  .agg(n_adm=("hadm_id", "nunique")).reset_index())
    cond_support = merged.groupby("condition")["hadm_id"].nunique()
    base = candidate_frame.groupby("candidate")["hadm_id"].nunique().rename("baseline_adm")
    total_adm = cond["hadm_id"].nunique()

    frames: list[pd.DataFrame] = []
    for cname, csup in cond_support.items():
        if csup < min_condition_support:
            continue
        sub = pair[pair["condition"] == cname].merge(base, on="candidate", how="left")
        sub["share"] = sub["n_adm"] / csup
        sub["baseline_share"] = sub["baseline_adm"] / total_adm
        sub["selectivity"] = sub["share"] / sub["baseline_share"].replace(0, float("nan"))
        sub = sub[sub["baseline_share"] <= max_baseline_share]
        sub = sub[sub["baseline_adm"] >= min_candidate_support]
        sub = sub.assign(condition=cname, condition_support=int(csup))
        frames.append(sub)
    if not frames:
        return []
    df = pd.concat(frames, ignore_index=True)
    if df.empty:
        return []

    df["p_value"] = [
        binomial_greater_pvalue(int(k), int(n), float(p0))
        for k, n, p0 in zip(df["n_adm"], df["condition_support"], df["baseline_share"])
    ]
    df["q_value"] = 0.0
    for cname, grp in df.groupby("condition"):
        df.loc[grp.index, "q_value"] = benjamini_hochberg(grp["p_value"].tolist())
    df["wilson_lower"] = [
        wilson_lower(int(k), int(n)) for k, n in zip(df["n_adm"], df["condition_support"])
    ]
    df["reliability"] = [
        math.log10(max(1.0, 1 + int(k) - psr_nco_min)) + psr_r for k in df["n_adm"]
    ]
    df["psr"] = df["share"] * df["selectivity"] * df["reliability"]

    if gold_semantics == "psr":
        df = df[(df["n_adm"] >= psr_nco_min) & (df["share"] >= psr_p_min)]
        rank_col, gold_basis = "psr", "behavioral_psr"
    elif gold_semantics == "selectivity":
        df = df[df["q_value"] <= fdr_q]
        df = df[df["selectivity"] >= score_ratio_minimum]
        rank_col, gold_basis = "selectivity", "behavioral_most_selective_fdr"
    else:
        rank_col, gold_basis = "share", "behavioral_most_likely"

    rows: list[dict] = []
    for cname, grp in df.groupby("condition"):
        grp = grp.sort_values(rank_col, ascending=False)
        top = grp.head(5)
        if top.empty:
            continue
        # uniqueness filter: drop when top-2 shares are too close (ambiguous
        # answer, "多专科合理性 ~10pp" from the survey).
        if len(top) >= 2 and top.iloc[0]["share"] - top.iloc[1]["share"] < min_share_gap:
            continue
        g = top.iloc[0]
        # absolute-share floor: drop rare categories whose lift is inflated by
        # a tiny baseline (e.g. spurious "vaccine" / "antigout" gold).
        if g["share"] < min_gold_share:
            continue
        rows.append({
            "class": class_name,
            "condition": cname,
            "condition_support": int(top.iloc[0]["condition_support"]),
            "gold_candidate": g["candidate"],
            "gold_share": round(float(g["share"]), 4),
            "gold_selectivity": round(float(g["selectivity"]), 3)
                                if pd.notna(g["selectivity"]) else None,
            "gold_psr": round(float(g["psr"]), 3),
            "gold_basis": gold_basis,
            "top_candidates": [
                {"candidate": r["candidate"], "n_adm": int(r["n_adm"]),
                 "share": round(float(r["share"]), 4),
                 "selectivity": round(float(r["selectivity"]), 3)
                                if pd.notna(r["selectivity"]) else None,
                 "psr": round(float(r["psr"]), 3)}
                for _, r in top.iterrows()
            ],
        })
    return rows


def make_questions(gold_rows: list[dict], pool: list[str], stem_fn,
                   class_name: str, n_options: int = 4) -> list[dict]:
    qs = []
    for i, g in enumerate(gold_rows, start=1):
        gold = g["gold_candidate"]
        distractors = [c for c in pool if c != gold][: n_options - 1]
        if len(distractors) < n_options - 1:
            continue
        options = [gold] + distractors
        qs.append({
            "question_id": f"q_{class_name}_{i:04d}",
            "task": class_name,
            "comparison_class": class_name,
            "condition": g["condition"],
            "condition_support": g["condition_support"],
            "stem": stem_fn(g["condition"]),
            "options": options,
            "answer_index": 0,
            "answer": gold,
            "gold_basis": g["gold_basis"],
            "status": "exploratory_unreviewed",
            "candidate_counts": g["top_candidates"],
        })
    return qs


COLS = ["event_id", "subject_id", "hadm_id", "event_kind", "entity_type",
        "source_table", "source_array_index", "source_label", "preferred_name",
        "source_concept_id", "concept_id", "assertion"]


def run_task(events_path, split_path, candidate_fn, pool_fn, stem_fn, class_name,
             role: str = "development", gold_semantics: str = "selectivity",
             min_share_gap: float = 0.05, min_gold_share: float = 0.0,
             out_dir=None) -> dict:
    """Full behavioral-gold pipeline: load -> filter -> gold -> questions -> validate.

    Writes summary.json / questions.jsonl / gold_patterns.jsonl /
    run_manifest.json to out_dir.
    """
    from benchmark_common import extract_conditions, _verify_normalized_events, _sha256_file
    import pyarrow.parquet as pq

    events_path = Path(events_path)
    split_path = Path(split_path)
    events_hash = _verify_normalized_events(events_path)
    split_hash = _sha256_file(split_path)

    split = pd.read_parquet(split_path)
    subjects = set(split[split["role"] == role]["subject_id"].astype(str))
    events = pq.read_table(events_path, columns=COLS).to_pandas()
    events = events[events["subject_id"].astype(str).isin(subjects)]

    cond = extract_conditions(events)
    candidate_frame = candidate_fn(events)
    gold = build_single_class_gold(events, cond, candidate_frame, class_name,
                                   gold_semantics=gold_semantics,
                                   min_share_gap=min_share_gap,
                                   min_gold_share=min_gold_share)
    pool = pool_fn(events)
    questions = make_questions(gold, pool, stem_fn, class_name)

    summary = {
        "status": "exploratory_unreviewed",
        "task": class_name,
        "gold_semantics": gold_semantics,
        "gold_track": "behavioral",
        "split_role": role,
        "events_path": str(events_path), "events_sha256": events_hash,
        "split_path": str(split_path), "split_sha256": split_hash,
        "admissions_total": int(events["hadm_id"].nunique()),
        "subjects_total": int(events["subject_id"].nunique()),
        "admissions_with_condition": int(cond["hadm_id"].nunique()),
        "n_gold_patterns": len(gold), "n_questions": len(questions),
        "gold_patterns": gold, "questions": questions,
    }
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "questions.jsonl").write_text(
            "\n".join(json.dumps(q, ensure_ascii=False) for q in questions) + "\n",
            encoding="utf-8")
        (out_dir / "gold_patterns.jsonl").write_text(
            "\n".join(json.dumps(g, ensure_ascii=False) for g in gold) + "\n",
            encoding="utf-8")
        (out_dir / "run_manifest.json").write_text(json.dumps({
            "schema": "benchmark-task-exploratory-manifest/1.0.0",
            "status": "exploratory_unreviewed",
            "task": class_name, "gold_semantics": gold_semantics,
            "gold_track": "behavioral",
            "input": {"path": str(events_path), "sha256": events_hash},
            "split": {"path": str(split_path), "sha256": split_hash, "role": role},
            "counts": {"admissions_total": summary["admissions_total"],
                       "n_gold_patterns": len(gold), "n_questions": len(questions)},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def validate_single_class(dev_gold: list[dict], events: pd.DataFrame,
                          candidate_frame: pd.DataFrame,
                          min_condition_support: int = 10,
                          max_baseline_share: float = 0.5,
                          min_candidate_support: int = 20,
                          psr_nco_min: int = 10, psr_p_min: float = 0.005) -> dict:
    """Recompute ranking on validation events; record gold candidate's rank."""
    from benchmark_common.conditions import extract_conditions
    cond = extract_conditions(events)
    base = candidate_frame.groupby("candidate")["hadm_id"].nunique().rename("baseline_adm")
    total_adm = cond["hadm_id"].nunique()

    results = []
    for g in dev_gold:
        condition, gold = g["condition"], g["gold_candidate"]
        cond_adm = cond[cond["condition"] == condition]
        if cond_adm.empty:
            results.append({"condition": condition, "gold_candidate": gold,
                            "status": "condition_absent"})
            continue
        csup = int(cond_adm["hadm_id"].nunique())
        if csup < min_condition_support:
            results.append({"condition": condition, "gold_candidate": gold,
                            "status": "insufficient_support", "validation_support": csup})
            continue
        merged = cond_adm.merge(candidate_frame, on="hadm_id", how="inner")
        pair = merged.groupby("candidate")["hadm_id"].nunique().reset_index(name="n_adm")
        pair = pair.merge(base, on="candidate", how="left")
        pair = pair[pair["baseline_adm"] >= min_candidate_support]
        pair["share"] = pair["n_adm"] / csup
        pair["baseline_share"] = pair["baseline_adm"] / total_adm
        pair["selectivity"] = pair["share"] / pair["baseline_share"].replace(0, float("nan"))
        pair = pair[pair["baseline_share"] <= max_baseline_share]
        pair["reliability"] = [
            math.log10(max(1.0, 1 + int(k) - psr_nco_min)) + 1.0 for k in pair["n_adm"]
        ]
        pair["psr"] = pair["share"] * pair["selectivity"] * pair["reliability"]
        # rank by the same semantics as the gold
        gs = g.get("gold_basis", "")
        rank_col = "psr" if "psr" in gs else ("share" if "likelihood" in gs else "selectivity")
        pair = pair.sort_values(rank_col, ascending=False).reset_index(drop=True)
        if pair.empty:
            results.append({"condition": condition, "gold_candidate": gold,
                            "status": "no_eligible_candidate", "validation_support": csup})
            continue
        idx = pair.index[pair["candidate"] == gold]
        rank = int(idx[0]) + 1 if len(idx) else None
        results.append({
            "condition": condition, "gold_candidate": gold, "status": "checked",
            "validation_support": csup, "gold_rank": rank,
            "top_candidate_validation": pair.iloc[0]["candidate"],
            "concordant_rank1": rank == 1,
            "concordant_top3": rank is not None and rank <= 3,
        })

    checked = [r for r in results if r.get("status") == "checked"]
    n = len(checked)
    return {
        "summary": {
            "n_rules": len(dev_gold), "n_checked": n,
            "n_condition_absent": sum(1 for r in results if r.get("status") == "condition_absent"),
            "n_insufficient": sum(1 for r in results if r.get("status") == "insufficient_support"),
            "rank1_concordance": round(sum(1 for r in checked if r["concordant_rank1"]) / n, 4) if n else None,
            "top3_concordance": round(sum(1 for r in checked if r["concordant_top3"]) / n, 4) if n else None,
        },
        "results": results,
    }


def validate_task(events_path, split_path, dev_gold_path, candidate_fn,
                  out_dir=None, role: str = "validation",
                  min_condition_support: int = 10,
                  max_baseline_share: float = 0.5,
                  min_candidate_support: int = 20) -> dict:
    """Validate development gold rules on a held-out split (fail-closed)."""
    from benchmark_common import _verify_normalized_events, _sha256_file
    import pyarrow.parquet as pq

    events_path = Path(events_path)
    split_path = Path(split_path)
    events_hash = _verify_normalized_events(events_path)
    split_hash = _sha256_file(split_path)
    dev_gold = [json.loads(l) for l in Path(dev_gold_path).read_text(encoding="utf-8").splitlines() if l.strip()]

    split = pd.read_parquet(split_path)
    subjects = set(split[split["role"] == role]["subject_id"].astype(str))
    events = pq.read_table(events_path, columns=COLS).to_pandas()
    events = events[events["subject_id"].astype(str).isin(subjects)]

    out = validate_single_class(
        dev_gold, events, candidate_fn(events),
        min_condition_support=min_condition_support,
        max_baseline_share=max_baseline_share,
        min_candidate_support=min_candidate_support,
    )
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "validation_summary.json").write_text(json.dumps({
            "events_sha256": events_hash, "split_sha256": split_hash,
            "summary": out["summary"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "validation_results.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in out["results"]) + "\n",
            encoding="utf-8")
    return out


def build_validated(questions_path, validation_path, out_dir=None) -> dict:
    """Filter questions to validation-stable rules (rank-1 / top-3)."""
    questions_path = Path(questions_path)
    validation_path = Path(validation_path)
    val = [json.loads(l) for l in validation_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    val_by_key = {(r["condition"], r["gold_candidate"]): r for r in val}
    qs = [json.loads(l) for l in questions_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    rank1, top3, dropped = [], [], []
    for q in qs:
        v = val_by_key.get((q["condition"], q["answer"]))
        if v is None or v.get("status") != "checked":
            dropped.append(("uncheckable", q))
            continue
        q = dict(q)
        q["validation_status"] = "rank1_stable" if v["concordant_rank1"] else "top3_stable"
        q["validation_gold_rank"] = v["gold_rank"]
        if v["concordant_rank1"]:
            rank1.append(q); top3.append(q)
        elif v["concordant_top3"]:
            top3.append(q)
        else:
            dropped.append(("discordant", q))

    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, subset in (("validated_rank1.jsonl", rank1),
                             ("validated_top3.jsonl", top3)):
            (out_dir / name).write_text(
                "\n".join(json.dumps(x, ensure_ascii=False) for x in subset) + "\n",
                encoding="utf-8")
        (out_dir / "validated_manifest.json").write_text(json.dumps({
            "status": "exploratory_unreviewed",
            "n_development_questions": len(qs),
            "n_rank1_validated": len(rank1),
            "n_top3_validated": len(top3),
            "n_dropped_uncheckable": sum(1 for s, _ in dropped if s == "uncheckable"),
            "n_dropped_discordant": sum(1 for s, _ in dropped if s == "discordant"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"rank1": len(rank1), "top3": len(top3), "dropped": len(dropped)}
