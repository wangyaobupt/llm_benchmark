"""Generate candidate questions from mined accepted rules (Stage 5-8).

Takes the accepted rules from the full mining output, locks A-D options, calls
the LLM to write ``stem``+``rationale``, applies the 12 program checks, runs the
independent auto review, and exports gold (empty under the exploratory profile,
fail-closed). FakeClient by default; pass ``--execute`` for real DeepSeek Flash.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "versions" / "v2-llm-stem"))

from data_pipeline.archived.phenotype.progress import write_progress  # noqa: E402
from data_pipeline.archived.phenotype.run_phenotype import load_events  # noqa: E402
from mcq.audit import write_json, write_jsonl  # noqa: E402
from mcq.catalog import build_catalog  # noqa: E402
from mcq.client import (  # noqa: E402
    FakeStructuredClient,
    OpenAIStructuredClient,
    OpenAICompatibleSettings,
    load_api_config,
)
from mcq.config_loader import CONFIG_DIR, load_prompt  # noqa: E402
from mcq.distractors import lock_options  # noqa: E402
from mcq.generation import generate_questions  # noqa: E402
from mcq.pipeline import (  # noqa: E402
    apply_human_decisions,
    export_gold,
    export_human_queue,
)
from mcq.review import review_questions  # noqa: E402
from evaluation_pipeline.governance.legacy import assert_legacy_phenotype_formal_forbidden  # noqa: E402

RULES = Path(r"D:\Projects\llm_benchmark\data\phenotype\conditional_rules_development.jsonl")
EVENTS = Path(
    r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full"
    r"\event_pipeline\normalization\normalized_events.parquet"
)
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")
OUT_DIR = Path(r"D:\Projects\llm_benchmark\data\phenotype\generation")


def load_rules(path: Path, n: int) -> list[dict]:
    rules = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    rules.sort(key=lambda r: -(r.get("score") or 0.0))
    return rules[:n]


def load_human_decisions(path: Path | None) -> dict[str, str]:
    if path is None or not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data.items()}


def build_client(execute: bool):
    if not execute:
        return FakeStructuredClient(model_name="fake-mcq-model"), "fake-mcq-model"
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    settings = OpenAICompatibleSettings(
        api_key=env["TEXT_NER_API_KEY"], base_url=env["TEXT_NER_BASE_URL"],
        model=env["TEXT_NER_MODEL"], model_version=env["TEXT_NER_MODEL_VERSION"],
        provider=env["TEXT_NER_PROVIDER"],
    )
    api_config = load_api_config(CONFIG_DIR / "api.json")
    client = OpenAIStructuredClient(settings, api_config, execute=True,
                                    data_transfer_authorized=True)
    return client, settings.model


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rules", type=Path, default=RULES)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--profile", default="exploratory", choices=["formal", "exploratory"])
    ap.add_argument("--human-decisions", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)
    assert_legacy_phenotype_formal_forbidden(args.profile)

    t0 = time.time()
    events, _ = load_events(EVENTS, SPLIT, "development")
    catalog = build_catalog(events)
    rules = load_rules(args.rules, args.n)
    locked, lock_failures = lock_options(rules, catalog)

    client, model = build_client(args.execute)
    generate_prompt = load_prompt("generate_stem.md")
    review_prompt = load_prompt("review_question.md")

    write_progress("generation", {
        "status": "running", "n_rules": len(rules), "n_locked": len(locked),
        "n_candidates": 0, "n_passed": 0, "elapsed_s": 0,
    })

    candidates, gen_failures = generate_questions(
        locked, client, generate_prompt, {}, generator_model=model)
    reviewed, records = review_questions(candidates, client, review_prompt,
                                         reviewer_model=model)
    # Human review queue: only candidate_passed questions (UTF-8-SIG CSV).
    export_human_queue(reviewed, records, args.out_dir)
    # Apply human decisions (question_id -> approved/rejected/revise), then the
    # fail-closed gold gate with the selected profile.
    human_decisions = load_human_decisions(args.human_decisions)
    reviewed = apply_human_decisions(reviewed, human_decisions)
    gold = export_gold(reviewed, profile=args.profile)

    summary = {
        "model": model,
        "profile": args.profile,
        "n_rules": len(rules),
        "n_locked": len(locked),
        "n_insufficient_distractors": len(lock_failures),
        "n_candidates": len(candidates),
        "n_generation_failures": len(gen_failures),
        "n_candidate_passed": sum(1 for q in reviewed if q["automatic_review_status"] == "candidate_passed"),
        "n_human_approved": sum(1 for q in reviewed if q["human_review_status"] == "approved"),
        "n_gold": len(gold),
        "elapsed_s": round(time.time() - t0, 1),
    }

    out = args.out_dir
    write_jsonl(out / "questions_candidates.jsonl", candidates)
    write_jsonl(out / "questions_reviewed.jsonl", reviewed)
    write_jsonl(out / "review_records.jsonl", records)
    write_jsonl(out / "generation_failures.jsonl", gen_failures)
    write_jsonl(out / "questions_gold.jsonl", gold)
    write_json(out / "summary.json", summary)

    write_progress("generation", {
        "status": "done", "n_rules": len(rules), "n_locked": len(locked),
        "n_candidates": len(candidates),
        "n_passed": summary["n_candidate_passed"],
        "elapsed_s": summary["elapsed_s"],
    })
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
