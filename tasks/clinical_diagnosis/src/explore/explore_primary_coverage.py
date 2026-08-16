"""Compute primary-diagnosis coverage: what % of admissions have a usable
primary diagnosis after each filter stage."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pyarrow.parquet as pq

from diagnosis import _is_disease_code, _is_comorbidity, normalize_diagnosis_name

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")

COLS = ["subject_id", "hadm_id", "event_kind", "source_table",
        "source_array_index", "source_concept_id", "preferred_name"]


def main() -> int:
    split = pd.read_parquet(SPLIT)
    dev = set(split[split["role"] == "development"]["subject_id"].astype(str))
    df = pq.read_table(EVENTS, columns=COLS).to_pandas()
    df = df[df["subject_id"].astype(str).isin(dev)]

    total_adm = df["hadm_id"].nunique()
    cc_adm = df[df["event_kind"] == "symptom_reported"]["hadm_id"].nunique()

    primary = df[
        (df["event_kind"] == "condition_recorded_post_hoc")
        & (df["source_table"] == "hosp.diagnoses_icd")
        & (df["source_array_index"] == 0)
    ].copy()
    primary["is_disease"] = primary["source_concept_id"].map(_is_disease_code)
    primary["candidate"] = primary["preferred_name"].map(normalize_diagnosis_name)
    primary["nonempty"] = primary["candidate"].notna() & (primary["candidate"] != "")
    primary["not_comorb"] = ~primary["candidate"].map(_is_comorbidity)

    n_raw = primary["hadm_id"].nunique()
    n_disease = primary[primary["is_disease"]]["hadm_id"].nunique()
    n_nonempty = primary[primary["is_disease"] & primary["nonempty"]]["hadm_id"].nunique()
    n_clean = primary[primary["is_disease"] & primary["nonempty"] & primary["not_comorb"]]["hadm_id"].nunique()

    print(f"development admissions total           : {total_adm}")
    print(f"  with chief complaint                : {cc_adm}  ({cc_adm/total_adm:.1%})")
    print(f"primary diagnosis (seq_num=1, raw)    : {n_raw}  ({n_raw/total_adm:.1%})")
    print(f"  after disease-code filter           : {n_disease}  ({n_disease/total_adm:.1%})")
    print(f"  + non-empty name                    : {n_nonempty}  ({n_nonempty/total_adm:.1%})")
    print(f"  + comorbidity blacklist             : {n_clean}  ({n_clean/total_adm:.1%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
