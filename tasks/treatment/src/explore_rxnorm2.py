"""Quantify unmapped medication labels: vehicle (correct) vs real drug (gap)."""
import sys
from pathlib import Path
import pyarrow.parquet as pq
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
from run import medication_category, _MEDICATION_CATEGORIES, _NON_TREATMENT

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
cols = ["hadm_id", "event_kind", "source_label"]
e = pq.read_table(EVENTS, columns=cols).to_pandas()
d = e[e["event_kind"] == "medication_ordered"]

d["cat"] = d["source_label"].map(medication_category)
unm = d[d["cat"].isna()]
unm_agg = unm.groupby("source_label")["hadm_id"].nunique().sort_values(ascending=False)

def is_vehicle(s):
    s = s.lower()
    return any(kw in s for kw in _NON_TREATMENT)

rows = []
for lbl, n in unm_agg.items():
    rows.append({"label": lbl, "n_adm": int(n), "vehicle": is_vehicle(lbl)})
udf = pd.DataFrame(rows)
veh = udf[udf["vehicle"]]
drug = udf[~udf["vehicle"]]
print(f"unmapped distinct labels: {len(udf)}, total adm: {udf['n_adm'].sum()}")
print(f"  vehicle/device (correctly excluded): {len(veh)} labels, {veh['n_adm'].sum()} adm")
print(f"  real drug (coverage gap):           {len(drug)} labels, {drug['n_adm'].sum()} adm")
print()
print("--- top 80 real-drug coverage gaps (distinct admissions) ---")
print(drug.head(80).to_string(index=False))
