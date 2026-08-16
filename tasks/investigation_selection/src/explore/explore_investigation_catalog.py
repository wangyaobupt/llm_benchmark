"""Focused exploration: candidate catalog (ordered investigations) and
condition X (ED chief complaints) distributions for the first task prototype.
"""
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
EVENTS = ROOT / "data" / "test_1000_0812" / "event_pipeline_output" / "aggregation" / "processed_events.parquet"

COLS = ["event_id", "subject_id", "hadm_id", "source_table", "event_kind",
        "entity_type", "source_label", "preferred_name", "concept_id",
        "normalization_status", "assertion", "event_time", "value_text"]


def section(t):
    print("\n" + "=" * 70 + "\n" + t + "\n" + "=" * 70)


def main() -> int:
    df = pq.read_table(EVENTS, columns=COLS).to_pandas()

    # ---- candidate catalog: ordered investigations ----
    ordered = df[
        ((df["event_kind"] == "laboratory_ordered") & (df["entity_type"] == "laboratory_test")) |
        ((df["event_kind"] == "imaging_ordered") & (df["entity_type"] == "imaging_study")) |
        ((df["event_kind"] == "clinical_ordered") & (df["entity_type"] == "clinical_order"))
    ].copy()

    section(f"ordered investigation events: {len(ordered)}")
    print(ordered.groupby(["entity_type", "event_kind"]).size().to_string())

    for et in ["laboratory_test", "imaging_study", "clinical_order"]:
        sub = ordered[ordered["entity_type"] == et]
        section(f"top candidates — {et} (events={len(sub)})")
        g = (sub.groupby(["source_label", "concept_id", "preferred_name",
                          "normalization_status"], dropna=False)
               .agg(n=("event_id", "count"),
                    n_adm=("hadm_id", "nunique"))
               .sort_values("n", ascending=False))
        print(g.head(30).to_string(max_colwidth=44))

    # ---- condition X: chief complaints ----
    cc = df[(df["event_kind"] == "symptom_reported")].copy()
    section(f"chief complaints: {len(cc)} events, {cc['hadm_id'].nunique()} admissions")
    g = (cc.groupby("source_label", dropna=False)
           .agg(n=("event_id", "count"), n_adm=("hadm_id", "nunique"))
           .sort_values("n", ascending=False))
    print(g.head(60).to_string(max_colwidth=60))

    # ---- how many admissions have a chief complaint / any order ----
    section("coverage")
    print("admissions total:", df["hadm_id"].nunique())
    print("admissions with chief complaint:", cc["hadm_id"].nunique())
    print("admissions with >=1 ordered investigation:", ordered["hadm_id"].nunique())

    return 0


if __name__ == "__main__":
    sys.exit(main())
