"""Explore diagnosis events (clinical-diagnosis task candidates)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyarrow.parquet as pq
import pandas as pd

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")

COLS = ["event_id", "subject_id", "hadm_id", "event_kind", "entity_type",
        "source_table", "source_label", "preferred_name", "source_concept_id",
        "concept_id", "status", "content_specificity", "normalization_status"]


def main() -> int:
    df = pq.read_table(EVENTS, columns=COLS).to_pandas()
    diag = df[df["event_kind"] == "condition_recorded_post_hoc"].copy()
    print(f"diagnosis events: {len(diag)}")
    print(f"  admissions: {diag['hadm_id'].nunique()}")

    print("\n=== source_table x entity_type ===")
    print(diag.groupby(["source_table", "entity_type"]).size().to_string())

    print("\n=== status / content_specificity distribution ===")
    for c in ("status", "content_specificity"):
        print(diag[c].value_counts(dropna=False).head(20).to_string())

    print("\n=== top 40 diagnosis candidates (by preferred_name) ===")
    g = (diag.groupby(["preferred_name", "source_concept_id"], dropna=False)
           .agg(n_adm=("hadm_id", "nunique"), n=("event_id", "size"))
           .sort_values("n_adm", ascending=False))
    print(g.head(40).to_string(max_colwidth=40))

    print("\n=== source_label sample (is diagnosis name here?) ===")
    print(diag[["source_label", "preferred_name", "source_concept_id"]].drop_duplicates().head(20).to_string(max_colwidth=40))

    return 0


if __name__ == "__main__":
    sys.exit(main())
