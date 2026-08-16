"""Dump normalized chief-complaint distribution on the full development split."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # project root for benchmark_common

import pyarrow.parquet as pq
import pandas as pd

from benchmark_common import normalize_condition

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")


def main() -> int:
    split = pd.read_parquet(SPLIT)
    dev = set(split[split["role"] == "development"]["subject_id"].astype(str))
    df = pq.read_table(EVENTS, columns=["subject_id", "event_kind", "source_label"]).to_pandas()
    df = df[df["subject_id"].astype(str).isin(dev)]
    cc = df[df["event_kind"] == "symptom_reported"].copy()
    cc["norm"], cc["transfer_in"] = zip(*cc["source_label"].map(normalize_condition))
    cc = cc[cc["norm"] != ""]
    g = (cc.groupby("norm")
           .agg(n=("source_label", "size"),
                raw=("source_label", lambda s: " | ".join(dict.fromkeys(s))[:60]))
           .sort_values("n", ascending=False))
    print(f"distinct normalized conditions: {len(g)}")
    print("\n=== top 100 (norm | n | raw examples) ===")
    for norm, row in g.head(100).iterrows():
        print(f"{norm!r:<42} {row['n']:>5}  {row['raw']}")
    print("\n=== suspicious short conditions (len<=3) ===")
    for norm, row in g.iterrows():
        if len(norm) <= 3:
            print(f"{norm!r:<42} {row['n']:>5}  {row['raw']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
