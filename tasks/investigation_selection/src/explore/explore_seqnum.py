"""Verify whether diagnosis source_array_index == 0 corresponds to seq_num == 1."""
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pandas as pd

RAW = Path(r"D:\Projects\llm_benchmark\data\test_1000_0812\event_pipeline_output\aggregation\raw_source_records.parquet")


def main() -> int:
    if not RAW.exists():
        print("MISSING", RAW)
        return 2
    raw = pq.read_table(RAW, columns=["hadm_id", "source_table", "source_array_index",
                                      "raw_record_json"]).to_pandas()
    diag = raw[raw["source_table"] == "hosp.diagnoses_icd"].copy()

    # inspect a few admissions: source_array_index vs seq_num
    print("=== sample admissions: source_array_index -> seq_num / icd_code ===")
    shown = 0
    for hadm, grp in diag.groupby("hadm_id"):
        grp = grp.sort_values("source_array_index")
        for _, r in grp.head(4).iterrows():
            try:
                rec = json.loads(r["raw_record_json"])
            except Exception:
                continue
            seq = rec.get("seq_num")
            code = rec.get("icd_code")
            print(f"  hadm={hadm} idx={int(r['source_array_index'])}  seq_num={seq}  icd={code}")
        shown += 1
        if shown >= 3:
            break

    # aggregate: is idx==0 always seq_num==1 ?
    def _seqnum(rr):
        try:
            return json.loads(rr).get("seq_num")
        except Exception:
            return None

    diag["seq_num"] = diag["raw_record_json"].map(_seqnum)
    idx0 = diag[diag["source_array_index"] == 0]
    print("\n=== idx==0 records: seq_num distribution ===")
    print(idx0["seq_num"].value_counts(dropna=False).to_string())
    print("\n=== cross: idx==0 vs seq_num==1 (first 10) ===")
    print(idx0[["hadm_id", "source_array_index", "seq_num"]].head(10).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
