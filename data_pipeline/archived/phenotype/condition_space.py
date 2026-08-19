"""P6 — condition-space construction (feature-combination enumeration).

Turns the per-visit feature frame into candidate condition combinations X, one
row per (hadm_id, combination), satisfying the design-doc constraints
(``mcq_generation_design.md`` §7.1):

* combination size within [min_conditions, max_conditions] (2-4 formal, 1-4
  exploratory);
* at least one clinical feature (symptom / sign / physiologic_flag / absent);
* at most one age_band and at most one sex;
* feature ids sorted in canonical order.

Apriori support pruning is intentionally NOT applied here (it is a mining-side
optimization); ``max_combinations_per_visit`` bounds pathological fan-out.
"""
from __future__ import annotations

from itertools import combinations

import pandas as pd

CLINICAL_TYPES = {"symptom", "sign", "physiologic_flag", "absent"}
SINGLETON_TYPES = {"age_band", "sex"}


def _valid_combination(types: list[str]) -> bool:
    if not any(t in CLINICAL_TYPES for t in types):
        return False
    for t in SINGLETON_TYPES:
        if types.count(t) > 1:
            return False
    return True


def enumerate_conditions(
    feature_frame: pd.DataFrame,
    min_conditions: int = 1,
    max_conditions: int = 4,
    *,
    max_combinations_per_visit: int = 500,
    min_feature_support: int | None = None,
) -> pd.DataFrame:
    """Enumerate per-visit condition combinations into a long frame.

    Returns columns: hadm_id, condition, condition_feature_ids,
    condition_features, n_features. ``condition`` is the canonical sorted-id
    key; ``condition_feature_ids`` is a sorted list and ``condition_features``
    follows the same order (rule-schema requirement).

    ``min_feature_support`` applies Apriori L1 pruning: features appearing in
    fewer admissions than the threshold can never form a supported condition
    and are dropped before combination (``min_x_support`` from the thresholds).
    """
    if min_feature_support is not None and min_feature_support > 1:
        support = feature_frame.groupby("feature_id")["hadm_id"].nunique()
        keep = set(support[support >= min_feature_support].index)
        feature_frame = feature_frame[feature_frame["feature_id"].isin(keep)]
    rows: list[dict] = []
    for hadm_id, grp in feature_frame.groupby("hadm_id", sort=True):
        entries = list(zip(grp["feature_id"], grp["feature_type"], grp["display_name"]))
        # sort entries by feature_id for canonical order
        entries.sort(key=lambda e: e[0])
        n = len(entries)
        produced = 0
        for k in range(min_conditions, min(max_conditions, n) + 1):
            for combo in combinations(entries, k):
                ids = [e[0] for e in combo]
                types = [e[1] for e in combo]
                if not _valid_combination(types):
                    continue
                displays = [e[2] for e in combo]
                rows.append({
                    "hadm_id": hadm_id,
                    "condition": "|".join(ids),
                    "condition_feature_ids": ids,
                    "condition_features": displays,
                    "n_features": k,
                })
                produced += 1
                if produced >= max_combinations_per_visit:
                    break
            if produced >= max_combinations_per_visit:
                break
    if not rows:
        return pd.DataFrame(columns=[
            "hadm_id", "condition", "condition_feature_ids", "condition_features",
            "n_features"])
    return pd.DataFrame(rows)
