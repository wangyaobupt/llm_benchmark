"""Condition-feature extraction for the v2 investigation-selection task.

Reuses the project-root ``benchmark_common.conditions`` normalizer (the same
chief-complaint normalization as v1) and maps a normalized condition string to
the ordered feature list the pipeline and LLM see.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark_common.conditions import extract_conditions  # noqa: E402

from .hashing import feature_id  # noqa: E402

# Feature types present in the current (symptom-only) feature space. The richer
# space (age_band/sex/sign/physiologic_flag/past_condition/medication/absent)
# awaits the upstream standardization module; see the README deviation note.
_FEATURE_TYPE = "symptom"


def condition_features(condition: str) -> list[str]:
    """Split a normalized condition string into its ordered, deduped phrases.

    ``extract_conditions`` already sorts and dedupes phrases, so the string is
    ``"a, b"`` with phrases in canonical order; splitting on ``", "`` recovers
    the ordered unique list.
    """
    if not condition:
        return []
    return [p for p in condition.split(", ") if p]


def feature_ids(features: list[str]) -> list[str]:
    return [feature_id(f) for f in features]


def extract_condition_frame(events: pd.DataFrame) -> pd.DataFrame:
    """Return hadm_id -> condition + condition_feature_ids (+ display list)."""
    cond = extract_conditions(events)
    cond["condition_features"] = cond["condition"].map(condition_features)
    cond["condition_feature_ids"] = cond["condition_features"].map(feature_ids)
    cond["n_features"] = cond["condition_features"].map(len)
    return cond
