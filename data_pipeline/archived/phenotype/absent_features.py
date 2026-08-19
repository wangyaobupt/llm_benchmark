"""P5 — explicit-negation (absent) features from symptom assertions.

A symptom reported with ``assertion == "absent"`` is an explicit negation
("no chest pain", "denies fever") and becomes an ``absent`` feature. The ≥8
support constraint for negated combinations is enforced by the miner (P6).
"""
from __future__ import annotations

import pandas as pd


def extract_absent_features(events: pd.DataFrame) -> pd.DataFrame:
    """Return hadm_id -> sorted list of explicitly-negated symptoms."""
    sym = events[
        (events["event_kind"] == "symptom_reported")
        & (events["assertion"] == "absent")
        & events["source_label"].notna()
    ]
    if sym.empty:
        return pd.DataFrame(columns=["hadm_id", "absent_features"])
    sym = sym[["hadm_id", "source_label"]].drop_duplicates()
    out = (
        sym.groupby("hadm_id")["source_label"]
        .apply(lambda s: sorted(set(s)))
        .reset_index(name="absent_features")
    )
    return out
