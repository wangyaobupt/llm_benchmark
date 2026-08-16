"""Locate where laboratory order identity lives (source_label is NaN)."""
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
EVENTS = ROOT / "data" / "test_1000_0812" / "event_pipeline_output" / "aggregation" / "processed_events.parquet"
RAW = ROOT / "data" / "test_1000_0812" / "event_pipeline_output" / "aggregation" / "raw_source_records.parquet"

FULL = ["event_id", "subject_id", "hadm_id", "source_table", "event_kind",
        "entity_type", "lifecycle_action", "source_action",
        "source_concept_id", "concept_id", "source_label", "preferred_name",
        "value_text", "value_numeric", "value_structured_json", "unit",
        "normalization_status", "source_text_field", "source_text_kind",
        "source_text", "quality_flags", "supporting_source_row_ids",
        "supporting_raw_row_refs", "raw_row_ref", "status", "content_specificity"]


def main() -> int:
    df = pq.read_table(EVENTS, columns=FULL).to_pandas()
    lab = df[(df["event_kind"] == "laboratory_ordered")].copy()
    print(f"laboratory_ordered events: {len(lab)}")

    # distinct non-null identity-ish fields
    for c in ["source_concept_id", "concept_id", "source_label", "preferred_name",
              "value_text", "value_structured_json", "source_text",
              "content_specificity", "status"]:
        nn = lab[c].notna().sum()
        print(f"  {c}: non-null {nn} / {len(lab)}")

    with pd.option_context("display.max_colwidth", 200, "display.width", 260,
                           "display.max_columns", None):
        print("\n=== sample laboratory_ordered rows (identity fields) ===")
        cols = ["event_id", "hadm_id", "source_concept_id", "concept_id",
                "source_label", "preferred_name", "value_text",
                "value_structured_json", "content_specificity", "status",
                "source_text_field", "source_text_kind"]
        print(lab[cols].head(12).to_string())

        # distinct content_specificity / status for lab orders
        print("\n=== content_specificity x status ===")
        print(lab.groupby(["content_specificity", "status"], dropna=False).size().to_string())

        # value_structured_json distinct (first 20)
        print("\n=== distinct value_structured_json (head) ===")
        vsj = lab["value_structured_json"].dropna().unique()[:20]
        for v in vsj:
            print("  ", v)

        # does source_concept_id appear for lab RESULT events? (labevents)
        lab_res = df[(df["event_kind"] == "laboratory_resulted")].copy()
        print(f"\nlaboratory_resulted events: {len(lab_res)}")
        for c in ["source_concept_id", "concept_id", "source_label", "preferred_name"]:
            print(f"  {c}: non-null {lab_res[c].notna().sum()}")

    # raw source records for a few lab-order supporting rows
    print("\n=== raw_source_records schema sample (hosp.poe / poe_detail) ===")
    raw = pq.read_table(RAW, columns=["source_record_id", "source_table",
                                      "source_text_field", "source_text",
                                      "source_role"]).to_pandas()
    poe = raw[raw["source_table"].str.startswith("hosp.poe", na=False)]
    print(poe.groupby(["source_table", "source_text_field", "source_role"], dropna=False)
             .size().to_string())

    return 0


if __name__ == "__main__":
    sys.exit(main())
