"""Clinical diagnosis task: chief complaint -> most likely diagnosis.

Reuses the shared normalization / statistics / split infrastructure from the
investigation-selection package. Diagnosis candidates come from `ed.diagnosis`
(the presenting diagnosis), filtered to disease chapters (drop symptom R,
history Z/V, external-cause S/T/W/X/Y/E codes). Gold uses PSR (probability x
specificity x reliability), which suits the low-prior disease answer space.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pandas as pd

# make benchmark_common (project root) importable
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmark_common import (
    extract_conditions, _verify_normalized_events, _sha256_file,
    wilson_lower, binomial_greater_pvalue, benjamini_hochberg,
)

# ICD-10 disease chapters kept (drop R=症状, Z=历史/状态, S/T=损伤,
# V/W/X/Y=外因, O/P/Q=孕产/先天).
_DISEASE_ICD10 = set("ABCDEFGHIJKLMN")


def _is_disease_code(code: str | None) -> bool:
    if not code:
        return False
    if code.startswith("icd10:"):
        return code[6:7] in _DISEASE_ICD10
    if code.startswith("icd9:"):
        c = code[5:]
        if c and c[0] in "EV":
            return False
        try:
            return int(c[:3]) < 780  # keep 001-779; drop symptoms 780-799 + injury 800-999
        except ValueError:
            return False
    return False


_QUALIFIER_RE = re.compile(
    r",?\s*(unspecified|site not specified|organism unspecified|"
    r"not elsewhere classified|without mention of complication|"
    r"without complication|other specified|uncomplicated|unspec|nos|nec|"
    r"initial episode of care|subsequent episode of care|"
    r"initial encounter|subsequent encounter|acute on chronic)\s*$"
)

# Common ICD-9 / ICD-10 name variants mapped to one canonical concept.
_DIAGNOSIS_SYNONYMS = {
    "congestive heart failure": "heart failure",
    "essential hypertension": "hypertension",
    "diabetes uncompl adult": "diabetes mellitus",
    "type 2 diabetes mellitus": "diabetes mellitus",
    "urin tract infection": "urinary tract infection",
    "non-st elevation myocardial infarction": "nstemi",
    "subendocardial infarction": "nstemi",
    "acute renal failure": "acute kidney failure",
    "gastrointest hemorrh": "gastrointestinal hemorrhage",
}


def normalize_diagnosis_name(name: str | None) -> str:
    if not name:
        return ""
    s = name.lower().strip()
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s)  # drop parenthetical qualifiers
    s = _QUALIFIER_RE.sub("", s)              # drop trailing "unspecified/nos/..."
    s = re.sub(r"\s+", " ", s).strip(" ,;")
    s = _DIAGNOSIS_SYNONYMS.get(s, s)
    # family merges: same disease, different granularity / location / severity.
    if "heart failure" in s:
        return "heart failure"
    if "st elevation myocardial infarction" in s or s == "stemi":
        return "stemi"
    if "septicemia" in s or "sepsis" in s:
        return "sepsis"
    if "cerebral" in s and any(k in s for k in ("infarction", "embolism", "occlusion")):
        return "cerebral infarction"
    return s


# Chronic comorbidities that are background conditions, not the presenting
# diagnosis. Excluded from the candidate (answer) space.
_COMORBIDITY_KEYWORDS = (
    "hypertension", "diabetes", "hyperlipid", "hypercholesterol",
    "atherosclerotic heart", "coronary atherosclerosis", "coronary artery disease",
    "old myocardial infarction", "atrial fibrillation",
    "chronic kidney", "end stage renal",
    "chronic obstructive pulmonary", "asthma",
    "depressive", "depression", "anxiety", "bipolar",
    "hypothyroidism", "reflux", "obesity", "gout", "osteoporosis",
    "sleep apnea", "nicotine", "tobacco",
    "urinary tract infection",  # over-coded catch-all in MIMIC
)


def _is_comorbidity(name: str) -> bool:
    return any(k in name for k in _COMORBIDITY_KEYWORDS)


# Symptom/sign "diagnoses" (ICD disease chapters but clinically a finding, not
# a disease). Excluded from the answer space per the P3 default.
_SYMPTOM_KEYWORDS = ("orthostatic hypotension", "melena")


def _is_symptom(name: str) -> bool:
    return any(k in name for k in _SYMPTOM_KEYWORDS)


def diagnosis_candidates(events: pd.DataFrame) -> pd.DataFrame:
    d = events[events["event_kind"] == "condition_recorded_post_hoc"].copy()
    d = d[d["source_concept_id"].map(_is_disease_code)]
    d["candidate"] = d["preferred_name"].map(normalize_diagnosis_name)
    d = d[d["candidate"].notna() & (d["candidate"] != "")]
    d = d[~d["candidate"].map(_is_comorbidity)]
    d = d[~d["candidate"].map(_is_symptom)]
    return d[["hadm_id", "candidate"]].drop_duplicates()


def primary_diagnosis(events: pd.DataFrame) -> pd.DataFrame:
    """Primary (seq_num==1) hospital diagnosis per admission.

    Verified: in the raw archive the diagnoses_icd array is sorted by seq_num,
    so source_array_index==0 is always seq_num==1 (the primary diagnosis).
    """
    d = events[
        (events["event_kind"] == "condition_recorded_post_hoc")
        & (events["source_table"] == "hosp.diagnoses_icd")
        & (events["source_array_index"] == 0)
    ].copy()
    d = d[d["source_concept_id"].map(_is_disease_code)]
    d["candidate"] = d["preferred_name"].map(normalize_diagnosis_name)
    d = d[d["candidate"].notna() & (d["candidate"] != "")]
    d = d[~d["candidate"].map(_is_comorbidity)]
    d = d[~d["candidate"].map(_is_symptom)]
    return d[["hadm_id", "candidate"]].drop_duplicates()


def diagnosis_pool(events: pd.DataFrame) -> list[str]:
    d = diagnosis_candidates(events)
    return (d.groupby("candidate")["hadm_id"].nunique()
             .sort_values(ascending=False).index.tolist())


def build_diagnosis_gold(events: pd.DataFrame, cond: pd.DataFrame,
                         min_condition_support: int = 10,
                         max_baseline_share: float = 0.15,
                         min_candidate_support: int = 20,
                         gold_semantics: str = "psr",
                         psr_nco_min: int = 5,
                         psr_p_min: float = 0.005,
                         psr_r: float = 1.0) -> list[dict]:
    order_frame = primary_diagnosis(events)
    merged = cond.merge(order_frame, on="hadm_id", how="inner")
    pair = (merged.groupby(["condition", "candidate"], dropna=True)
                  .agg(n_adm=("hadm_id", "nunique")).reset_index())
    cond_support = merged.groupby("condition")["hadm_id"].nunique()
    base = order_frame.groupby("candidate")["hadm_id"].nunique().rename("baseline_adm")
    total_adm = cond["hadm_id"].nunique()

    frames: list[pd.DataFrame] = []
    for cname, csup in cond_support.items():
        if csup < min_condition_support:
            continue
        sub = pair[pair["condition"] == cname].merge(base, on="candidate", how="left")
        sub["share"] = sub["n_adm"] / csup
        sub["baseline_share"] = sub["baseline_adm"] / total_adm
        sub["selectivity"] = sub["share"] / sub["baseline_share"].replace(0, float("nan"))
        sub = sub[sub["baseline_share"] <= max_baseline_share]
        sub = sub[sub["baseline_adm"] >= min_candidate_support]
        sub = sub.assign(condition=cname, condition_support=int(csup))
        frames.append(sub)
    if not frames:
        return []
    df = pd.concat(frames, ignore_index=True)
    if df.empty:
        return []

    df["p_value"] = [
        binomial_greater_pvalue(int(k), int(n), float(p0))
        for k, n, p0 in zip(df["n_adm"], df["condition_support"], df["baseline_share"])
    ]
    df["q_value"] = 0.0
    for cname, grp in df.groupby("condition"):
        df.loc[grp.index, "q_value"] = benjamini_hochberg(grp["p_value"].tolist())
    df["wilson_lower"] = [
        wilson_lower(int(k), int(n)) for k, n in zip(df["n_adm"], df["condition_support"])
    ]
    df["reliability"] = [
        math.log10(max(1.0, 1 + int(k) - psr_nco_min)) + psr_r for k in df["n_adm"]
    ]
    df["psr"] = df["share"] * df["selectivity"] * df["reliability"]
    df["sr"] = df["selectivity"] * df["reliability"]

    if gold_semantics == "psr":
        df = df[(df["n_adm"] >= psr_nco_min) & (df["share"] >= psr_p_min)]
        rank_col, gold_basis = "psr", "behavioral_psr"
    elif gold_semantics == "selectivity":
        df = df[df["q_value"] <= 0.10]
        rank_col, gold_basis = "selectivity", "behavioral_most_selective_fdr"
    else:
        rank_col, gold_basis = "share", "behavioral_most_likely"

    rows: list[dict] = []
    for cname, grp in df.groupby("condition"):
        grp = grp.sort_values(rank_col, ascending=False)
        top = grp.head(5)
        if top.empty:
            continue
        g = top.iloc[0]
        rows.append({
            "class": "diagnosis",
            "condition": cname,
            "condition_support": int(top.iloc[0]["condition_support"]),
            "gold_candidate": g["candidate"],
            "gold_share": round(float(g["share"]), 4),
            "gold_selectivity": round(float(g["selectivity"]), 3)
                                if pd.notna(g["selectivity"]) else None,
            "gold_psr": round(float(g["psr"]), 3),
            "gold_basis": gold_basis,
            "top_candidates": [
                {"candidate": r["candidate"], "n_adm": int(r["n_adm"]),
                 "share": round(float(r["share"]), 4),
                 "selectivity": round(float(r["selectivity"]), 3)
                                if pd.notna(r["selectivity"]) else None,
                 "psr": round(float(r["psr"]), 3)}
                for _, r in top.iterrows()
            ],
        })
    return rows


def generate_diagnosis_questions(gold_rows: list[dict], pool: list[str],
                                 n_options: int = 4) -> list[dict]:
    qs = []
    for i, g in enumerate(gold_rows, start=1):
        gold = g["gold_candidate"]
        distractors = [c for c in pool if c != gold][: n_options - 1]
        if len(distractors) < n_options - 1:
            continue
        options = [gold] + distractors
        stem = (f"A patient presents to the emergency department with "
                f"{g['condition']}. What is the most likely diagnosis?")
        qs.append({
            "question_id": f"qdx_{i:04d}",
            "task": "clinical_diagnosis",
            "comparison_class": "diagnosis",
            "condition": g["condition"],
            "condition_support": g["condition_support"],
            "stem": stem,
            "options": options,
            "answer_index": 0,
            "answer": gold,
            "gold_basis": g["gold_basis"],
            "status": "exploratory_unreviewed",
            "candidate_counts": g["top_candidates"],
        })
    return qs


def run_diagnosis(events_path: Path, split_path: Path, role: str = "development",
                  gold_semantics: str = "psr", out_dir: Path | None = None) -> dict:
    events_path = Path(events_path)
    split_path = Path(split_path)
    events_hash = _verify_normalized_events(events_path)
    split_hash = _sha256_file(split_path)

    split_df = pd.read_parquet(split_path)
    role_subjects = set(split_df[split_df["role"] == role]["subject_id"].astype(str))
    cols = ["event_id", "subject_id", "hadm_id", "event_kind", "entity_type",
            "source_table", "source_array_index", "source_label",
            "preferred_name", "source_concept_id", "concept_id", "assertion"]
    events = pq.read_table(events_path, columns=cols).to_pandas()
    events = events[events["subject_id"].astype(str).isin(role_subjects)]

    cond = extract_conditions(events)
    gold = build_diagnosis_gold(events, cond, gold_semantics=gold_semantics)
    pool = diagnosis_pool(events)
    questions = generate_diagnosis_questions(gold, pool)

    summary = {
        "status": "exploratory_unreviewed",
        "task": "clinical_diagnosis",
        "gold_semantics": gold_semantics,
        "split_role": role,
        "events_path": str(events_path),
        "events_sha256": events_hash,
        "split_path": str(split_path),
        "split_sha256": split_hash,
        "admissions_total": int(events["hadm_id"].nunique()),
        "subjects_total": int(events["subject_id"].nunique()),
        "admissions_with_condition": int(cond["hadm_id"].nunique()),
        "n_gold_patterns": len(gold),
        "n_questions": len(questions),
        "gold_patterns": gold,
        "questions": questions,
    }
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "questions.jsonl").write_text(
            "\n".join(json.dumps(q, ensure_ascii=False) for q in questions) + "\n",
            encoding="utf-8")
        (out_dir / "gold_patterns.jsonl").write_text(
            "\n".join(json.dumps(g, ensure_ascii=False) for g in gold) + "\n",
            encoding="utf-8")
        (out_dir / "run_manifest.json").write_text(
            json.dumps({
                "schema": "clinical-diagnosis-exploratory-manifest/1.0.0",
                "status": "exploratory_unreviewed",
                "gold_semantics": gold_semantics,
                "input": {"path": str(events_path), "sha256": events_hash},
                "split": {"path": str(split_path), "sha256": split_hash, "role": role},
                "counts": {"admissions_total": summary["admissions_total"],
                           "n_gold_patterns": len(gold),
                           "n_questions": len(questions)},
            }, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
