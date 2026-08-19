"""Unit tests for the phenotype (clinical-feature standardization) layer."""
from __future__ import annotations

import pandas as pd
import pytest

from data_pipeline.archived.phenotype.demographics import age_band, parse_admission
from data_pipeline.archived.phenotype.vital_flags import extract_vital_flags, flags_for_visit, load_flag_rules
from data_pipeline.archived.phenotype.medication_categories import medication_category, medication_feature
from data_pipeline.archived.phenotype.medication_features import extract_medication_features
from data_pipeline.archived.phenotype.absent_features import extract_absent_features
from data_pipeline.archived.phenotype.temporal_gate import index_times, is_available
from data_pipeline.archived.phenotype.phenotype import build_feature_frame, feature_id, extract_present_symptoms


# --- demographics -----------------------------------------------------------

def test_age_band():
    assert age_band(17) == "<18"
    assert age_band(18) == "18-39"
    assert age_band(39) == "18-39"
    assert age_band(40) == "40-64"
    assert age_band(65) == "65-79"
    assert age_band(80) == "80+"


def test_parse_admission():
    rec = {
        "subject_id": "1", "hadm_id": "9",
        "mimic_iv_hosp": {
            "patients": [{"subject_id": "1", "gender": "F", "anchor_age": "68",
                          "anchor_year": "2137", "anchor_year_group": "2011 - 2013"}],
            "admissions": [{"admittime": "2145-12-24 00:01:00"}],
        },
    }
    row = parse_admission(rec)
    assert row["gender"] == "F"
    assert row["age_at_encounter"] == 76  # 68 + (2145 - 2137)
    assert row["age_band"] == "65-79"


# --- vital flags ------------------------------------------------------------

def _vital_rows():
    return pd.DataFrame([
        {"hadm_id": "a", "source_label": "Heart rate", "value_numeric": 110.0,
         "value_structured_json": None, "unit": "/min"},
        {"hadm_id": "a", "source_label": "Oxygen saturation", "value_numeric": 88.0,
         "value_structured_json": None, "unit": "%"},
        {"hadm_id": "a", "source_label": "Blood pressure", "value_numeric": None,
         "value_structured_json": '{"systolic": 84.0, "diastolic": 50.0}', "unit": "mmHg"},
    ])


def test_vital_flags():
    rules = load_flag_rules()
    flags = flags_for_visit(_vital_rows(), rules)
    assert "tachycardia" in flags
    assert "hypoxia" in flags
    assert "hypotension" in flags
    assert "fever" not in flags


def test_temperature_fahrenheit_conversion():
    rules = load_flag_rules()
    rows = pd.DataFrame([
        {"hadm_id": "a", "source_label": "Temperature", "value_numeric": 101.2,
         "value_structured_json": None, "unit": "°F"},
    ])
    assert "fever" in flags_for_visit(rows, rules)  # 101.2F = 38.4C >= 38


def test_extract_vital_flags_dataframe():
    events = pd.DataFrame([
        {"event_id": "e1", "hadm_id": "a", "event_kind": "vital_measured",
         "source_label": "Heart rate", "value_numeric": 120.0,
         "value_structured_json": None, "unit": "/min"},
    ])
    out = extract_vital_flags(events)
    assert out.iloc[0]["physiologic_flags"] == ["tachycardia"]


# --- medication -------------------------------------------------------------

def test_medication_feature_keeps_chronic():
    assert medication_feature("metformin") == "antidiabetic"
    assert medication_feature("levothyroxine") == "thyroid"
    assert medication_feature("sodium chloride") is None  # vehicle excluded


def test_medication_category_excludes_chronic_for_answer():
    assert medication_category("metformin") == "antidiabetic"
    assert medication_category("levothyroxine") is None  # chronic, excluded from answer


def test_extract_medication_features():
    events = pd.DataFrame([
        {"event_id": "e1", "hadm_id": "a", "event_kind": "medication_reconciled",
         "source_label": "metformin"},
        {"event_id": "e2", "hadm_id": "a", "event_kind": "medication_reconciled",
         "source_label": "lisinopril"},
    ])
    out = extract_medication_features(events)
    assert out.iloc[0]["medications"] == ["ace_arb", "antidiabetic"]


# --- absent -----------------------------------------------------------------

def test_extract_absent_features():
    events = pd.DataFrame([
        {"event_id": "e1", "hadm_id": "a", "event_kind": "symptom_reported",
         "source_label": "chest pain", "assertion": "absent"},
        {"event_id": "e2", "hadm_id": "a", "event_kind": "symptom_reported",
         "source_label": "fever", "assertion": "present"},
    ])
    out = extract_absent_features(events)
    assert out.iloc[0]["absent_features"] == ["chest pain"]


# --- temporal gate ----------------------------------------------------------

def test_index_times_and_availability():
    events = pd.DataFrame([
        {"event_id": "e1", "hadm_id": "a", "event_kind": "imaging_ordered",
         "event_time": "2159-01-01 10:00:00", "evidence_phase": "source_event"},
        {"event_id": "e2", "hadm_id": "a", "event_kind": "symptom_reported",
         "event_time": "2159-01-01 09:00:00", "evidence_phase": "source_event"},
        {"event_id": "e3", "hadm_id": "a", "event_kind": "symptom_reported",
         "event_time": "2159-01-01 11:00:00", "evidence_phase": "source_event"},
        {"event_id": "e4", "hadm_id": "a", "event_kind": "condition_recorded_post_hoc",
         "event_time": "2159-01-01 09:30:00", "evidence_phase": "post_hoc"},
    ])
    idx = index_times(events)
    index = idx.iloc[0]["index_time"]
    assert index == "2159-01-01 10:00:00"
    assert is_available("2159-01-01 09:00:00", "source_event", index)
    assert not is_available("2159-01-01 11:00:00", "source_event", index)
    assert not is_available("2159-01-01 09:30:00", "post_hoc", index)


# --- phenotype assembly -----------------------------------------------------

def test_feature_id_stability():
    assert feature_id("age_band", "65-79") == "age_band:65-79"
    assert feature_id("symptom", "chest pain") == feature_id("symptom", "chest pain")
    assert feature_id("symptom", "chest pain") != feature_id("symptom", "fever")


def test_extract_present_symptoms_respects_assertion():
    events = pd.DataFrame([
        {"event_id": "e1", "hadm_id": "a", "event_kind": "symptom_reported",
         "source_label": "chest pain", "assertion": "present"},
        {"event_id": "e2", "hadm_id": "a", "event_kind": "symptom_reported",
         "source_label": "fever", "assertion": "absent"},
    ])
    out = extract_present_symptoms(events)
    assert set(out["display_name"]) == {"chest pain"}


def test_extract_present_symptoms_drops_vital_sign_words():
    # A1: vital-sign-derived words are physiologic_flag only, not symptom.
    events = pd.DataFrame([
        {"event_id": "e1", "hadm_id": "a", "event_kind": "symptom_reported",
         "source_label": "chest pain", "assertion": "present"},
        {"event_id": "e2", "hadm_id": "a", "event_kind": "symptom_reported",
         "source_label": "fever", "assertion": "present"},
        {"event_id": "e3", "hadm_id": "a", "event_kind": "symptom_reported",
         "source_label": "tachycardia", "assertion": "present"},
    ])
    out = extract_present_symptoms(events)
    assert set(out["display_name"]) == {"chest pain"}


def test_build_feature_frame():
    events = pd.DataFrame([
        {"event_id": "e1", "hadm_id": "a", "event_kind": "symptom_reported",
         "source_label": "chest pain", "assertion": "present",
         "value_numeric": None, "value_structured_json": None, "unit": None},
        {"event_id": "e2", "hadm_id": "a", "event_kind": "vital_measured",
         "source_label": "Heart rate", "assertion": None,
         "value_numeric": 120.0, "value_structured_json": None, "unit": "/min"},
        {"event_id": "e3", "hadm_id": "a", "event_kind": "medication_reconciled",
         "source_label": "metformin", "assertion": None,
         "value_numeric": None, "value_structured_json": None, "unit": None},
        {"event_id": "e4", "hadm_id": "a", "event_kind": "symptom_reported",
         "source_label": "fever", "assertion": "absent",
         "value_numeric": None, "value_structured_json": None, "unit": None},
    ])
    demographics = pd.DataFrame([{"hadm_id": "a", "gender": "M", "age_band": "65-79"}])
    vital_flags = extract_vital_flags(events)
    meds = extract_medication_features(events)
    absent = extract_absent_features(events)
    frame = build_feature_frame(events, demographics, vital_flags, meds, absent)
    types = set(frame["feature_type"])
    assert types == {"age_band", "sex", "symptom", "physiologic_flag", "medication", "absent"}
    assert {"age_band:65-79", "sex:M", "symptom:" + _h("chest pain")} <= set(frame["feature_id"])


def _h(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.casefold().encode()).hexdigest()[:16]


# --- sign (P4 NER track) ---------------------------------------------------

def test_extract_physical_exam():
    from data_pipeline.archived.phenotype.sign_ner import extract_physical_exam
    text = (
        "Chief Complaint:\nchest pain\n\n"
        "Physical Exam:\nVitals: 98.7, 165/93\nHEART - RRR, no MRG, nl S1-S2\n"
        "ABDOMEN - NABS\n\n"
        "Discharge Diagnosis:\nNSTEMI\n"
    )
    section = extract_physical_exam(text)
    assert section is not None
    assert "RRR" in section and "NABS" in section
    assert "NSTEMI" not in section  # stopped at the next section header
    assert extract_physical_exam("no physical exam here") is None


# --- past_condition (P4) ----------------------------------------------------

def test_past_condition_icd_track():
    from data_pipeline.archived.phenotype.past_condition import extract_past_condition_icd
    events = pd.DataFrame([
        {"event_id": "e1", "hadm_id": "a", "event_kind": "condition_recorded_post_hoc",
         "concept_id": "icd10:Z86718", "source_label": "Personal history of venous thrombosis"},
        {"event_id": "e2", "hadm_id": "a", "event_kind": "condition_recorded_post_hoc",
         "concept_id": "icd10:E119", "source_label": "Type 2 diabetes mellitus"},
        {"event_id": "e3", "hadm_id": "a", "event_kind": "condition_recorded_post_hoc",
         "concept_id": "icd10:S022XXA", "source_label": "Fracture of nasal bones"},
    ])
    out = extract_past_condition_icd(events)
    features = out.iloc[0]["features"]
    assert "Personal history of venous thrombosis" in features  # Z-code history
    assert "diabetes mellitus" in features                      # chronic keyword, normalized
    assert "Fracture of nasal bones" not in features            # acute, not chronic


def test_normalize_icd_name():
    from data_pipeline.archived.phenotype.past_condition import _normalize_icd_name
    assert _normalize_icd_name(
        "Atherosclerotic heart disease of native coronary artery without angina pectoris"
    ) == "coronary artery disease"
    assert _normalize_icd_name("Hyperlipidemia, unspecified") == "hyperlipidemia"
    assert _normalize_icd_name("Congestive heart failure, unspecified") == "heart failure"
    assert _normalize_icd_name("Chronic kidney disease, stage 3 (moderate)") == "chronic kidney disease"
    assert _normalize_icd_name("Type 2 diabetes mellitus without complications") == "diabetes mellitus"
    assert _normalize_icd_name("Atrial fibrillation") == "atrial fibrillation"
    # C1 extension: asthma/COPD variants + Z89 "acquired absence" status codes.
    assert _normalize_icd_name("ASTHMA W STATUS ASTHMAT") == "asthma"
    assert _normalize_icd_name("ASTHMA, UNSPECIFIED, WITH ACUTE EXACERBATION") == "asthma"
    assert _normalize_icd_name(
        "ASTHMA, CHRONIC OBSTRUCTIVE, WITH ACUTE EXACERBATION"
    ) == "copd"
    assert _normalize_icd_name("Acquired absence of left leg above knee") == "amputation/organ absence status"
    assert _normalize_icd_name("Acquired absence of kidney") == "amputation/organ absence status"


def test_past_condition_ner_track():
    import shutil
    import uuid
    from pathlib import Path
    import pyarrow as pa
    import pyarrow.parquet as pq
    from data_pipeline.archived.phenotype.past_condition import extract_past_condition_ner
    # Path.mkdir (not tempfile.mkdtemp) — the sandbox denies writes inside
    # mkdtemp-created directories.
    d = Path(r"D:\Projects\llm_benchmark") / ("test-ner-" + uuid.uuid4().hex)
    d.mkdir(parents=True, exist_ok=True)
    try:
        p = d / "mentions.parquet"
        df = pd.DataFrame([
            {"entity_type": "clinical_problem", "temporality": "historical",
             "hadm_id": "a", "surface_text": "PMHx of CHF"},
            {"entity_type": "clinical_problem", "temporality": "current",
             "hadm_id": "a", "surface_text": "acute bronchitis"},
        ])
        pq.write_table(pa.Table.from_pandas(df), p)
        out = extract_past_condition_ner(p)
        # "PMHx of CHF" normalizes to "congestive heart failure"; current
        # "acute bronchitis" is excluded (not historical).
        assert out.iloc[0]["features"] == ["congestive heart failure"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- condition space --------------------------------------------------------

def test_enumerate_conditions_constraints():
    from data_pipeline.archived.phenotype.condition_space import enumerate_conditions
    frame = pd.DataFrame([
        {"hadm_id": "a", "feature_id": "age_band:65-79", "feature_type": "age_band", "display_name": "age 65-79"},
        {"hadm_id": "a", "feature_id": "sex:M", "feature_type": "sex", "display_name": "M"},
        {"hadm_id": "a", "feature_id": "symptom:" + _h("chest pain"), "feature_type": "symptom", "display_name": "chest pain"},
        {"hadm_id": "a", "feature_id": "physiologic_flag:tachycardia", "feature_type": "physiologic_flag", "display_name": "tachycardia"},
    ])
    cond = enumerate_conditions(frame, min_conditions=2, max_conditions=4)
    # every combination must have >=1 clinical (symptom/flag) and <=1 age, <=1 sex
    for ids, names in zip(cond["condition_feature_ids"], cond["condition_features"]):
        types = [i.split(":")[0] for i in ids]
        assert any(t in {"symptom", "sign", "physiologic_flag", "absent"} for t in types)
        assert types.count("age_band") <= 1 and types.count("sex") <= 1
        assert len(ids) == len(names)
    # single-symptom-only frame with min_conditions=2 yields nothing
    single = frame[frame["feature_type"] == "symptom"]
    assert enumerate_conditions(single, min_conditions=2, max_conditions=4).empty
