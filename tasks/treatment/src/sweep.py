"""Sweep min_share_gap x min_gold_share for treatment layers (dev gold -> val rank).

Only uses development + validation splits (never final_test).
Loads events once, then sweeps in-memory.
"""
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from run import LAYERS
from benchmark_common.task import build_single_class_gold, validate_single_class, COLS
from benchmark_common import extract_conditions

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")

GAPS = [0.05, 0.08, 0.10, 0.15]
GOLD_SHARES = [0.0, 0.05, 0.10, 0.15]


def main() -> int:
    split = pd.read_parquet(SPLIT)
    dev_subj = set(split[split["role"] == "development"]["subject_id"].astype(str))
    val_subj = set(split[split["role"] == "validation"]["subject_id"].astype(str))

    events = pq.read_table(EVENTS, columns=COLS).to_pandas()
    events = events[events["subject_id"].astype(str).isin(dev_subj | val_subj)]
    dev = events[events["subject_id"].astype(str).isin(dev_subj)]
    val = events[events["subject_id"].astype(str).isin(val_subj)]
    del events

    for layer in ("t1", "t2", "t3"):
        candidate_fn, _ = LAYERS[layer]
        cond_dev = extract_conditions(dev)
        cond_val = extract_conditions(val)
        cand_dev = candidate_fn(dev)
        cand_val = candidate_fn(val)
        print(f"\n=== {layer} ===  (baseline val rank-1 56.5%/62.2%/59.6%)")
        print(f"gap x gold_share | n_gold  n_checked  rank1    top3")
        for gs in GOLD_SHARES:
            row = []
            for gap in GAPS:
                gold = build_single_class_gold(
                    dev, cond_dev, cand_dev, f"treatment_{layer}",
                    gold_semantics="selectivity",
                    min_share_gap=gap, min_gold_share=gs,
                )
                v = validate_single_class(gold, val, cand_val)
                s = v["summary"]
                row.append(f"g{gap:.2f}/m{gs:.2f}: {len(gold):>3} {s['n_checked']:>4} "
                           f"{s['rank1_concordance'] if s['rank1_concordance'] is not None else '-':>6} "
                           f"{s['top3_concordance'] if s['top3_concordance'] is not None else '-':>6}")
            print(" | ".join(row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
