"""P6 — assemble the typed per-visit condition-feature space.

Combines every feature source (age_band, sex, present symptoms, physiologic
flags, medications on admission, explicit-negation absent features, and — when
provided — past conditions and physical-exam signs) into one long feature frame:
one row per (hadm_id, feature). This is the "visit transaction" feature side of
MCQ Stage 3 (``mcq_generation_design.md`` §6), consumed by the rule miner.
"""
from __future__ import annotations

import hashlib
from typing import Iterable

import pandas as pd

from benchmark_common.conditions import normalize_condition


def feature_id(feature_type: str, display_name: str) -> str:
    """Stable feature id. Enumerated types use the canonical value verbatim;
    free-text types are content-hashed."""
    enumerated = {"age_band", "sex", "physiologic_flag", "medication"}
    if feature_type in enumerated:
        return f"{feature_type}:{display_name}"
    return f"{feature_type}:" + hashlib.sha256(
        display_name.casefold().encode("utf-8")
    ).hexdigest()[:16]


def _rows(hadm_id: str, feature_type: str, displays: Iterable[str],
          prefix: str = "") -> list[dict]:
    out = []
    for d in displays:
        if not d:
            continue
        disp = f"{prefix}{d}"
        out.append({
            "hadm_id": hadm_id,
            "feature_id": feature_id(feature_type, disp),
            "feature_type": feature_type,
            "display_name": disp,
        })
    return out


# Vital-sign-derived words captured deterministically as ``physiologic_flag``.
# The same word also surfaces as a patient-reported symptom (e.g. "fever"); keep
# it ONLY on the physiologic_flag side so a condition never carries the same
# concept under two feature types (avoids "fever; fever" duplicate conditions).
_VITAL_SIGN_WORDS = {
    "fever", "hypertension", "hypotension", "tachycardia", "bradycardia",
    "tachypnea", "bradypnea", "hypoxia", "hypothermia",
}


def extract_present_symptoms(events: pd.DataFrame) -> pd.DataFrame:
    """Present (assertion == 'present') normalized symptom features."""
    sym = events[
        (events["event_kind"] == "symptom_reported")
        & (events["assertion"] == "present")
        & events["source_label"].notna()
    ]
    if sym.empty:
        return pd.DataFrame(columns=["hadm_id", "feature_id", "feature_type", "display_name"])
    recs: list[dict] = []
    for hadm_id, grp in sym.groupby("hadm_id", sort=True):
        phrases = set()
        for raw in grp["source_label"]:
            norm, _ = normalize_condition(raw)
            for p in _split_phrases(norm):
                if p.casefold() not in _VITAL_SIGN_WORDS:
                    phrases.add(p)
        recs.extend(_rows(hadm_id, "symptom", sorted(phrases)))
    return pd.DataFrame(recs, columns=["hadm_id", "feature_id", "feature_type", "display_name"])


def _split_phrases(condition: str) -> list[str]:
    if not condition:
        return []
    return [p for p in condition.split(", ") if p]


def build_feature_frame(
    events: pd.DataFrame,
    demographics: pd.DataFrame,
    vital_flags: pd.DataFrame,
    medications: pd.DataFrame,
    absent_features: pd.DataFrame,
    past_conditions: pd.DataFrame | None = None,
    signs: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Assemble the long per-(hadm_id, feature) frame across all feature types."""
    frames: list[pd.DataFrame] = []

    # age_band + sex from the demographics sidecar.
    demo_rows: list[dict] = []
    for row in demographics.itertuples(index=False):
        if row.age_band is not None:
            demo_rows.append({"hadm_id": row.hadm_id,
                              "feature_id": feature_id("age_band", row.age_band),
                              "feature_type": "age_band",
                              "display_name": f"age {row.age_band}"})
        if row.gender in ("M", "F"):
            demo_rows.append({"hadm_id": row.hadm_id,
                              "feature_id": feature_id("sex", row.gender),
                              "feature_type": "sex", "display_name": row.gender})
    if demo_rows:
        frames.append(pd.DataFrame(demo_rows, columns=[
            "hadm_id", "feature_id", "feature_type", "display_name"]))

    # present symptoms
    frames.append(extract_present_symptoms(events))

    # physiologic flags
    if vital_flags is not None and not vital_flags.empty:
        flag_rows = []
        for row in vital_flags.itertuples(index=False):
            flag_rows.extend(_rows(row.hadm_id, "physiologic_flag", row.physiologic_flags))
        if flag_rows:
            frames.append(pd.DataFrame(flag_rows, columns=[
                "hadm_id", "feature_id", "feature_type", "display_name"]))

    # medications on admission
    if medications is not None and not medications.empty:
        med_rows = []
        for row in medications.itertuples(index=False):
            med_rows.extend(_rows(row.hadm_id, "medication", row.medications))
        if med_rows:
            frames.append(pd.DataFrame(med_rows, columns=[
                "hadm_id", "feature_id", "feature_type", "display_name"]))

    # absent (explicit negation)
    if absent_features is not None and not absent_features.empty:
        abs_rows = []
        for row in absent_features.itertuples(index=False):
            abs_rows.extend(_rows(row.hadm_id, "absent", row.absent_features, prefix="no "))
        if abs_rows:
            frames.append(pd.DataFrame(abs_rows, columns=[
                "hadm_id", "feature_id", "feature_type", "display_name"]))

    # past_condition + sign (P4, optional)
    for df, ftype in ((past_conditions, "past_condition"), (signs, "sign")):
        if df is None or df.empty or "features" not in df.columns:
            continue
        extra = []
        for row in df.itertuples(index=False):
            extra.extend(_rows(row.hadm_id, ftype, row.features))
        if extra:
            frames.append(pd.DataFrame(extra, columns=[
                "hadm_id", "feature_id", "feature_type", "display_name"]))

    if not frames:
        return pd.DataFrame(columns=["hadm_id", "feature_id", "feature_type", "display_name"])
    return pd.concat(frames, ignore_index=True).drop_duplicates()
