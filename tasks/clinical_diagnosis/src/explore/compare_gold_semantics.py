"""Compare gold semantics on the PRIMARY-diagnosis candidate space."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pyarrow.parquet as pq

from diagnosis import build_diagnosis_gold
from benchmark_common import extract_conditions, _verify_normalized_events

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")

COLS = ["event_id", "subject_id", "hadm_id", "event_kind", "entity_type",
        "source_table", "source_array_index", "source_label",
        "preferred_name", "source_concept_id", "concept_id", "assertion"]


def _load(role: str) -> pd.DataFrame:
    split = pd.read_parquet(SPLIT)
    subjects = set(split[split["role"] == role]["subject_id"].astype(str))
    df = pq.read_table(EVENTS, columns=COLS).to_pandas()
    return df[df["subject_id"].astype(str).isin(subjects)]


def main() -> int:
    _verify_normalized_events(EVENTS)
    dev = _load("development")
    val = _load("validation")
    dev_cond = extract_conditions(dev)
    val_cond = extract_conditions(val)

    print(f"development admissions: {dev['hadm_id'].nunique()}")
    print(f"validation  admissions: {val['hadm_id'].nunique()}")
    print("\n=== gold semantics on PRIMARY diagnosis ===\n")
    for gs in ("psr", "selectivity", "likelihood"):
        dev_gold = build_diagnosis_gold(dev, dev_cond, gold_semantics=gs)
        val_gold = build_diagnosis_gold(val, val_cond, gold_semantics=gs)
        val_map = {g["condition"]: g for g in val_gold}
        checked = rank1 = top3 = 0
        for g in dev_gold:
            v = val_map.get(g["condition"])
            if v is None:
                continue
            checked += 1
            gold = g["gold_candidate"]
            if v["gold_candidate"] == gold:
                rank1 += 1
            if gold in [c["candidate"] for c in v["top_candidates"][:3]]:
                top3 += 1
        print(f"{gs:<12} patterns={len(dev_gold):<4} checked={checked:<4} "
              f"rank1={rank1/checked:.1%}  top3={top3/checked:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
