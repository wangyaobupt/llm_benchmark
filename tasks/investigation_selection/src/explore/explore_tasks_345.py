"""Explore candidate spaces for tasks 3 (treatment), 4 (referral), 5 (discharge)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import pyarrow.parquet as pq
import pandas as pd

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")

COLS = ["event_id", "subject_id", "hadm_id", "event_kind", "entity_type",
        "source_table", "source_label", "preferred_name", "source_concept_id",
        "value_text", "status", "evidence_phase"]


def _top(df, name_col, label):
    g = (df.groupby(name_col, dropna=True)
           .agg(n_adm=("hadm_id", "nunique"))
           .sort_values("n_adm", ascending=False))
    print(f"\n=== {label} (n={len(df)}) ===")
    print(g.head(25).to_string(max_colwidth=40))


def main() -> int:
    t = pq.read_table(EVENTS, columns=COLS).to_pandas()

    # task 3: treatment (medications ordered)
    med = t[t["event_kind"] == "medication_ordered"]
    _top(med, "source_label", "medication_ordered (source_label)")
    _top(med, "preferred_name", "medication_ordered (preferred_name)")

    # task 4: referral (service / care unit)
    svc = t[t["event_kind"] == "service_changed"]
    _top(svc, "source_label", "service_changed")
    xfer = t[t["event_kind"] == "patient_transferred"]
    _top(xfer, "source_label", "patient_transferred (care unit)")

    # task 5: discharge disposition — find candidate events
    print("\n=== event_kind containing 'discharge'/'disposition'/'followup' ===")
    kinds = sorted(t["event_kind"].unique())
    for k in kinds:
        if any(w in k.lower() for w in ("discharge", "disposition", "followup", "transfer", "service")):
            print(f"  {k}: {int((t['event_kind']==k).sum())}")

    # check administrative facts in hosp.admissions / transfers
    adm = t[t["source_table"] == "hosp.admissions"]
    print("\n=== hosp.admissions fields ===")
    print(adm.groupby("event_kind").size().to_string())
    _top(adm, "value_text", "hosp.admissions value_text (disposition?)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
