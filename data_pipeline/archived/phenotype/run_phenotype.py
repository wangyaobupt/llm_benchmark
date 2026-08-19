"""P6 — reproducible end-to-end phenotype build: visit features + condition space.

Loads the validated ``normalized_events.parquet`` (one split role), joins the
demographics sidecar, applies the decision-time gate, extracts typed condition
features, and enumerates the condition space. Writes hashed Parquet artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark_common.io import _sha256_file, _verify_normalized_events  # noqa: E402
from data_pipeline.archived.phenotype.absent_features import extract_absent_features  # noqa: E402
from data_pipeline.archived.phenotype.condition_space import enumerate_conditions  # noqa: E402
from data_pipeline.archived.phenotype.medication_features import extract_medication_features  # noqa: E402
from data_pipeline.archived.phenotype.past_condition import (  # noqa: E402
    extract_past_condition_icd,
    extract_past_condition_ner,
)
from data_pipeline.archived.phenotype.phenotype import build_feature_frame  # noqa: E402
from data_pipeline.archived.phenotype.sign_ner import filter_sign_features  # noqa: E402
from data_pipeline.archived.phenotype.temporal_gate import gate_events, index_times  # noqa: E402
from data_pipeline.archived.phenotype.vital_flags import extract_vital_flags  # noqa: E402

EVENTS = Path(
    r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full"
    r"\event_pipeline\normalization\normalized_events.parquet"
)
SPLIT = Path(
    r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet"
)
DEMOGRAPHICS = Path(r"D:\Projects\llm_benchmark\data\phenotype\hadm_demographics.parquet")
OUT_DIR = Path(r"D:\Projects\llm_benchmark\data\phenotype")

EVENT_COLS = ["event_id", "subject_id", "hadm_id", "event_kind", "entity_type",
              "source_label", "preferred_name", "source_concept_id", "concept_id",
              "assertion", "event_time", "evidence_phase", "value_numeric",
              "value_text", "value_structured_json", "unit"]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_events(events_path: Path, split_path: Path, role: str) -> tuple[pd.DataFrame, dict]:
    events_hash = _verify_normalized_events(events_path)
    split_hash = _file_sha256(split_path)
    split_df = pd.read_parquet(split_path)
    subjects = set(split_df[split_df["role"] == role]["subject_id"].astype(str))
    events = pq.read_table(events_path, columns=EVENT_COLS).to_pandas()
    events = events[events["subject_id"].astype(str).isin(subjects)]
    return events, {"events_sha256": events_hash, "split_sha256": split_hash,
                    "split_role": role, "n_subjects": len(subjects)}


def _union_past_condition(icd: pd.DataFrame, ner: pd.DataFrame) -> pd.DataFrame:
    """Union the ICD and NER past_condition tracks per hadm_id (deduplicated)."""
    if icd.empty:
        return ner
    if ner.empty:
        return icd
    merged = pd.concat([icd, ner], ignore_index=True)
    return (
        merged.groupby("hadm_id", sort=True)["features"]
        .agg(lambda lists: sorted({x for lst in lists for x in lst}))
        .reset_index()
    )


def build(
    events: pd.DataFrame,
    demographics: pd.DataFrame,
    *,
    min_conditions: int,
    max_conditions: int,
    min_feature_support: int | None = None,
    signs: pd.DataFrame | None = None,
    past_condition_ner: pd.DataFrame | None = None,
) -> dict:
    index_map = index_times(events)
    gated = gate_events(events, index_map)

    vital_flags = extract_vital_flags(gated)
    meds = extract_medication_features(gated)
    absent = extract_absent_features(gated)
    # past_condition reads the UNGATED post-hoc diagnoses (the diagnosis is the
    # source of the comorbidity/history proxy, not a presentation feature gated
    # by the decision time). ICD track is deterministic; NER track (text_ner_v2
    # clinical_problem historical mentions) is unioned in when provided.
    past = extract_past_condition_icd(events)
    if past_condition_ner is not None and not past_condition_ner.empty:
        past = _union_past_condition(past, past_condition_ner)
    frame = build_feature_frame(gated, demographics, vital_flags, meds, absent,
                                past_conditions=past, signs=signs)
    conditions = enumerate_conditions(frame, min_conditions, max_conditions,
                                      min_feature_support=min_feature_support)

    return {
        "n_admissions": int(events["hadm_id"].nunique()),
        "n_admissions_with_index": int(index_map["hadm_id"].nunique()),
        "n_features": int(frame["feature_id"].nunique()),
        "n_feature_rows": len(frame),
        "n_conditions": len(conditions),
        "features": frame,
        "conditions": conditions,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", type=Path, default=EVENTS)
    ap.add_argument("--split", type=Path, default=SPLIT)
    ap.add_argument("--demographics", type=Path, default=DEMOGRAPHICS)
    ap.add_argument("--role", default="development")
    ap.add_argument("--min-conditions", type=int, default=1)
    ap.add_argument("--max-conditions", type=int, default=4)
    ap.add_argument("--max-admissions", type=int, default=None)
    ap.add_argument("--min-feature-support", type=int, default=None)
    ap.add_argument("--sign-features", type=Path, default=None)
    ap.add_argument("--past-condition-ner", type=Path, default=None,
                    help="text_ner_v2 entity_mentions.parquet (NER track, unioned with ICD).")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)

    events, meta = load_events(args.events, args.split, args.role)
    if args.max_admissions is not None:
        hadms = sorted(events["hadm_id"].unique())[: args.max_admissions]
        events = events[events["hadm_id"].isin(set(hadms))]
    demographics = pd.read_parquet(args.demographics)
    demographics = demographics[demographics["hadm_id"].isin(set(events["hadm_id"]))]
    signs = pd.read_parquet(args.sign_features) if args.sign_features else None
    signs = filter_sign_features(signs)
    past_ner = extract_past_condition_ner(args.past_condition_ner) if args.past_condition_ner else None
    result = build(events, demographics,
                   min_conditions=args.min_conditions,
                   max_conditions=args.max_conditions,
                   min_feature_support=args.min_feature_support,
                   signs=signs, past_condition_ner=past_ner)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    feat_path = out_dir / f"visit_features_{args.role}.parquet"
    cond_path = out_dir / f"visit_conditions_{args.role}.parquet"
    result["features"].to_parquet(feat_path, index=False)
    result["conditions"].to_parquet(cond_path, index=False)

    summary = {
        "schema_version": "phenotype-visit-transactions/1.0.0",
        "input": meta,
        "demographics_sha256": _file_sha256(Path(args.demographics)),
        "min_conditions": args.min_conditions,
        "max_conditions": args.max_conditions,
        "min_feature_support": args.min_feature_support,
        "counts": {k: v for k, v in result.items()
                   if k in ("n_admissions", "n_admissions_with_index",
                            "n_features", "n_feature_rows", "n_conditions")},
        "outputs": {
            "visit_features": str(feat_path),
            "visit_conditions": str(cond_path),
        },
    }
    (out_dir / f"phenotype_manifest_{args.role}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
