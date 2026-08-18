"""Stage orchestration: mine -> lock -> generate -> review -> human queue -> gold.

Coordinates the deterministic data layer with the isolated LLM generation and
review layers, writes every intermediate artifact atomically, and exports gold
fail-closed (design doc §3, §13, §16).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .audit import read_jsonl, write_csv_utf8sig, write_json, write_jsonl
from .catalog import build_catalog
from .client import StructuredLLMClient
from .conditions import extract_condition_frame
from .constants import PIPELINE_VERSION, PROMPT_VERSION, SCHEMA_VERSION
from .distractors import lock_options
from .generation import generate_questions
from .mining import mine_rules
from .review import review_questions
from evaluation_pipeline.governance.legacy import (
    LegacyArtifactError,
    assert_release_ids_not_invalidated,
)

HUMAN_QUEUE_HEADER = [
    "question_id", "stem", "option_a", "option_b", "option_c", "option_d",
    "correct_option", "correct_answer", "automatic_status", "automatic_reason",
    "human_decision", "reviewer_id", "reviewed_at", "notes",
]


def _source_texts(cond: pd.DataFrame) -> dict[str, str]:
    out: dict[str, str] = {}
    for c, raw in zip(cond["condition"], cond["condition_raw"]):
        if c not in out and raw:
            out[c] = str(raw)
    return out


def apply_human_decisions(reviewed: list[dict],
                          human_decisions: dict[str, str] | None) -> list[dict]:
    decisions = human_decisions or {}
    out: list[dict] = []
    for q in reviewed:
        q = dict(q)
        d = decisions.get(q["question_id"])
        if d == "approved":
            q["human_review_status"] = "approved"
        elif d in ("rejected", "revise"):
            q["human_review_status"] = "rejected"
        out.append(q)
    return out


def export_gold(reviewed: list[dict], *, profile: str,
                release_policy: dict[str, Any] | None = None) -> list[dict]:
    """Fail-closed gold gate (design doc §13.2 / logic doc §7.3)."""
    policy = release_policy or {}
    allowed_schemas = set(policy.get("allowed_schema_versions", [SCHEMA_VERSION]))
    allowed_prompts = set(policy.get("allowed_prompt_versions", [PROMPT_VERSION]))
    gold: list[dict] = []
    for q in reviewed:
        try:
            assert_release_ids_not_invalidated([q])
        except LegacyArtifactError:
            # Known legacy lineage is excluded from release.  The direct gate
            # remains raising so callers cannot mistake exclusion for approval.
            continue
        if profile == "exploratory":
            continue
        if q.get("automatic_review_status") != "candidate_passed":
            continue
        if q.get("human_review_status") != "approved":
            continue
        if q.get("schema_version") not in allowed_schemas:
            continue
        if q.get("prompt_version") not in allowed_prompts:
            continue
        gold.append(q)
    return gold


def export_human_queue(reviewed: list[dict], review_records: list[dict],
                       out_dir: Path) -> list[dict]:
    passed = []
    for q in reviewed:
        if q["automatic_review_status"] != "candidate_passed":
            continue
        try:
            assert_release_ids_not_invalidated([q])
        except LegacyArtifactError:
            # Fail closed at the review boundary: legacy records are not queued.
            continue
        passed.append(q)
    reason_by_id = {r["question_id"]: r.get("concise_reason", "") for r in review_records}
    rows = []
    for q in passed:
        rows.append([
            q["question_id"], q["stem"],
            q["options"]["A"], q["options"]["B"], q["options"]["C"], q["options"]["D"],
            q["correct_option"], q["correct_answer"], q["automatic_review_status"],
            reason_by_id.get(q["question_id"], ""),
            "", "", "", "",
        ])
    if out_dir is not None:
        write_csv_utf8sig(out_dir / "human_review_queue.csv", HUMAN_QUEUE_HEADER, rows)
    return passed


def run_pipeline(
    events: pd.DataFrame,
    thresholds: dict,
    client: StructuredLLMClient,
    generate_prompt: str,
    review_prompt: str,
    *,
    profile: str = "exploratory",
    human_decisions: dict[str, str] | None = None,
    release_policy: dict[str, Any] | None = None,
    out_dir: Path | None = None,
    generator_model: str | None = None,
    reviewer_model: str | None = None,
    input_meta: dict[str, Any] | None = None,
) -> dict:
    catalog = build_catalog(events)
    cond = extract_condition_frame(events)
    accepted, rejected = mine_rules(events, cond, catalog, thresholds)
    locked, lock_failures = lock_options(accepted, catalog)
    source_texts = _source_texts(cond)
    candidates, gen_failures = generate_questions(
        locked, client, generate_prompt, source_texts, generator_model=generator_model
    )
    reviewed, review_records = review_questions(
        candidates, client, review_prompt, reviewer_model=reviewer_model
    )
    reviewed = apply_human_decisions(reviewed, human_decisions)
    gold = export_gold(reviewed, profile=profile, release_policy=release_policy)

    summary: dict[str, Any] = {
        "pipeline_version": PIPELINE_VERSION,
        "run_profile": profile,
        "counts": {
            "n_admissions": int(events["hadm_id"].nunique()),
            "n_conditions": int(cond["condition"].nunique()),
            "n_rules_accepted": len(accepted),
            "n_rules_rejected": len(rejected),
            "n_locked": len(locked),
            "n_insufficient_distractors": len(lock_failures),
            "n_candidates": len(candidates),
            "n_generation_failures": len(gen_failures),
            "n_reviewed": len(reviewed),
            "n_candidate_passed": sum(
                1 for q in reviewed if q["automatic_review_status"] == "candidate_passed"
            ),
            "n_gold": len(gold),
        },
        "generator_model": generator_model or client.model_name,
        "reviewer_model": reviewer_model or client.model_name,
        "prompt_version": PROMPT_VERSION,
        "thresholds": thresholds,
    }

    if out_dir is not None:
        out_dir = Path(out_dir)
        write_jsonl(out_dir / "conditional_rules.jsonl", accepted)
        write_jsonl(out_dir / "conditional_rules_rejected.jsonl", rejected)
        write_jsonl(out_dir / "distractor_failures.jsonl", lock_failures)
        write_jsonl(out_dir / "questions_candidates.jsonl", candidates)
        write_jsonl(out_dir / "questions_reviewed.jsonl", reviewed)
        write_jsonl(out_dir / "review_records.jsonl", review_records)
        write_jsonl(out_dir / "generation_failures.jsonl", gen_failures)
        export_human_queue(reviewed, review_records, out_dir)
        write_jsonl(out_dir / "questions_gold.jsonl", gold)
        write_json(out_dir / "summary.json", summary)
        write_json(out_dir / "manifest.json", _manifest(summary, input_meta))
    return summary


def _manifest(summary: dict, input_meta: dict[str, Any] | None) -> dict:
    meta = input_meta or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": summary["pipeline_version"],
        "run_profile": summary["run_profile"],
        "input": {
            "events_sha256": meta.get("events_sha256", ""),
            "split_sha256": meta.get("split_sha256", ""),
            "split_role": meta.get("split_role", ""),
        },
        "thresholds": summary["thresholds"],
        "generator_model": summary["generator_model"],
        "reviewer_model": summary["reviewer_model"],
        "prompt_version": summary["prompt_version"],
        "counts": summary["counts"],
    }


def load_events(events_path: Path, split_path: Path, role: str) -> tuple[pd.DataFrame, dict]:
    """Load + verify + filter normalized events to one split role (fail-closed).

    Mirrors the v1 IO contract: verify the normalized_events hash against its
    workflow manifest and bind the split artifact by SHA-256.
    """
    import sys
    from pathlib import Path as _P

    root = _P(__file__).resolve().parents[3]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from benchmark_common.io import _sha256_file, _verify_normalized_events

    events_path = Path(events_path)
    split_path = Path(split_path)
    events_hash = _verify_normalized_events(events_path)
    split_hash = _sha256_file(split_path)
    from evaluation_pipeline.governance.legacy import assert_split_not_legacy

    assert_split_not_legacy(split_path)
    split_df = pd.read_parquet(split_path)
    if "role" not in split_df.columns or "subject_id" not in split_df.columns:
        raise ValueError("split artifact must have subject_id + role columns")
    subjects = set(split_df[split_df["role"] == role]["subject_id"].astype(str))
    if not subjects:
        raise ValueError(f"split role '{role}' is empty")
    import pyarrow.parquet as pq

    cols = ["event_id", "subject_id", "hadm_id", "event_kind", "entity_type",
            "source_label", "preferred_name", "source_concept_id", "concept_id",
            "assertion"]
    events = pq.read_table(events_path, columns=cols).to_pandas()
    events = events[events["subject_id"].astype(str).isin(subjects)]
    if events.empty:
        raise ValueError("no events for the selected split role")
    meta = {"events_sha256": events_hash, "split_sha256": split_hash, "split_role": role}
    return events, meta
