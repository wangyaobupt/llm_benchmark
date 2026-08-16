"""Check whether the full-cohort normalized_events can feed the investigation-
selection pipeline directly (no aggregation needed) and whether the universal-
order pattern persists at scale."""
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pandas as pd

P = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")

NEED = ["event_id", "subject_id", "hadm_id", "event_kind", "entity_type",
        "source_label", "preferred_name", "concept_id", "assertion",
        "normalization_status", "evidence_phase"]


def main() -> int:
    if not P.exists():
        print("MISSING", P)
        return 2
    schema = pq.read_schema(P)
    missing = [c for c in NEED if c not in schema.names]
    print(f"columns total : {len(schema.names)}")
    print(f"required cols : {'OK' if not missing else 'MISSING ' + str(missing)}")

    t = pq.read_table(P, columns=["event_kind", "entity_type", "hadm_id"])
    df = t.to_pandas()
    print(f"\nevent rows     : {len(df)}")
    print(f"admissions     : {df['hadm_id'].nunique()}")
    print("\n=== event_kind distribution (top 30) ===")
    print(df["event_kind"].value_counts().head(30).to_string())

    # ordered-investigation scale at full cohort
    ordered = df[
        ((df["event_kind"] == "laboratory_ordered") & (df["entity_type"] == "laboratory_test")) |
        ((df["event_kind"] == "imaging_ordered") & (df["entity_type"] == "imaging_study")) |
        ((df["event_kind"] == "clinical_ordered") & (df["entity_type"] == "clinical_order"))
    ]
    print(f"\nordered-investigation events: {len(ordered)}")
    print(f"admissions with >=1 ordered: {ordered['hadm_id'].nunique()}")
    print(f"symptom_reported events     : {(df['event_kind']=='symptom_reported').sum()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
