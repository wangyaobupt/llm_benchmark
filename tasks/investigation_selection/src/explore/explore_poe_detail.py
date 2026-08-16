"""Check whether hosp.poe_detail can recover the specific lab test name."""
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
RAW = ROOT / "data" / "test_1000_0812" / "event_pipeline_output" / "aggregation" / "raw_source_records.parquet"

COLS = ["source_record_id", "subject_id", "hadm_id", "source_table",
        "source_array_index", "raw_row_ref", "source_role",
        "clinical_readable_record_json"]


def main() -> int:
    raw = pq.read_table(RAW, columns=COLS).to_pandas()
    pd_ = raw[raw["source_table"] == "hosp.poe_detail"]
    print(f"hosp.poe_detail records: {len(pd_)}")

    # inspect a few decoded records
    print("\n=== sample poe_detail decoded records ===")
    for _, row in pd_.head(10).iterrows():
        try:
            rec = json.loads(row["clinical_readable_record_json"])
        except Exception as e:  # noqa: BLE001
            print("  parse error", e)
            continue
        # print only small informative subset
        keep = {k: v for k, v in rec.items()
                if k in ("poe_id", "field_name", "field_value",
                         "field_ordinal", "order_type", "ordervalue",
                         "sequence_num") or "field" in k or "value" in k}
        print(f"  hadm={row['hadm_id']} {json.dumps(keep, ensure_ascii=False)[:500]}")

    # distinct field_name distribution
    fnames = []
    for rec in pd_["clinical_readable_record_json"].head(2000):
        try:
            d = json.loads(rec)
        except Exception:  # noqa: BLE001
            continue
        fnames.append(d.get("field_name"))
    print("\n=== field_name distribution (first 2000) ===")
    for k, v in pd.Series(fnames).value_counts(dropna=False).items():
        print(f"  {k!r:<40} {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
