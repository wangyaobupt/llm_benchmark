"""Deterministic first-cut generator: condition X -> behavioral gold -> MCQ.

Data source: data/test_1000_0812/event_pipeline_output/aggregation/processed_events.parquet
(the cleaning/normalization/review dirs are ACL-denied in this environment, but
processed_events carries every normalized event field plus source text).

Behavioral gold definition (exploratory):
  For each normalized presenting condition (ED chief complaint) and each
  comparison class, the candidate that is most frequently ordered (imaging /
  clinical orders) or resulted (laboratory, used as an ORDER proxy) across the
  development admissions in this 1000-admission sample.

No human annotation, no protocol freeze, no FDR/validation here. This is a
readiness probe, not a release.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow.parquet as pq
import pandas as pd

# make benchmark_common (project root) importable
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmark_common.conditions import (
    extract_conditions, _PHRASE_SYNONYMS, _SINGLE_TOKEN_SYNONYMS,
)
from benchmark_common.stats import (
    wilson_lower, binomial_greater_pvalue, benjamini_hochberg,
)
from benchmark_common.io import _sha256_file, _verify_normalized_events

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVENTS = (
    ROOT / "data" / "test_1000_0812" / "event_pipeline_output"
    / "aggregation" / "processed_events.parquet"
)


def _verify_input(events_path: Path) -> str:
    """Verify processed_events.parquet matches its aggregation manifest (fail-closed)."""
    manifest_path = events_path.parent / "aggregation_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"aggregation manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest["outputs"]["processed_events.parquet"]
    actual_size = events_path.stat().st_size
    if actual_size != expected["bytes"]:
        raise ValueError(
            f"input size drift: {actual_size} != {expected['bytes']} "
            f"(re-run aggregation or fix manifest)")
    actual_hash = hashlib.sha256(events_path.read_bytes()).hexdigest()
    if actual_hash != expected["sha256"]:
        raise ValueError("input SHA-256 drift vs aggregation manifest (fail-closed)")
    return actual_hash

# --- comparison class definitions -------------------------------------------

# clinical_order labels that are diagnostic/monitoring investigations (not
# logistics, treatments, or dispositions). Placeholder allowlist for the probe.
CLINICAL_ORDER_ALLOWLIST = {
    "Telemetry",
    "ECG",
    "Echo",
    "Vitals/Monitoring",
    "Blood tests",
}

# First-line ED imaging modalities only. Excludes follow-up/secondary studies
# (MRI, Nuclear Med, Noninvasive Vascular, Interventional*, Angio) so the gold
# reflects "which FIRST-LINE imaging is most discriminating", matching clinical
# intuition. Exploratory placeholder pending clinical review.
IMAGING_ALLOWLIST = {"General Xray", "CT Scan", "Ultrasound"}

CLASS_LABEL = {
    "imaging": "imaging study",
    "clinical_order": "monitoring/cardiac investigation",
    "laboratory": "laboratory panel",
}

# Frozen placeholder mapping from lab concept_id to a clinical panel/domain.
# Individual analytes are near-universal (BMP/CBC), so the lab class uses the
# PANEL as its candidate and ranks by selectivity (lift) rather than raw share.
LAB_PANEL_MAP = {
    # Basic metabolic / chemistry (universal)
    "lab:50971": "chemistry_bmp", "lab:50912": "chemistry_bmp",
    "lab:51006": "chemistry_bmp", "lab:50902": "chemistry_bmp",
    "lab:50983": "chemistry_bmp", "lab:50931": "chemistry_bmp",
    "lab:50868": "chemistry_bmp", "lab:50882": "chemistry_bmp",
    "lab:50960": "chemistry_bmp", "lab:50893": "chemistry_bmp",
    "lab:50970": "chemistry_bmp",
    # CBC / hematology (universal)
    "lab:51265": "cbc_hematology", "lab:51221": "cbc_hematology",
    "lab:51248": "cbc_hematology", "lab:51279": "cbc_hematology",
    "lab:51250": "cbc_hematology", "lab:51277": "cbc_hematology",
    "lab:51222": "cbc_hematology", "lab:51249": "cbc_hematology",
    "lab:51301": "cbc_hematology", "lab:52172": "cbc_hematology",
    "lab:51146": "cbc_hematology", "lab:51256": "cbc_hematology",
    "lab:51254": "cbc_hematology", "lab:51200": "cbc_hematology",
    "lab:51244": "cbc_hematology", "lab:51144": "cbc_hematology",
    "lab:52075": "cbc_hematology", "lab:52069": "cbc_hematology",
    "lab:51133": "cbc_hematology", "lab:52074": "cbc_hematology",
    "lab:52073": "cbc_hematology", "lab:52135": "cbc_hematology",
    # Coagulation
    "lab:51274": "coagulation", "lab:51237": "coagulation",
    "lab:51275": "coagulation", "lab:51214": "coagulation",
    "lab:50915": "coagulation", "lab:51297": "coagulation",
    # Cardiac markers
    "lab:51003": "cardiac_markers", "lab:50911": "cardiac_markers",
    "lab:50908": "cardiac_markers", "lab:50963": "cardiac_markers",
    # Liver
    "lab:50885": "liver_panel", "lab:50861": "liver_panel",
    "lab:50878": "liver_panel", "lab:50863": "liver_panel",
    "lab:50862": "liver_panel", "lab:50976": "liver_panel",
    "lab:50927": "liver_panel", "lab:50883": "liver_panel",
    "lab:50884": "liver_panel",
    # Pancreatic
    "lab:50956": "pancreatic", "lab:50867": "pancreatic",
    # Thyroid
    "lab:50993": "thyroid", "lab:50995": "thyroid",
    "lab:50994": "thyroid", "lab:51001": "thyroid",
    # Blood gas
    "lab:50820": "blood_gas", "lab:50821": "blood_gas",
    "lab:50818": "blood_gas", "lab:50802": "blood_gas",
    "lab:50804": "blood_gas", "lab:50822": "blood_gas",
    "lab:50824": "blood_gas", "lab:50806": "blood_gas",
    "lab:50808": "blood_gas", "lab:50817": "blood_gas",
    "lab:50803": "blood_gas", "lab:50813": "blood_gas",
    # Inflammatory / acute phase / tissue
    "lab:50954": "inflammatory", "lab:50889": "inflammatory",
    "lab:50924": "inflammatory", "lab:51288": "inflammatory",
    "lab:50866": "inflammatory",
    # Renal / other chemistry
    "lab:50920": "renal_function", "lab:51007": "renal_function",
    "lab:51082": "renal_function", "lab:51100": "renal_function",
    # Iron studies
    "lab:50952": "iron_studies", "lab:50998": "iron_studies",
    "lab:50953": "iron_studies",
    # Urinalysis
    "lab:51478": "urinalysis", "lab:51464": "urinalysis",
    "lab:51492": "urinalysis", "lab:51506": "urinalysis",
    "lab:51498": "urinalysis", "lab:51508": "urinalysis",
    "lab:51514": "urinalysis", "lab:51491": "urinalysis",
    "lab:51487": "urinalysis", "lab:51486": "urinalysis",
    "lab:51484": "urinalysis", "lab:51466": "urinalysis",
    "lab:51493": "urinalysis", "lab:51463": "urinalysis",
    "lab:51476": "urinalysis", "lab:51516": "urinalysis",
    "lab:51519": "urinalysis", "lab:51512": "urinalysis",
    "lab:51482": "urinalysis",
    # Toxicology / drug levels
    "lab:51009": "toxicology", "lab:50917": "toxicology",
    "lab:50922": "toxicology", "lab:50856": "toxicology",
    "lab:50981": "toxicology", "lab:50967": "toxicology",
    "lab:51008": "toxicology", "lab:50986": "toxicology",
    "lab:50929": "toxicology", "lab:50961": "toxicology",
    "lab:51079": "toxicology", "lab:51092": "toxicology",
    "lab:51090": "toxicology", "lab:51075": "toxicology",
    "lab:51071": "toxicology", "lab:51074": "toxicology",
    "lab:50880": "toxicology", "lab:50879": "toxicology",
    "lab:51989": "toxicology", "lab:51089": "toxicology",
}


def lab_panel(concept_id: str | None) -> str:
    return LAB_PANEL_MAP.get(concept_id, "other")


# --- exploratory statistical policy (protocol placeholders) -----------------

# Statistical helpers, condition normalization, and IO verification are
# imported from benchmark_common (shared across benchmark tasks).
# --- candidate catalog ------------------------------------------------------

@dataclass
class Catalog:
    imaging: pd.DataFrame
    clinical: pd.DataFrame
    laboratory: pd.DataFrame


def _candidate_frame(events: pd.DataFrame, name_col: str) -> pd.DataFrame:
    g = (events.groupby(name_col, dropna=True)
               .agg(n=("event_id", "size"), n_adm=("hadm_id", "nunique"))
               .sort_values("n_adm", ascending=False))
    g = g.reset_index().rename(columns={name_col: "candidate"})
    return g


def build_catalog(events: pd.DataFrame) -> Catalog:
    imaging = events[
        (events["event_kind"] == "imaging_ordered")
        & (events["entity_type"] == "imaging_study")
        & events["source_label"].notna()
    ]
    clinical = events[
        (events["event_kind"] == "clinical_ordered")
        & (events["entity_type"] == "clinical_order")
        & events["source_label"].isin(CLINICAL_ORDER_ALLOWLIST)
    ]
    lab = events[
        (events["event_kind"] == "laboratory_resulted")
        & events["preferred_name"].notna()
    ]
    return Catalog(
        imaging=_candidate_frame(imaging, "source_label"),
        clinical=_candidate_frame(clinical, "source_label"),
        laboratory=_candidate_frame(lab, "preferred_name"),
    )


# --- condition extraction ---------------------------------------------------

# --- behavioral gold --------------------------------------------------------

def _per_admission_orders(events: pd.DataFrame, kind: str, entity: str,
                          name_col: str, allowlist: set[str] | None) -> pd.DataFrame:
    m = (events["event_kind"] == kind) & (events["entity_type"] == entity)
    if allowlist is not None:
        m &= events["source_label"].isin(allowlist)
    sub = events[m & events[name_col].notna()][["hadm_id", name_col]].drop_duplicates()
    sub = sub.rename(columns={name_col: "candidate"})
    return sub


def _lab_panel_orders(events: pd.DataFrame) -> pd.DataFrame:
    """Map each laboratory result to its clinical panel; drop unmapped/rare."""
    lab = events[events["event_kind"] == "laboratory_resulted"].copy()
    lab["panel"] = lab["concept_id"].map(lab_panel)
    lab = lab[lab["panel"] != "other"]
    return (lab[["hadm_id", "panel"]].drop_duplicates()
               .rename(columns={"panel": "candidate"}))


def _lab_panel_pool(events: pd.DataFrame) -> list[str]:
    """Panel names ordered by admission coverage (for plausible distractors)."""
    lab = events[events["event_kind"] == "laboratory_resulted"].copy()
    lab["panel"] = lab["concept_id"].map(lab_panel)
    lab = lab[lab["panel"] != "other"]
    return (lab.groupby("panel")["hadm_id"].nunique()
               .sort_values(ascending=False).index.tolist())


def _candidate_pools(catalog: Catalog, events: pd.DataFrame,
                     min_baseline_share: float) -> dict[str, list[str]]:
    """Candidate pools for distractors, excluding rare (sub-threshold) candidates."""
    total_adm = events["hadm_id"].nunique()

    def _filter(cat: pd.DataFrame) -> list[str]:
        return cat[cat["n_adm"] / total_adm >= min_baseline_share]["candidate"].tolist()

    lab = events[events["event_kind"] == "laboratory_resulted"].copy()
    lab["panel"] = lab["concept_id"].map(lab_panel)
    lab = lab[lab["panel"] != "other"]
    lab_pool = (lab.groupby("panel")["hadm_id"].nunique()
                .rename("n_adm").reset_index())
    lab_pool = lab_pool[lab_pool["n_adm"] / total_adm >= min_baseline_share]
    lab_pool = lab_pool.sort_values("n_adm", ascending=False)["panel"].tolist()
    return {
        "imaging": _filter(catalog.imaging),
        "clinical_order": _filter(catalog.clinical),
        "laboratory": lab_pool,
    }


def build_gold(events: pd.DataFrame, cond: pd.DataFrame,
               catalog: Catalog, min_condition_support: int = 5,
               max_baseline_share: float = 0.85,
               min_baseline_share: float = 0.02,
               min_selectivity_share: float = 0.15,
               min_candidate_support: int = 10,
               fdr_q: float = 0.10,
               score_ratio_minimum: float = 1.5,
               min_share_gap: float = 0.10,
               z: float = 1.96,
               gold_semantics: str = "selectivity",
               psr_nco_min: int = 10,
               psr_p_min: float = 0.01,
               psr_r: float = 1.0) -> list[dict]:
    # gold_semantics: "likelihood" (v1 most-likely) | "selectivity" (v2
    # discriminative) | "psr" (v3, Li 2020 PSR = probability x specificity x
    # reliability). Lab never uses likelihood (universal panels degenerate it).
    if gold_semantics == "likelihood":
        imaging_mode = clinical_mode = "likelihood"
        lab_mode = "selectivity"
    elif gold_semantics == "selectivity":
        imaging_mode = clinical_mode = lab_mode = "selectivity"
    elif gold_semantics == "specificity_reliability":
        imaging_mode = clinical_mode = lab_mode = "specificity_reliability"
    else:  # psr
        imaging_mode = clinical_mode = lab_mode = "psr"
    classes = [
        ("imaging", _per_admission_orders(
            events, "imaging_ordered", "imaging_study", "source_label",
            IMAGING_ALLOWLIST),
         catalog.imaging, imaging_mode),
        ("clinical_order", _per_admission_orders(
            events, "clinical_ordered", "clinical_order", "source_label",
            CLINICAL_ORDER_ALLOWLIST), catalog.clinical, clinical_mode),
        ("laboratory", _lab_panel_orders(events), catalog.laboratory, lab_mode),
    ]
    rows: list[dict] = []
    for class_key, order_frame, cat, mode in classes:
        merged = cond.merge(order_frame, on="hadm_id", how="inner")
        pair = (merged.groupby(["condition", "candidate"], dropna=True)
                      .agg(n_adm=("hadm_id", "nunique"))
                      .reset_index())
        cond_support = merged.groupby("condition")["hadm_id"].nunique()
        base = (order_frame.groupby("candidate")["hadm_id"].nunique()
                .rename("baseline_adm"))
        total_adm = cond["hadm_id"].nunique()

        # collect every (condition, candidate) pair that clears the structural
        # gates, then apply a single BH-FDR pass per class.
        frames: list[pd.DataFrame] = []
        for cname, csup in cond_support.items():
            if csup < min_condition_support:
                continue
            sub = pair[pair["condition"] == cname].merge(
                base, on="candidate", how="left")
            sub["share"] = sub["n_adm"] / csup
            sub["baseline_share"] = sub["baseline_adm"] / total_adm
            sub["selectivity"] = (sub["share"]
                                  / sub["baseline_share"].replace(0, float("nan")))
            sub = sub[sub["baseline_share"] <= max_baseline_share]
            sub = sub[sub["baseline_share"] >= min_baseline_share]
            sub = sub[sub["baseline_adm"] >= min_candidate_support]
            sub = sub.assign(condition=cname, condition_support=int(csup))
            frames.append(sub)
        if not frames:
            continue
        df = pd.concat(frames, ignore_index=True)
        if df.empty:
            continue

        df["p_value"] = [
            binomial_greater_pvalue(int(k), int(n), float(p0))
            for k, n, p0 in zip(df["n_adm"], df["condition_support"],
                                df["baseline_share"])
        ]
        # FDR family = (condition, comparison class): apply BH within each
        # condition across its candidate panels (protocol
        # fdr_family_definition = condition_by_comparison_class).
        df["q_value"] = 0.0
        for cname, grp in df.groupby("condition"):
            df.loc[grp.index, "q_value"] = benjamini_hochberg(grp["p_value"].tolist())
        df["wilson_lower"] = [
            wilson_lower(int(k), int(n), z)
            for k, n in zip(df["n_adm"], df["condition_support"])
        ]
        # Li 2020 PSR: reliability = log10(max(1, 1 + Nco - Nco_min)) + R,
        # PSR = probability x specificity x reliability.
        df["reliability"] = [
            math.log10(max(1.0, 1 + int(k) - psr_nco_min)) + psr_r
            for k in df["n_adm"]
        ]
        df["psr"] = df["share"] * df["selectivity"] * df["reliability"]
        df["sr"] = df["selectivity"] * df["reliability"]

        if mode == "selectivity":
            # FDR is meaningful for the association claim ("elevated vs
            # baseline"); the likelihood classes keep "most common" instead.
            df = df[df["q_value"] <= fdr_q]
        elif mode in ("psr", "specificity_reliability"):
            # paper's graph-cleaning thresholds instead of FDR
            df = df[(df["n_adm"] >= psr_nco_min) & (df["share"] >= psr_p_min)]

        for cname, grp in df.groupby("condition"):
            if mode == "selectivity":
                grp = grp[(grp["share"] >= min_selectivity_share)
                          & (grp["selectivity"] >= score_ratio_minimum)]
                grp = grp.sort_values("selectivity", ascending=False)
                gold_basis = "behavioral_most_selective_fdr"
            elif mode == "psr":
                grp = grp.sort_values("psr", ascending=False)
                gold_basis = "behavioral_psr"
            elif mode == "specificity_reliability":
                grp = grp.sort_values("sr", ascending=False)
                gold_basis = "behavioral_specificity_reliability"
            else:
                grp = grp.sort_values("share", ascending=False)
                gold_basis = "behavioral_most_likely_ordered"
            top = grp.head(5)
            if top.empty:
                continue
            # uniqueness filter: drop ambiguous answers (top-2 share too close,
            # "多专科合理性 ~10pp" from the survey).
            if len(top) >= 2 and top.iloc[0]["share"] - top.iloc[1]["share"] < min_share_gap:
                continue
            gold_cand = top.iloc[0]
            rows.append({
                "class": class_key,
                "condition": cname,
                "condition_support": int(top.iloc[0]["condition_support"]),
                "gold_candidate": gold_cand["candidate"],
                "gold_share": round(float(gold_cand["share"]), 4),
                "gold_selectivity": round(float(gold_cand["selectivity"]), 3)
                                if pd.notna(gold_cand["selectivity"]) else None,
                "gold_psr": round(float(gold_cand["psr"]), 3),
                "gold_basis": gold_basis,
                "top_candidates": [
                    {"candidate": r["candidate"],
                     "n_adm": int(r["n_adm"]),
                     "share": round(float(r["share"]), 4),
                     "selectivity": round(float(r["selectivity"]), 3)
                                    if pd.notna(r["selectivity"]) else None,
                     "reliability": round(float(r["reliability"]), 3),
                     "psr": round(float(r["psr"]), 3),
                     "sr": round(float(r["sr"]), 3),
                     "p_value": round(float(r["p_value"]), 6),
                     "q_value": round(float(r["q_value"]), 6),
                     "wilson_lower": round(float(r["wilson_lower"]), 4)}
                    for _, r in top.iterrows()
                ],
            })
    return rows


# --- MCQ generation ---------------------------------------------------------

def generate_questions(gold_rows: list[dict],
                       candidate_pools: dict[str, list[str]] | None = None,
                       n_options: int = 4) -> list[dict]:
    qs: list[dict] = []
    for i, g in enumerate(gold_rows, start=1):
        gold = g["gold_candidate"]
        if candidate_pools:
            pool = candidate_pools.get(g["class"], [])
        else:
            pool = [c["candidate"] for c in g.get("top_candidates", [])]
        distractors = [c for c in pool if c != gold][: n_options - 1]
        if len(distractors) < n_options - 1:
            continue
        options = [gold] + distractors
        cls_label = CLASS_LABEL[g["class"]]
        if g["gold_basis"] == "behavioral_most_likely_ordered":
            stem = (f"A patient presents to the emergency department with "
                    f"{g['condition']}. Which {cls_label} is most likely to be "
                    f"ordered?")
        else:
            stem = (f"A patient presents to the emergency department with "
                    f"{g['condition']}. Which {cls_label} is most strongly "
                    f"associated with this presentation?")
        qs.append({
            "question_id": f"q_expl_{i:04d}",
            "task": "investigation_selection",
            "comparison_class": g["class"],
            "condition": g["condition"],
            "condition_support": g["condition_support"],
            "stem": stem,
            "options": options,
            "answer_index": 0,
            "answer": gold,
            "gold_basis": g["gold_basis"],
            "status": "exploratory_unreviewed",
            "candidate_counts": [
                {"candidate": c["candidate"], "n_adm": c["n_adm"],
                 "share": c["share"], "selectivity": c["selectivity"]}
                for c in g["top_candidates"]
            ],
        })
    return qs


# --- main -------------------------------------------------------------------

def run(events_path: Path | None = None,
        min_condition_support: int = 5,
        max_baseline_share: float = 0.85,
        min_selectivity_share: float = 0.15,
        min_candidate_support: int = 10,
        fdr_q: float = 0.10,
        score_ratio_minimum: float = 1.5,
        gold_semantics: str = "psr",
        psr_nco_min: int = 10,
        psr_p_min: float = 0.01,
        psr_r: float = 1.0,
        out_dir: Path | None = None) -> dict:
    if events_path is None:
        events_path = DEFAULT_EVENTS
    input_sha256 = _verify_input(events_path)
    cols = ["event_id", "subject_id", "hadm_id", "event_kind", "entity_type",
            "source_label", "preferred_name", "concept_id", "assertion"]
    events = pq.read_table(events_path, columns=cols).to_pandas()

    catalog = build_catalog(events)
    cond = extract_conditions(events)
    gold = build_gold(events, cond, catalog,
                      min_condition_support=min_condition_support,
                      max_baseline_share=max_baseline_share,
                      min_selectivity_share=min_selectivity_share,
                      min_candidate_support=min_candidate_support,
                      fdr_q=fdr_q,
                      score_ratio_minimum=score_ratio_minimum,
                      gold_semantics=gold_semantics,
                      psr_nco_min=psr_nco_min,
                      psr_p_min=psr_p_min,
                      psr_r=psr_r)
    candidate_pools = {
        "imaging": catalog.imaging["candidate"].tolist(),
        "clinical_order": catalog.clinical["candidate"].tolist(),
        "laboratory": _lab_panel_pool(events),
    }
    questions = generate_questions(gold, candidate_pools)

    params = {
        "gold_semantics": gold_semantics,
        "min_condition_support": min_condition_support,
        "max_baseline_share": max_baseline_share,
        "min_selectivity_share": min_selectivity_share,
        "min_candidate_support": min_candidate_support,
        "fdr_q": fdr_q,
        "score_ratio_minimum": score_ratio_minimum,
        "psr_nco_min": psr_nco_min,
        "psr_p_min": psr_p_min,
        "psr_r": psr_r,
        "clinical_order_allowlist": sorted(CLINICAL_ORDER_ALLOWLIST),
        "lab_panel_map": dict(sorted(LAB_PANEL_MAP.items())),
        "phrase_synonyms": dict(sorted(_PHRASE_SYNONYMS.items())),
        "single_token_synonyms": dict(sorted(_SINGLE_TOKEN_SYNONYMS.items())),
    }

    summary = {
        "status": "exploratory_unreviewed",
        "gold_semantics": gold_semantics,
        "source": str(events_path),
        "input_sha256": input_sha256,
        "admissions_total": int(events["hadm_id"].nunique()),
        "admissions_with_condition": int(cond["hadm_id"].nunique()),
        "candidate_catalog": {
            "imaging": catalog.imaging.head(20).to_dict("records"),
            "clinical_order": catalog.clinical.to_dict("records"),
            "laboratory": catalog.laboratory.head(40).to_dict("records"),
        },
        "params": params,
        "n_gold_patterns": len(gold),
        "n_questions": len(questions),
        "gold_patterns": gold,
        "questions": questions,
    }

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        with (out_dir / "questions.jsonl").open("w", encoding="utf-8") as fh:
            for q in questions:
                fh.write(json.dumps(q, ensure_ascii=False) + "\n")
        (out_dir / "gold_patterns.jsonl").open("w", encoding="utf-8").write(
            "\n".join(json.dumps(g, ensure_ascii=False) for g in gold) + "\n")
        # self-describing run manifest: input + params + counts, so a run is
        # auditable against the exact input hash and parameter set.
        run_manifest = {
            "schema": "investigation-selection-exploratory-manifest/1.0.0",
            "status": "exploratory_unreviewed",
            "input": {"path": str(events_path), "sha256": input_sha256,
                      "bytes": events_path.stat().st_size},
            "params": params,
            "counts": {
                "admissions_total": summary["admissions_total"],
                "admissions_with_condition": summary["admissions_with_condition"],
                "n_gold_patterns": len(gold),
                "n_questions": len(questions),
            },
            "outputs": {
                "summary.json": None, "questions.jsonl": None,
                "gold_patterns.jsonl": None,
            },
        }
        (out_dir / "run_manifest.json").write_text(
            json.dumps(run_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return summary


# --- full-cohort split-aware runner -----------------------------------------

def run_split(events_path: Path, split_path: Path, role: str = "development",
              gold_semantics: str = "selectivity",
              min_condition_support: int = 5,
              max_baseline_share: float = 0.85,
              min_baseline_share: float = 0.02,
              min_selectivity_share: float = 0.15,
              min_candidate_support: int = 10,
              fdr_q: float = 0.10,
              score_ratio_minimum: float = 1.5,
              min_share_gap: float = 0.10,
              out_dir: Path | None = None) -> dict:
    """Run the gold + MCQ generation on one split role of the full cohort.

    Reproducibility: verifies the normalized_events hash against its
    workflow_manifest, binds the split artifact by SHA-256, filters events to
    the role's subjects, and emits a run manifest recording both hashes.
    """
    events_path = Path(events_path)
    split_path = Path(split_path)
    events_hash = _verify_normalized_events(events_path)
    split_hash = _sha256_file(split_path)

    split_df = pd.read_parquet(split_path)
    if "role" not in split_df.columns or "subject_id" not in split_df.columns:
        raise ValueError("split artifact must have subject_id + role columns")
    role_subjects = set(split_df[split_df["role"] == role]["subject_id"].astype(str))
    if not role_subjects:
        raise ValueError(f"split role '{role}' is empty")

    cols = ["event_id", "subject_id", "hadm_id", "event_kind", "entity_type",
            "source_label", "preferred_name", "concept_id", "assertion"]
    events = pq.read_table(events_path, columns=cols).to_pandas()
    events = events[events["subject_id"].astype(str).isin(role_subjects)]
    if events.empty:
        raise ValueError("no events for the selected split role")

    catalog = build_catalog(events)
    cond = extract_conditions(events)
    gold = build_gold(events, cond, catalog,
                      min_condition_support=min_condition_support,
                      max_baseline_share=max_baseline_share,
                      min_baseline_share=min_baseline_share,
                      min_selectivity_share=min_selectivity_share,
                      min_candidate_support=min_candidate_support,
                      fdr_q=fdr_q,
                      score_ratio_minimum=score_ratio_minimum,
                      min_share_gap=min_share_gap,
                      gold_semantics=gold_semantics)
    candidate_pools = _candidate_pools(catalog, events, min_baseline_share)
    questions = generate_questions(gold, candidate_pools)

    params = {
        "gold_semantics": gold_semantics,
        "min_condition_support": min_condition_support,
        "max_baseline_share": max_baseline_share,
        "min_baseline_share": min_baseline_share,
        "min_selectivity_share": min_selectivity_share,
        "min_candidate_support": min_candidate_support,
        "fdr_q": fdr_q,
        "score_ratio_minimum": score_ratio_minimum,
        "min_share_gap": min_share_gap,
        "clinical_order_allowlist": sorted(CLINICAL_ORDER_ALLOWLIST),
        "lab_panel_map": dict(sorted(LAB_PANEL_MAP.items())),
        "phrase_synonyms": dict(sorted(_PHRASE_SYNONYMS.items())),
        "single_token_synonyms": dict(sorted(_SINGLE_TOKEN_SYNONYMS.items())),
    }

    summary = {
        "status": "exploratory_unreviewed",
        "gold_semantics": gold_semantics,
        "split_role": role,
        "events_path": str(events_path),
        "events_sha256": events_hash,
        "split_path": str(split_path),
        "split_sha256": split_hash,
        "admissions_total": int(events["hadm_id"].nunique()),
        "subjects_total": int(events["subject_id"].nunique()),
        "admissions_with_condition": int(cond["hadm_id"].nunique()),
        "candidate_catalog": {
            "imaging": catalog.imaging.head(20).to_dict("records"),
            "clinical_order": catalog.clinical.to_dict("records"),
            "laboratory": catalog.laboratory.head(40).to_dict("records"),
        },
        "params": params,
        "n_gold_patterns": len(gold),
        "n_questions": len(questions),
        "gold_patterns": gold,
        "questions": questions,
    }

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        with (out_dir / "questions.jsonl").open("w", encoding="utf-8") as fh:
            for q in questions:
                fh.write(json.dumps(q, ensure_ascii=False) + "\n")
        (out_dir / "gold_patterns.jsonl").open("w", encoding="utf-8").write(
            "\n".join(json.dumps(g, ensure_ascii=False) for g in gold) + "\n")
        run_manifest = {
            "schema": "investigation-selection-exploratory-manifest/1.0.0",
            "status": "exploratory_unreviewed",
            "input": {"path": str(events_path), "sha256": events_hash,
                      "bytes": events_path.stat().st_size},
            "split": {"path": str(split_path), "sha256": split_hash,
                      "role": role},
            "params": params,
            "counts": {
                "admissions_total": summary["admissions_total"],
                "subjects_total": summary["subjects_total"],
                "admissions_with_condition": summary["admissions_with_condition"],
                "n_gold_patterns": len(gold),
                "n_questions": len(questions),
            },
            "outputs": {
                "summary.json": None, "questions.jsonl": None,
                "gold_patterns.jsonl": None,
            },
        }
        (out_dir / "run_manifest.json").write_text(
            json.dumps(run_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return summary


def validate_rules(dev_gold: list[dict], events: pd.DataFrame,
                   min_condition_support: int = 10,
                   max_baseline_share: float = 0.85,
                   min_baseline_share: float = 0.02,
                   min_candidate_support: int = 10) -> dict:
    """Check whether development gold rules generalize to independent patients.

    For each development rule (condition, class -> gold_candidate), recompute
    the candidate ranking on the provided (validation) events and record the
    gold candidate's rank. Returns per-rule results + a concordance summary.
    """
    catalog = build_catalog(events)
    cond = extract_conditions(events)
    order_frames = {
        "imaging": _per_admission_orders(
            events, "imaging_ordered", "imaging_study", "source_label",
            IMAGING_ALLOWLIST),
        "clinical_order": _per_admission_orders(
            events, "clinical_ordered", "clinical_order", "source_label",
            CLINICAL_ORDER_ALLOWLIST),
        "laboratory": _lab_panel_orders(events),
    }
    total_adm = cond["hadm_id"].nunique()
    results: list[dict] = []
    for g in dev_gold:
        class_key = g["class"]
        condition = g["condition"]
        gold = g["gold_candidate"]
        order_frame = order_frames[class_key]
        base = (order_frame.groupby("candidate")["hadm_id"].nunique()
                .rename("baseline_adm"))
        cond_adm = cond[cond["condition"] == condition]
        if cond_adm.empty:
            results.append({"class": class_key, "condition": condition,
                            "gold_candidate": gold, "status": "condition_absent"})
            continue
        csup = int(cond_adm["hadm_id"].nunique())
        if csup < min_condition_support:
            results.append({"class": class_key, "condition": condition,
                            "gold_candidate": gold,
                            "status": "insufficient_support",
                            "validation_support": csup})
            continue
        merged = cond_adm.merge(order_frame, on="hadm_id", how="inner")
        pair = (merged.groupby("candidate")["hadm_id"].nunique()
                .reset_index(name="n_adm"))
        pair = pair.merge(base, on="candidate", how="left")
        pair = pair[pair["baseline_adm"] >= min_candidate_support]
        pair["share"] = pair["n_adm"] / csup
        pair["baseline_share"] = pair["baseline_adm"] / total_adm
        pair["selectivity"] = (pair["share"]
                               / pair["baseline_share"].replace(0, float("nan")))
        pair = pair[pair["baseline_share"] <= max_baseline_share]
        pair = pair[pair["baseline_share"] >= min_baseline_share]
        pair = pair.sort_values("selectivity", ascending=False).reset_index(drop=True)
        if pair.empty:
            results.append({"class": class_key, "condition": condition,
                            "gold_candidate": gold,
                            "status": "no_eligible_candidate",
                            "validation_support": csup})
            continue
        idx = pair.index[pair["candidate"] == gold]
        rank = int(idx[0]) + 1 if len(idx) else None
        gold_sel = round(float(pair.loc[idx[0], "selectivity"]), 3) if len(idx) else None
        results.append({
            "class": class_key, "condition": condition,
            "gold_candidate": gold, "status": "checked",
            "validation_support": csup,
            "gold_rank": rank,
            "gold_selectivity_validation": gold_sel,
            "top_candidate_validation": pair.iloc[0]["candidate"],
            "concordant_rank1": rank == 1,
            "concordant_top3": rank is not None and rank <= 3,
        })
    checked = [r for r in results if r.get("status") == "checked"]
    n_checked = len(checked)
    n_rank1 = sum(1 for r in checked if r["concordant_rank1"])
    n_top3 = sum(1 for r in checked if r["concordant_top3"])
    summary = {
        "n_rules": len(dev_gold),
        "n_checked": n_checked,
        "n_condition_absent": sum(1 for r in results if r.get("status") == "condition_absent"),
        "n_insufficient_support": sum(1 for r in results if r.get("status") == "insufficient_support"),
        "n_no_eligible_candidate": sum(1 for r in results if r.get("status") == "no_eligible_candidate"),
        "rank1_concordance": round(n_rank1 / n_checked, 4) if n_checked else None,
        "top3_concordance": round(n_top3 / n_checked, 4) if n_checked else None,
        "by_class": {},
    }
    for cls in ("imaging", "clinical_order", "laboratory"):
        c = [r for r in checked if r["class"] == cls]
        if c:
            summary["by_class"][cls] = {
                "n_checked": len(c),
                "rank1_concordance": round(sum(1 for r in c if r["concordant_rank1"]) / len(c), 4),
                "top3_concordance": round(sum(1 for r in c if r["concordant_top3"]) / len(c), 4),
            }
    return {"summary": summary, "results": results}
