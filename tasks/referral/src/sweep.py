"""Sweep min_share_gap for referral (dev gold -> val rank). Dev + val only."""
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from run import candidate_fn
from benchmark_common.task import build_single_class_gold, validate_single_class, COLS
from benchmark_common import extract_conditions

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")

GAPS = [0.05, 0.08, 0.10, 0.15]


def main() -> int:
    split = pd.read_parquet(SPLIT)
    dev_subj = set(split[split["role"] == "development"]["subject_id"].astype(str))
    val_subj = set(split[split["role"] == "validation"]["subject_id"].astype(str))
    events = pq.read_table(EVENTS, columns=COLS).to_pandas()
    dev = events[events["subject_id"].astype(str).isin(dev_subj)]
    val = events[events["subject_id"].astype(str).isin(val_subj)]
    del events

    cond_dev = extract_conditions(dev)
    cand_dev = candidate_fn(dev)
    cand_val = candidate_fn(val)

    print("referral (baseline val rank-1 61.5% at gap 0.05)")
    print("gap   | n_gold  n_checked  rank1   top3")
    for gap in GAPS:
        gold = build_single_class_gold(
            dev, cond_dev, cand_dev, "referral",
            gold_semantics="selectivity", min_share_gap=gap,
        )
        v = validate_single_class(gold, val, cand_val)
        s = v["summary"]
        print(f"g{gap:.2f} | {len(gold):>4}  {s['n_checked']:>5}  "
              f"{s['rank1_concordance'] if s['rank1_concordance'] is not None else '-':>6}  "
              f"{s['top3_concordance'] if s['top3_concordance'] is not None else '-':>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
