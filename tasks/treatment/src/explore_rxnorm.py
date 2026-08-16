"""Explore medication_ordered fields to plan RxNorm-exact category mapping."""
import sys
from pathlib import Path
import pyarrow.parquet as pq
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
from run import medication_category, _MEDICATION_CATEGORIES

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
cols = ["hadm_id", "event_kind", "entity_type", "source_label",
        "preferred_name", "concept_id", "source_concept_id", "assertion"]

e = pq.read_table(EVENTS, columns=cols).to_pandas()
d = e[e["event_kind"] == "medication_ordered"]
print("medication_ordered rows:", len(d))
print("preferred_name non-null:", int(d["preferred_name"].notna().sum()), "unique:", int(d["preferred_name"].nunique()))
print("source_label unique:", int(d["source_label"].nunique()))
print("concept_id non-null:", int(d["concept_id"].notna().sum()), "unique:", int(d["concept_id"].nunique()))
print("source_concept_id non-null:", int(d["source_concept_id"].notna().sum()))
print()

print("--- sample (source_label | preferred_name | concept_id | entity_type) ---")
samp = d[["source_label", "preferred_name", "concept_id", "entity_type"]].drop_duplicates()
print(samp.head(50).to_string())
print()

# coverage of current substring mapping on source_label vs preferred_name
for col in ("source_label", "preferred_name"):
    cats = d[col].map(medication_category)
    tot = d[col].notna().sum()
    cov = cats.notna().sum()
    print(f"{col}: mapped {cov}/{tot} = {cov/tot:.3%}")
print()

# top unmapped source_labels by distinct hadm_id (coverage opportunity)
d["cat_sl"] = d["source_label"].map(medication_category)
unm = d[d["cat_sl"].isna()].groupby("source_label")["hadm_id"].nunique().sort_values(ascending=False)
print("--- top 60 UNMAPPED source_label (distinct admissions) ---")
print(unm.head(60).to_string())
