"""Chief-complaint normalization and extraction (shared across tasks)."""
from __future__ import annotations

import re

import pandas as pd

# Phrase-level synonyms (applied before splitting), preserving spaces inside
# multi-word complaints so "chest pain" stays "chest pain".
_PHRASE_SYNONYMS = {
    "s/p fall": "fall",
    "s/p fall on floor": "fall",
    "abd pain": "abdominal pain",
    "abdo pain": "abdominal pain",
    "abdominal pain": "abdominal pain",
    "abnormal lab values": "abnormal labs",
    "abnormal labs": "abnormal labs",
    "difficulty breathing": "shortness of breath",
    "shortness of breath": "shortness of breath",
    "altered mental status": "altered mental status",
    "chest pain": "chest pain",
    "lower back pain": "lower back pain",
    "failure to thrive": "failure to thrive",
    "bright red blood per rectum": "bright red blood per rectum",
}

# Single-token abbreviation synonyms (applied to whole phrases and, for
# multi-word phrases, token-by-token so laterality / quadrant prefixes map).
_SINGLE_TOKEN_SYNONYMS = {
    "cp": "chest pain", "c/p": "chest pain",
    "sob": "shortness of breath", "dib": "shortness of breath",
    "doe": "dyspnea on exertion",
    "n/v": "nausea/vomiting", "n/v/d": "nausea/vomiting/diarrhea",
    "brbpr": "bright red blood per rectum",
    "ams": "altered mental status", "htn": "hypertension", "copd": "copd",
    "cva": "stroke", "ich": "intracranial hemorrhage",
    "sdh": "subdural hematoma", "sah": "subarachnoid hemorrhage",
    "mvc": "motor vehicle collision", "ili": "influenza-like illness",
    "sbo": "small bowel obstruction", "gib": "gi bleed",
    "chf": "congestive heart failure", "pe": "pulmonary embolism",
    "dvt": "deep vein thrombosis", "ftt": "failure to thrive",
    "mi": "myocardial infarction", "uti": "urinary tract infection",
    "arf": "acute renal failure", "dka": "diabetic ketoacidosis",
    "ha": "headache", "h/a": "headache", "pna": "pneumonia",
    "od": "overdose", "svt": "supraventricular tachycardia",
    "lbp": "lower back pain", "sz": "seizure",
    "tia": "transient ischemic attack",
    "nstemi": "nstemi", "stemi": "stemi",
    "l": "left", "r": "right", "b": "bilateral",
    "ruq": "right upper quadrant", "luq": "left upper quadrant",
    "rlq": "right lower quadrant", "llq": "left lower quadrant",
}

# Clearly-garbage normalized conditions (placeholders, junk tokens).
CONDITION_BLACKLIST = {
    "unknown-cc", "___", "none", "n/a", "na", "unknown", "other", "test",
    "n", "t", "1", ".", "-",
}

_QUALIFIER_RE = re.compile(r"\([^)]*\)")
_MULTI_SPACE_RE = re.compile(r"\s+")


def _is_garbage_condition(norm: str) -> bool:
    if norm in CONDITION_BLACKLIST:
        return True
    if len(norm) <= 1:
        return True
    if not any(ch.isalnum() for ch in norm):
        return True
    return False


def normalize_condition(raw: str) -> tuple[str, bool]:
    """Return (normalized condition, transfer_in).

    Splits only on comma/semicolon (multi-complaint separators), NOT on
    whitespace, so multi-word complaints retain their spaces. Complaints are
    order-normalized by sorting.
    """
    if raw is None:
        return ("", False)
    s = raw.strip().lower()
    transfer_in = False
    if re.search(r",?\s*transfer$", s):
        transfer_in = True
        s = re.sub(r",?\s*transfer$", "", s).strip()
    s = _QUALIFIER_RE.sub(" ", s)
    s = _MULTI_SPACE_RE.sub(" ", s).strip(" ,;")
    phrases = [p.strip() for p in re.split(r"[;,]", s) if p.strip()]
    out = []
    for p in phrases:
        p = _PHRASE_SYNONYMS.get(p, p)
        if " " in p:
            toks = [_SINGLE_TOKEN_SYNONYMS.get(t, t) for t in p.split()]
            p = " ".join(toks)
        else:
            p = _SINGLE_TOKEN_SYNONYMS.get(p, p)
        out.append(p)
    s = ", ".join(sorted(dict.fromkeys(out)))
    return (s, transfer_in)


def extract_conditions(events: pd.DataFrame) -> pd.DataFrame:
    cc = events[events["event_kind"] == "symptom_reported"].copy()
    cc["norm"], cc["transfer_in"] = zip(*cc["source_label"].map(normalize_condition))
    cc = cc[cc["norm"] != ""]
    cc = cc[~cc["norm"].map(_is_garbage_condition)]
    g = (cc.groupby("hadm_id")
           .agg(condition=("norm", lambda s: ", ".join(dict.fromkeys(s))),
                condition_raw=("source_label", lambda s: " | ".join(dict.fromkeys(s))),
                transfer_in=("transfer_in", "max"))
           .reset_index())
    return g
