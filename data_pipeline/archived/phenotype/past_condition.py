"""P4 — past_condition (既往史) and sign (体征) feature tracks.

Two independent tracks, per the approved double-track decision:

* ICD track (deterministic, full cohort): ``condition_recorded_post_hoc``
  diagnoses mapped to past conditions via an exploratory heuristic — ICD
  "history of" Z-codes (Z80-Z99) plus a curated chronic-condition keyword list.
  Pending clinical review (POA semantics are weak in MIMIC-IV diagnoses_icd).
* NER track (text_ner_v2 sidecar): ``clinical_problem`` mentions with
  ``temporality == "historical"`` from the discharge-summary text.

``sign`` (physical-exam findings) has no structured source yet: the NER pilot
sidecar contains no ``physical_exam_finding`` entities, so the sign track is
declared BLOCKED until a physical-exam-section NER run exists.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd

# --- ICD track --------------------------------------------------------------

_HISTORY_ICD_PREFIXES = ("z8", "z9")  # ICD-10 Z80-Z99 "personal/family history"

# Exploratory chronic-condition keywords (substring match on the diagnosis name).
_CHRONIC_KEYWORDS = (
    "diabetes", "hypertension", "copd", "chronic obstructive", "asthma",
    "heart failure", "chronic kidney", "renal failure", "atrial fibrillation",
    "coronary artery", "hyperlipidemia", "hypothyroid", "gout", "osteoporosis",
    "epilepsy", "cirrhosis", "anemia of chronic", "depression", "anxiety",
    "obesity", "stroke", "cerebrovascular", "peripheral vascular",
)

# Trailing ICD-10 qualifiers that do not change the comorbidity concept.
_ICD_QUALIFIER_RE = re.compile(
    r",\s*(?:unspecified|unspec\b|not (?:elsewhere|otherwise) specified|site not specified|"
    r"without complications|not stated as uncontrolled|"
    r"without mention of complication[^,]*|"
    r"(?:initial|subsequent) encounter[^,]*|sequela[^,]*|"
    r"stage [^,]*|nos|uncompl(?:icated)?\s+adult|"
    r"nec\s*/\s*nos|type\s+(?:1|2|i{1,3})\s*(?:or\s+)?unspecified\s+type)\s*$",
    re.IGNORECASE,
)
_ICD_WITHOUT_RE = re.compile(r"\s+without\s+[^,]*$", re.IGNORECASE)
# "with X" suffixes that do not change the core comorbidity concept.
_ICD_WITH_RE = re.compile(
    r"\s+with\s+(?:unstable\s+angina(?:\s+pectoris)?"
    r"|(?:\(\s*acute\s*\)\s*|acute\s+)?exacerbation"
    r"|neurological\s+manifestations|foot\s+ulcer)\s*$",
    re.IGNORECASE,
)
# Space-separated trailing abbreviations (no comma before them).
_ICD_SPACE_SUFFIX_RE = re.compile(
    r"\s+(?:nec\s*/\s*nos|uncompl(?:icated)?\s+adult)\s*$",
    re.IGNORECASE,
)
# Leading "unspecified" does not change the core concept.
_ICD_UNSPECIFIED_PREFIX_RE = re.compile(r"^unspecified\s+", re.IGNORECASE)

# Z89 "acquired absence of ..." status codes collapse to one coarse surgical-history
# concept (they are granular anatomical statuses, not per-condition disease history).
_ICD_ACQUIRED_ABSENCE_RE = re.compile(r"^acquired absence of\b", re.IGNORECASE)

# Curated map: verbose/duplicate ICD diagnosis names -> concise clinical concept.
_ICD_CONCEPT_MAP = {
    "atherosclerotic heart disease of native coronary artery": "coronary artery disease",
    "coronary atherosclerosis of native coronary artery": "coronary artery disease",
    "hyperlipidemia": "hyperlipidemia",
    "other and unspecified hyperlipidemia": "hyperlipidemia",
    "essential (primary) hypertension": "hypertension",
    "essential hypertension": "hypertension",
    "hypertension nos": "hypertension",
    "hypertension": "hypertension",
    "congestive heart failure": "heart failure",
    "heart failure": "heart failure",
    "chronic diastolic (congestive) heart failure": "heart failure",
    "chronic systolic (congestive) heart failure": "heart failure",
    "acute on chronic diastolic (congestive) heart failure": "heart failure",
    "acute on chronic systolic (congestive) heart failure": "heart failure",
    "chronic kidney disease": "chronic kidney disease",
    "atrial fibrillation": "atrial fibrillation",
    "paroxysmal atrial fibrillation": "atrial fibrillation",
    "diabetes mellitus": "diabetes mellitus",
    "type 2 diabetes mellitus": "diabetes mellitus",
    "type 2 diabetes mellitus with diabetic chronic kidney disease": "diabetes mellitus",
    "diabetes": "diabetes mellitus",
    "personal history of nicotine dependence": "smoking history",
    "presence of coronary angioplasty implant and graft": "prior coronary intervention",
    "presence of aortocoronary bypass graft": "coronary bypass graft",
    "gout": "gout",
    "obesity": "obesity",
    "hypothyroidism": "hypothyroidism",
    "acquired hypothyroidism": "hypothyroidism",
    "chronic obstructive pulmonary disease": "copd",
    "asthma": "asthma",
    "asthma w status asthmat": "asthma",
    "asthma, unspecified, with acute exacerbation": "asthma",
    "asthma, chronic obstructive": "copd",
    "asthma, chronic obstructive, with acute exacerbation": "copd",
    "peripheral vascular disease": "peripheral vascular disease",
    "anxiety disorder": "anxiety",
    "anxiety state": "anxiety",
    "anxiety": "anxiety",
    "personal history of transient ischemic attack": "history of stroke/tia",
    "anemia in chronic kidney disease": "anemia of chronic kidney disease",
    "dependence on renal dialysis": "renal dialysis",
    "hypertensive heart disease with heart failure": "hypertensive heart disease",
    "hypertensive heart and chronic kidney disease": "hypertensive heart disease with ckd",
    "hypertensive chronic kidney disease": "hypertensive chronic kidney disease",
    # A3 additions: remaining verbose/abbreviated ICD names observed in the rules.
    "chronic systolic heart failure": "heart failure",
    "acute systolic (congestive) heart failure": "heart failure",
    "personal history of irradiation": "history of radiation therapy",
    "personal history of other venous thrombosis and embolism": "history of venous thromboembolism",
    "personal history of transient ischemic attack (tia), and cerebral infarction": "history of stroke/tia",
    "alcoholic cirrhosis of liver": "alcoholic cirrhosis",
    "alcoholic cirrhosis of liver with ascites": "alcoholic cirrhosis",
    "age-related osteoporosis": "osteoporosis",
    "presence of artificial knee joint, bilateral": "artificial joint",
    "status post administration of tpa (rtpa) in a different facility within the last 24 hours prior to admission to current facility": "recent tpa administration",
    "s/p admn tpa in diff fac w/n last 24 hr bef adm to crnt fac": "recent tpa administration",
    "hypertensive heart and chronic kidney disease with heart failure and stage 1 through stage 4 chronic kidney disease, or unspecified chronic kidney disease": "hypertensive heart disease with ckd",
    "hypertensive chronic kidney disease with stage 1 through stage 4 chronic kidney disease, or unspecified chronic kidney disease": "hypertensive chronic kidney disease",
}


def _normalize_icd_name(name: str) -> str:
    """Strip trailing ICD-10 qualifiers and map verbose names to concepts."""
    s = (name or "").strip()
    if _ICD_ACQUIRED_ABSENCE_RE.match(s):
        return "amputation/organ absence status"
    prev = None
    while prev != s:
        prev = s
        s = _ICD_QUALIFIER_RE.sub("", s).strip(" ,")
        s = _ICD_WITHOUT_RE.sub("", s).strip(" ,")
        s = _ICD_WITH_RE.sub("", s).strip(" ,")
        s = _ICD_SPACE_SUFFIX_RE.sub("", s).strip(" ,")
        s = _ICD_UNSPECIFIED_PREFIX_RE.sub("", s).strip(" ,")
    return _ICD_CONCEPT_MAP.get(s.casefold(), s)


def _past_condition_from_icd(concept_id: str, name: str) -> str | None:
    cid = (concept_id or "").casefold()
    code = cid.split(":", 1)[-1] if ":" in cid else cid
    if code.startswith(_HISTORY_ICD_PREFIXES):
        return _normalize_icd_name(name)
    nl = (name or "").casefold()
    for kw in _CHRONIC_KEYWORDS:
        if kw in nl:
            return _normalize_icd_name(name)
    return None


def extract_past_condition_icd(events: pd.DataFrame) -> pd.DataFrame:
    """hadm_id -> sorted past-condition names from post-hoc ICD diagnoses."""
    dx = events[
        (events["event_kind"] == "condition_recorded_post_hoc")
        & events["source_label"].notna()
    ]
    if dx.empty:
        return pd.DataFrame(columns=["hadm_id", "features"])
    dx = dx[["hadm_id", "concept_id", "source_label"]].drop_duplicates()
    recs: dict[str, set[str]] = {}
    for row in dx.itertuples(index=False):
        name = _past_condition_from_icd(row.concept_id, row.source_label)
        if name is not None:
            recs.setdefault(row.hadm_id, set()).add(name)
    return pd.DataFrame(
        [{"hadm_id": h, "features": sorted(v)} for h, v in sorted(recs.items())],
        columns=["hadm_id", "features"],
    )


# --- NER track --------------------------------------------------------------

# Light clinical abbreviation / phrase normalization so the NER surface text can
# be compared against the ICD track's formal names. Exploratory — pending
# clinical review (the full synonym/ontology layer is the standardization module's
# job, not this probe).
_NER_PAST_CONDITION_NORMALIZE = {
    "cad": "coronary artery disease",
    "chf": "congestive heart failure",
    "htn": "hypertension",
    "dm": "diabetes mellitus",
    "pna": "pneumonia",
    "copd": "copd",
    "ckd": "chronic kidney disease",
    "af": "atrial fibrillation",
    "afib": "atrial fibrillation",
    "mi": "myocardial infarction",
    "osa": "obstructive sleep apnea",
    "gord": "gastro-oesophageal reflux disease",
    "gerd": "gastro-oesophageal reflux disease",
    "pe": "pulmonary embolism",
    "dvt": "deep vein thrombosis",
    "tia": "transient ischemic attack",
    "cva": "stroke",
    "esrd": "end-stage renal disease",
    "pad": "peripheral arterial disease",
    "bph": "benign prostatic hyperplasia",
}

_HISTORY_PREFIXES = ("pmhx of ", "pmh of ", "h/o ", "history of ", "hx of ")


def _normalize_past_condition(surface: str) -> str:
    s = surface.strip()
    low = s.casefold()
    # strip "PMHx of ..." / "history of ..." prefixes
    for p in _HISTORY_PREFIXES:
        if low.startswith(p):
            s = s[len(p):].strip()
            low = s.casefold()
            break
    if low in _NER_PAST_CONDITION_NORMALIZE:
        return _NER_PAST_CONDITION_NORMALIZE[low]
    return s


def extract_past_condition_ner(mentions_path: Path) -> pd.DataFrame:
    """hadm_id -> sorted past-condition names from historical clinical_problem
    mentions in the text_ner_v2 entity sidecar (surface text lightly normalized)."""
    mentions_path = Path(mentions_path)
    if not mentions_path.exists():
        return pd.DataFrame(columns=["hadm_id", "features"])
    df = pd.read_parquet(mentions_path)
    m = df[
        (df["entity_type"] == "clinical_problem")
        & (df["temporality"] == "historical")
        & df["hadm_id"].notna()
    ]
    if m.empty:
        return pd.DataFrame(columns=["hadm_id", "features"])
    m = m[["hadm_id", "surface_text"]].drop_duplicates()
    recs: dict[str, set[str]] = {}
    for row in m.itertuples(index=False):
        recs.setdefault(row.hadm_id, set()).add(_normalize_past_condition(str(row.surface_text)))
    return pd.DataFrame(
        [{"hadm_id": h, "features": sorted(v)} for h, v in sorted(recs.items())],
        columns=["hadm_id", "features"],
    )


# --- sign track -------------------------------------------------------------

def extract_signs_ner(mentions_path: Path) -> pd.DataFrame:
    """physical_exam_finding mentions — BLOCKED until the sidecar contains them.

    Returns an empty frame (documented no-op) so the pipeline does not invent
    sign features from a source that has none.
    """
    mentions_path = Path(mentions_path)
    if not mentions_path.exists():
        return pd.DataFrame(columns=["hadm_id", "features"])
    df = pd.read_parquet(mentions_path)
    if "physical_exam_finding" not in set(df["entity_type"]):
        return pd.DataFrame(columns=["hadm_id", "features"])
    m = df[(df["entity_type"] == "physical_exam_finding") & df["hadm_id"].notna()]
    recs: dict[str, set[str]] = {}
    for row in m[["hadm_id", "surface_text"]].drop_duplicates().itertuples(index=False):
        recs.setdefault(row.hadm_id, set()).add(str(row.surface_text))
    return pd.DataFrame(
        [{"hadm_id": h, "features": sorted(v)} for h, v in sorted(recs.items())],
        columns=["hadm_id", "features"],
    )
