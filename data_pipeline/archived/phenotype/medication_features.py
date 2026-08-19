"""P3 — medications on admission (medication feature) from reconciliation.

Maps ``medication_reconciled`` names (home-med reconciliation) to a clinical
category via the shared category table. Keeps chronic home-med categories
(diabetes/thyroid/…), which are the "medications on admission" signal.
"""
from __future__ import annotations

import pandas as pd

from .medication_categories import medication_feature


def extract_medication_features(events: pd.DataFrame) -> pd.DataFrame:
    """Return hadm_id -> sorted medication categories present on admission."""
    med = events[events["event_kind"] == "medication_reconciled"].copy()
    med["category"] = med["source_label"].map(medication_feature)
    med = med[med["category"].notna()][["hadm_id", "category"]].drop_duplicates()
    out = (
        med.groupby("hadm_id")["category"]
        .apply(lambda s: sorted(set(s)))
        .reset_index(name="medications")
    )
    return out
