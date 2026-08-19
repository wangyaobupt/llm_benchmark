"""Integration: phenotype feature frame -> condition space -> v2 rule mining.

Proves the wiring: the richer typed feature space (age_band/sex/symptom/
physiologic_flag/medication) produces multi-feature conditions that the v2
miner accepts — including under the formal min_conditions=2 profile.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # v2-llm-stem
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # repo root

from data_pipeline.archived.phenotype.phenotype import build_feature_frame  # noqa: E402
from data_pipeline.archived.phenotype.condition_space import enumerate_conditions  # noqa: E402
from data_pipeline.archived.phenotype.vital_flags import extract_vital_flags  # noqa: E402
from data_pipeline.archived.phenotype.medication_features import extract_medication_features  # noqa: E402
from data_pipeline.archived.phenotype.absent_features import extract_absent_features  # noqa: E402

from mcq.catalog import build_catalog  # noqa: E402
from mcq.mining import mine_rules  # noqa: E402
from mcq.config_loader import load_thresholds  # noqa: E402


def _events():
    rows = []
    eid = 0

    def add(**kw):
        nonlocal eid
        rows.append({"event_id": str(eid), "subject_id": kw["subject_id"],
                     "hadm_id": kw["hadm_id"], "event_kind": kw["event_kind"],
                     "entity_type": kw["entity_type"], "source_label": kw.get("source_label"),
                     "preferred_name": None, "source_concept_id": None,
                     "concept_id": kw.get("concept_id"), "assertion": kw.get("assertion"),
                     "event_time": kw.get("event_time"), "evidence_phase": kw.get("evidence_phase", "source_event"),
                     "value_numeric": kw.get("value_numeric"),
                     "value_structured_json": kw.get("value_structured_json"),
                     "unit": kw.get("unit")})
        eid += 1

    # 12 "chest pain + tachycardia" admissions -> CT Scan; 6 "chest pain" only -> General Xray.
    for i in range(18):
        h = f"a_{i}"
        add(subject_id=f"s_{i}", hadm_id=h, event_kind="symptom_reported",
            entity_type="symptom", source_label="chest pain", assertion="present",
            event_time=None)
        if i < 12:
            add(subject_id=f"s_{i}", hadm_id=h, event_kind="vital_measured",
                entity_type="vital_sign", source_label="Heart rate", value_numeric=120.0,
                unit="/min", event_time="2159-01-01 08:00:00")
        add(subject_id=f"s_{i}", hadm_id=h, event_kind="medication_reconciled",
            entity_type="medication", source_label="metformin",
            event_time="2159-01-01 08:00:00")
        img = "CT Scan" if i < 12 else "General Xray"
        add(subject_id=f"s_{i}", hadm_id=h, event_kind="imaging_ordered",
            entity_type="imaging_study", source_label=img, event_time="2159-01-01 09:00:00")
    return pd.DataFrame(rows)


def _frame_and_conditions():
    events = _events()
    demographics = pd.DataFrame([
        {"hadm_id": f"a_{i}", "gender": "M", "age_band": "65-79"} for i in range(18)
    ])
    vital = extract_vital_flags(events)
    meds = extract_medication_features(events)
    absent = extract_absent_features(events)
    frame = build_feature_frame(events, demographics, vital, meds, absent)
    conditions = enumerate_conditions(frame, min_conditions=2, max_conditions=4)
    return events, frame, conditions


def test_condition_space_has_multi_feature_conditions():
    _, _, conditions = _frame_and_conditions()
    # "chest pain" + "tachycardia" (a 2-feature clinical condition) must exist.
    ids_tuples = {tuple(ids) for ids in conditions["condition_feature_ids"]}
    assert any(
        len(ids) == 2 and any(i.startswith("symptom:") for i in ids)
        and any(i.startswith("physiologic_flag:") for i in ids)
        for ids in ids_tuples
    )


def test_mining_accepts_richer_conditions():
    events, _, conditions = _frame_and_conditions()
    catalog = build_catalog(events)
    thresholds = load_thresholds("exploratory")
    accepted, _ = mine_rules(events, conditions, catalog, thresholds)
    assert accepted
    # accepted rules carry the richer feature types
    assert all(r["status"] == "accepted" for r in accepted)
    # at least one rule has >=2 features (symptom + physiologic_flag / medication)
    assert any(len(r["condition_feature_ids"]) >= 2 for r in accepted)


def test_formal_two_feature_conditions_produce_rules():
    events, _, conditions = _frame_and_conditions()
    catalog = build_catalog(events)
    # exploratory thresholds but formal min_conditions=2 (richer space now satisfies it)
    thresholds = load_thresholds("exploratory")
    thresholds["min_conditions"] = 2
    accepted, _ = mine_rules(events, conditions, catalog, thresholds)
    assert accepted
    assert all(len(r["condition_feature_ids"]) >= 2 for r in accepted)
