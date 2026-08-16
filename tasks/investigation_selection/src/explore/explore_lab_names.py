"""Final data check: full poe_detail field names + top lab result test names."""
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
EVENTS = ROOT / "data" / "test_1000_0812" / "event_pipeline_output" / "aggregation" / "processed_events.parquet"
RAW = ROOT / "data" / "test_1000_0812" / "event_pipeline_output" / "aggregation" / "raw_source_records.parquet"


def main() -> int:
    raw = pq.read_table(RAW, columns=["source_table", "clinical_readable_record_json"]).to_pandas()
    pd_ = raw[raw["source_table"] == "hosp.poe_detail"]
    fnames = []
    for rec in pd_["clinical_readable_record_json"]:
        try:
            fnames.append(json.loads(rec).get("field_name"))
        except Exception:  # noqa: BLE001
            fnames.append(None)
    print("=== full poe_detail field_name distribution ===")
    for k, v in pd.Series(fnames).value_counts(dropna=False).items():
        print(f"  {k!r:<40} {v}")

    ev = pq.read_table(
        EVENTS,
        columns=["event_kind", "entity_type", "source_label", "concept_id",
                 "preferred_name", "hadm_id"],
    ).to_pandas()
    res = ev[ev["event_kind"] == "laboratory_resulted"]
    print(f"\n=== top 40 laboratory_resulted test names (n={len(res)}, adm={res['hadm_id'].nunique()}) ===")
    g = (res.groupby(["concept_id", "preferred_name"], dropna=False)
           .agg(n=("hadm_id", "size"), n_adm=("hadm_id", "nunique"))
           .sort_values("n_adm", ascending=False))
    print(g.head(40).to_string(max_colwidth=44))

    return 0


if __name__ == "__main__":
    sys.exit(main())
