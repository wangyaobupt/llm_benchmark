"""Sweep diagnosis gold thresholds (dev -> val) to find a larger stable set.

Only development + validation splits (never final_test). Replicates the PSR
validation protocol from run_validation.py, parameterized to match dev thresholds.
"""
import sys
from pathlib import Path
import math

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from diagnosis import build_diagnosis_gold, primary_diagnosis
from benchmark_common import extract_conditions

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")

COLS = ["event_id", "subject_id", "hadm_id", "event_kind", "entity_type",
        "source_table", "source_array_index", "source_label",
        "preferred_name", "source_concept_id", "concept_id", "assertion"]


def validate(gold, val, min_condition_support, min_candidate_support, max_baseline_share, psr_nco_min):
    cond = extract_conditions(val)
    order = primary_diagnosis(val)
    base = order.groupby("candidate")["hadm_id"].nunique().rename("baseline_adm")
    total_adm = cond["hadm_id"].nunique()
    checked = 0
    hits = 0
    top3 = 0
    for g in gold:
        cond_adm = cond[cond["condition"] == g["condition"]]
        if cond_adm.empty:
            continue
        csup = int(cond_adm["hadm_id"].nunique())
        if csup < min_condition_support:
            continue
        merged = cond_adm.merge(order, on="hadm_id", how="inner")
        pair = merged.groupby("candidate")["hadm_id"].nunique().reset_index(name="n_adm")
        pair = pair.merge(base, on="candidate", how="left")
        pair = pair[pair["baseline_adm"] >= min_candidate_support]
        pair["share"] = pair["n_adm"] / csup
        pair["baseline_share"] = pair["baseline_adm"] / total_adm
        pair["selectivity"] = pair["share"] / pair["baseline_share"].replace(0, float("nan"))
        pair = pair[pair["baseline_share"] <= max_baseline_share]
        pair = pair[pair["n_adm"] >= psr_nco_min]
        pair["reliability"] = [math.log10(max(1.0, 1 + int(k) - psr_nco_min)) + 1.0 for k in pair["n_adm"]]
        pair["psr"] = pair["share"] * pair["selectivity"] * pair["reliability"]
        pair = pair.sort_values("psr", ascending=False).reset_index(drop=True)
        if pair.empty:
            continue
        idx = pair.index[pair["candidate"] == g["gold_candidate"]]
        rank = int(idx[0]) + 1 if len(idx) else None
        if rank is None:
            continue
        checked += 1
        if rank == 1:
            hits += 1
        if rank <= 3:
            top3 += 1
    r1 = round(hits / checked, 4) if checked else None
    t3 = round(top3 / checked, 4) if checked else None
    return len(gold), checked, r1, t3


def main() -> int:
    split = pd.read_parquet(SPLIT)
    dev_subj = set(split[split["role"] == "development"]["subject_id"].astype(str))
    val_subj = set(split[split["role"] == "validation"]["subject_id"].astype(str))
    events = pq.read_table(EVENTS, columns=COLS).to_pandas()
    dev = events[events["subject_id"].astype(str).isin(dev_subj)]
    val = events[events["subject_id"].astype(str).isin(val_subj)]
    del events

    cond_dev = extract_conditions(dev)
    print("min_cand_sup x max_base x psr_nco_min | n_gold  n_checked  rank1  top3")
    for mcs in (20, 15, 10):
        for mbs in (0.15, 0.20, 0.25):
            for nco in (10, 5):
                gold = build_diagnosis_gold(
                    dev, cond_dev, min_candidate_support=mcs,
                    max_baseline_share=mbs, psr_nco_min=nco,
                )
                ng, nc, r1, t3 = validate(
                    gold, val, 10, mcs, mbs, nco,
                )
                print(f"mcs{mcs:>2} x mbs{mbs:.2f} x nco{nco:>2} | "
                      f"{ng:>4} {nc:>6}  {r1 if r1 is not None else '-':>6}  {t3 if t3 is not None else '-':>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
