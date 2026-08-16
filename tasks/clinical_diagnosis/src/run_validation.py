"""Validate clinical-diagnosis gold rules on the VALIDATION split (PSR rank)."""
import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from diagnosis import primary_diagnosis
from benchmark_common import (
    extract_conditions, _verify_normalized_events, _sha256_file,
    binomial_greater_pvalue, benjamini_hochberg,
)

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")
DEV_GOLD = Path(r"D:\Projects\llm_benchmark\tasks\clinical_diagnosis\output\development\gold_patterns.jsonl")
BASE = Path(r"D:\Projects\llm_benchmark\tasks\clinical_diagnosis\output")

COLS = ["event_id", "subject_id", "hadm_id", "event_kind", "entity_type",
        "source_table", "source_array_index", "source_label",
        "preferred_name", "source_concept_id", "concept_id", "assertion"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", type=Path, default=EVENTS)
    ap.add_argument("--split", type=Path, default=SPLIT)
    ap.add_argument("--dev-gold", type=Path, default=DEV_GOLD)
    ap.add_argument("--role", default="validation", choices=["validation", "final_test"])
    ap.add_argument("--min-condition-support", type=int, default=10)
    args = ap.parse_args()
    out_dir = BASE / args.role

    events_hash = _verify_normalized_events(args.events)
    split_hash = _sha256_file(args.split)
    dev_gold = [json.loads(l) for l in args.dev_gold.read_text(encoding="utf-8").splitlines() if l.strip()]

    split = pd.read_parquet(args.split)
    val_subjects = set(split[split["role"] == args.role]["subject_id"].astype(str))
    events = pq.read_table(args.events, columns=COLS).to_pandas()
    events = events[events["subject_id"].astype(str).isin(val_subjects)]

    cond = extract_conditions(events)
    order_frame = primary_diagnosis(events)
    base = order_frame.groupby("candidate")["hadm_id"].nunique().rename("baseline_adm")
    total_adm = cond["hadm_id"].nunique()

    results = []
    for g in dev_gold:
        condition, gold = g["condition"], g["gold_candidate"]
        cond_adm = cond[cond["condition"] == condition]
        if cond_adm.empty:
            results.append({"condition": condition, "gold_candidate": gold, "status": "condition_absent"})
            continue
        csup = int(cond_adm["hadm_id"].nunique())
        if csup < args.min_condition_support:
            results.append({"condition": condition, "gold_candidate": gold,
                            "status": "insufficient_support", "validation_support": csup})
            continue
        merged = cond_adm.merge(order_frame, on="hadm_id", how="inner")
        pair = merged.groupby("candidate")["hadm_id"].nunique().reset_index(name="n_adm")
        pair = pair.merge(base, on="candidate", how="left")
        pair = pair[pair["baseline_adm"] >= 20]
        pair["share"] = pair["n_adm"] / csup
        pair["baseline_share"] = pair["baseline_adm"] / total_adm
        pair["selectivity"] = pair["share"] / pair["baseline_share"].replace(0, float("nan"))
        pair = pair[pair["baseline_share"] <= 0.15]
        pair = pair[pair["n_adm"] >= 5]
        pair["reliability"] = [math.log10(max(1.0, 1 + int(k) - 5)) + 1.0 for k in pair["n_adm"]]
        pair["psr"] = pair["share"] * pair["selectivity"] * pair["reliability"]
        pair = pair.sort_values("psr", ascending=False).reset_index(drop=True)
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
    s = {
        "n_rules": len(dev_gold), "n_checked": n,
        "n_condition_absent": sum(1 for r in results if r.get("status") == "condition_absent"),
        "n_insufficient": sum(1 for r in results if r.get("status") == "insufficient_support"),
        "rank1_concordance": round(sum(1 for r in checked if r["concordant_rank1"]) / n, 4) if n else None,
        "top3_concordance": round(sum(1 for r in checked if r["concordant_top3"]) / n, 4) if n else None,
    }

    print("=" * 78)
    print(f"CLINICAL DIAGNOSIS — {args.role} (exploratory)")
    print("=" * 78)
    print(f"dev rules          : {s['n_rules']}")
    print(f"checked            : {s['n_checked']}")
    print(f"condition absent   : {s['n_condition_absent']}")
    print(f"insufficient       : {s['n_insufficient']}")
    print(f"rank-1 concordance : {s['rank1_concordance']}")
    print(f"top-3 concordance  : {s['top3_concordance']}")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation_summary.json").write_text(
        json.dumps({"events_sha256": events_hash, "split_sha256": split_hash,
                    "summary": s}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "validation_results.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n", encoding="utf-8")

    discord = [r for r in results if r.get("status") == "checked" and not r["concordant_rank1"]]
    print(f"\n=== discordant (n={len(discord)}) ===")
    for r in discord[:15]:
        print(f"  {r['condition']:<32} dev={r['gold_candidate']:<40} val_top={r['top_candidate_validation']}")
    print(f"\nwritten to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
