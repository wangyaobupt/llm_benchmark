"""Dump the FULL unique laboratory result list (for panel mapping design)."""
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
EVENTS = ROOT / "data" / "test_1000_0812" / "event_pipeline_output" / "aggregation" / "processed_events.parquet"


def main() -> int:
    df = pq.read_table(
        EVENTS,
        columns=["event_kind", "entity_type", "concept_id", "preferred_name",
                 "source_label", "hadm_id"],
    ).to_pandas()
    res = df[(df["event_kind"] == "laboratory_resulted")]
    g = (res.groupby(["concept_id", "preferred_name"], dropna=False)
           .agg(n_adm=("hadm_id", "nunique"), n=("hadm_id", "size"))
           .sort_values("n_adm", ascending=False)
           .reset_index())
    print(f"unique labs: {len(g)}")
    print("concept_id | preferred_name | n_adm | n")
    for _, r in g.iterrows():
        print(f"{r['concept_id']} | {r['preferred_name']} | {r['n_adm']} | {r['n']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
