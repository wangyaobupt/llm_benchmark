"""P4 sign track — physical-exam-finding extraction and NER input.

The NER pilot tags the whole discharge summary, which produced zero
``physical_exam_finding`` entities (findings were tagged as ``symptom_or_sign``/
``clinical_problem``). This module extracts the **Physical Exam** section so a
focused DeepSeek-Flash run can tag ``physical_exam_finding`` and produce ``sign``
features.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

# Common normal-finding shorthands / general-appearance descriptors that carry no
# discriminative value. Filtered at sign-load time (the mining lift/support gates
# would drop them anyway, but removing them here shrinks the condition space).
# Case-insensitive exact-phrase match.
SIGN_STOPLIST = {
    # cardiac / lung normal shorthands
    "rrr", "regular rate and rhythm",
    "ctab", "clear to auscultation bilaterally", "cta bilat", "cta bilaterally",
    # general appearance / perfusion
    "wwp", "warm", "well perfused", "well-perfused", "supple",
    "sclera anicteric", "anicteric",
    # abbreviated normal findings
    "nt", "nd", "nt/nd", "eomi", "nabs", "+bs", "perrla", "mmm", "ncat",
    "nc/at", "op clear",
}


def filter_sign_features(signs: pd.DataFrame) -> pd.DataFrame:
    """Drop normal-finding shorthands from a hadm_id -> features sign frame."""
    if signs is None or signs.empty or "features" not in signs.columns:
        return signs
    rows: list[dict] = []
    for rec in signs.itertuples(index=False):
        kept = [f for f in rec.features if f.casefold() not in SIGN_STOPLIST]
        if kept:
            rows.append({"hadm_id": rec.hadm_id, "features": kept})
    return pd.DataFrame(rows, columns=["hadm_id", "features"])


# Case-insensitive "Physical Exam" section header variants (leading char may be
# lost at chunk boundaries or by de-identification).
_EXAM_HEADER_RE = re.compile(
    r"^\s*(?:[a-z_]*\s)*"
    r"(?:physical\s+exam(?:ination)?|admission\s+exam|exam\s+on\s+admission"
    r"|exam\s+on\s+discharge|discharge\s+exam)"
    r"\s*:?\s*$",
    re.IGNORECASE,
)

# Known following section headers that terminate the physical-exam section.
_NEXT_SECTION_RE = re.compile(
    r"^\s*(?:discharge\s+(?:diagnos\w*|medications?|labs?|instructions?"
    r"|disposition|follow\s*up)|primary\s+diagnos\w*|secondary\s+diagnos\w*"
    r"|medications?|labs?|plan|assessment|impression|follow[\s-]*up"
    r"|disposition|hospital\s+course|active\s+problems?|procedures?)"
    r"\s*:?\s*$",
    re.IGNORECASE,
)


def extract_physical_exam(text: str) -> str | None:
    """Return the Physical Exam section text, or None if absent."""
    if not text:
        return None
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if _EXAM_HEADER_RE.match(line):
            start = i
            break
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start + 1:]:
        if _NEXT_SECTION_RE.match(line):
            break
        body.append(line)
    # also stop at a blank line followed by a clear new header (section title)
    out = "\n".join(body).strip()
    return out or None


def build_physical_exam_frame(documents_path: Path) -> pd.DataFrame:
    """Concatenate discharge-summary chunks per hadm_id and extract the section.

    Returns hadm_id -> physical_exam_text (only rows with a non-empty section).
    """
    df = pd.read_parquet(documents_path)
    ds = df[df["source_text_kind"] == "discharge_summary"]
    rows: list[dict] = []
    for hadm_id, grp in ds.groupby("hadm_id", sort=True):
        grp = grp.sort_values("chunk_index")
        full = "\n".join(grp["chunk_text"].fillna("").astype(str))
        section = extract_physical_exam(full)
        if section:
            rows.append({"hadm_id": hadm_id, "physical_exam_text": section})
    return pd.DataFrame(rows, columns=["hadm_id", "physical_exam_text"])
