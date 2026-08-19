"""Investigation catalog: standardize candidate names into InvestigationConcept.

Builds the per-comparison-class candidate catalog from the event stream, mirrors
the v1 class structure (imaging / clinical_order / laboratory), and assigns each
candidate a stable ID, family, granularity and orderability flag (design doc §5.2).

First-line allowlists restrict the ANSWER space; the full per-class pool supplies
distractors (v1 decision: imaging gold stays first-line while distractors draw on
the broader imaging catalog).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .hashing import candidate_id
from .lab_panels import lab_panel, _OTHER

# First-line ED imaging modalities (answer space). Excludes MRI / Nuclear Med /
# vascular / interventional (follow-up / secondary studies). Exploratory placeholder.
IMAGING_ALLOWLIST = {"General Xray", "CT Scan", "Ultrasound"}

# Clinical-order allowlist: diagnostic/monitoring investigations (not logistics,
# treatments, or dispositions). Placeholder pending clinical review.
CLINICAL_ORDER_ALLOWLIST = {
    "Telemetry", "ECG", "Echo", "Vitals/Monitoring", "Blood tests",
}

CLASS_LABEL = {
    "imaging": "imaging study",
    "clinical_order": "monitoring/cardiac investigation",
    "laboratory": "laboratory panel",
}

COMPARISON_CLASSES = ("imaging", "clinical_order", "laboratory")


def image_family(name: str) -> str:
    s = (name or "").casefold()
    if any(k in s for k in ("xray", "x-ray", "radiograph")):
        return "xray"
    if any(k in s for k in ("ct", "computed tomography", "tomogram")):
        return "ct"
    if any(k in s for k in ("ultrasound", "sonograph", "echo")):
        return "ultrasound"
    if any(k in s for k in ("mri", "magnetic resonance")):
        return "mri"
    if any(k in s for k in ("nuclear", "pet", "spect")):
        return "nuclear"
    if any(k in s for k in ("vascular", "angiograph", "doppler", "duplex")):
        return "vascular"
    if "interventional" in s:
        return "interventional"
    return "other"


def clinical_family(name: str) -> str:
    s = (name or "").casefold()
    if any(k in s for k in ("telemetry", "monitoring", "vital")):
        return "monitoring"
    if any(k in s for k in ("ecg", "ekg", "echo")):
        return "cardiac"
    if "blood" in s:
        return "laboratory"
    return "other"


# Imaging granularity tiers (design doc §5.2 / §8.1). The benchmark's atomic
# answer-space tier is the GENERAL imaging modality ("specific"): the four
# plausibly-first-line modalities. Specialized modalities ("specialized") are
# almost never the first-line selection in the ED, so they make obviously-wrong
# distractors and are excluded from the distractor pool. Finer-grained
# body-part / interventional procedure names are "procedure" (also excluded).
_IMAGING_MODALITY_TIER = {
    "general xray", "general x-ray", "x-ray", "xray",
    "ct scan", "ct",
    "ultrasound",
    "mri", "magnetic resonance imaging",
}
_IMAGING_SPECIALIZED = {
    "nuclear med", "nuclear medicine", "nuclear scan",
    "noninvasive vascular",
    "interventional radiology",
}


def image_granularity(name: str) -> str:
    """Return the imaging granularity tier for ``name``.

    ``specific`` = general first-line modality (answer + distractor eligible);
    ``specialized`` = non-first-line modality (excluded from distractors);
    ``procedure`` = finer-grained body-part / interventional names (excluded).
    """
    s = (name or "").casefold()
    if s in _IMAGING_MODALITY_TIER:
        return "specific"
    if s in _IMAGING_SPECIALIZED:
        return "specialized"
    return "procedure"


@dataclass(frozen=True)
class InvestigationConcept:
    investigation_id: str
    canonical_name: str
    comparison_class: str
    family: str
    granularity: str
    is_orderable: bool
    source_visit_count: int


@dataclass
class Catalog:
    """Per-class candidate concepts: ``answers`` (rank-1 eligible) and ``pool``
    (distractor pool, a superset for imaging)."""

    answers: dict[str, list[InvestigationConcept]]
    pool: dict[str, list[InvestigationConcept]]

    def pool_names(self, comparison_class: str) -> list[str]:
        return [c.canonical_name for c in self.pool.get(comparison_class, [])]

    def answer_names(self, comparison_class: str) -> list[str]:
        return [c.canonical_name for c in self.answers.get(comparison_class, [])]


def _count_frame(events: pd.DataFrame, name_col: str) -> pd.DataFrame:
    g = (
        events.groupby(name_col, dropna=True)
        .agg(n=("event_id", "size"), n_adm=("hadm_id", "nunique"))
        .reset_index()
        .rename(columns={name_col: "candidate"})
    )
    return g[g["candidate"].notna() & (g["candidate"] != "")]


def _concepts(frame: pd.DataFrame, comparison_class: str,
              family_fn, granularity_fn=lambda name: "specific") -> list[InvestigationConcept]:
    out: list[InvestigationConcept] = []
    for row in frame.itertuples(index=False):
        name = str(row.candidate)
        out.append(InvestigationConcept(
            investigation_id=candidate_id(comparison_class, name),
            canonical_name=name,
            comparison_class=comparison_class,
            family=family_fn(name),
            granularity=granularity_fn(name),
            is_orderable=True,
            source_visit_count=int(row.n_adm),
        ))
    return out


def build_catalog(events: pd.DataFrame) -> Catalog:
    # imaging: full pool (all imaging studies); answers = first-line modalities.
    imaging = events[
        (events["event_kind"] == "imaging_ordered")
        & (events["entity_type"] == "imaging_study")
    ]
    imaging_pool = _count_frame(imaging, "source_label")
    imaging_answer = imaging_pool[
        imaging_pool["candidate"].isin(IMAGING_ALLOWLIST)
    ].copy()

    # clinical_order: allowlist is both the answer space and the pool.
    clinical = events[
        (events["event_kind"] == "clinical_ordered")
        & (events["entity_type"] == "clinical_order")
        & events["source_label"].isin(CLINICAL_ORDER_ALLOWLIST)
    ]
    clinical_frame = _count_frame(clinical, "source_label")

    # laboratory: panels (answer space == pool).
    lab = events[events["event_kind"] == "laboratory_resulted"].copy()
    lab["panel"] = lab["concept_id"].map(lab_panel)
    lab = lab[lab["panel"] != _OTHER]
    lab_frame = _count_frame(lab, "panel")

    return Catalog(
        answers={
            "imaging": _concepts(imaging_answer, "imaging", image_family, image_granularity),
            "clinical_order": _concepts(clinical_frame, "clinical_order", clinical_family),
            "laboratory": _concepts(lab_frame, "laboratory", lambda n: n.casefold()),
        },
        pool={
            "imaging": _concepts(imaging_pool, "imaging", image_family, image_granularity),
            "clinical_order": _concepts(clinical_frame, "clinical_order", clinical_family),
            "laboratory": _concepts(lab_frame, "laboratory", lambda n: n.casefold()),
        },
    )
