"""Integration: full pipeline (mine -> lock -> generate -> review -> gold)."""
from __future__ import annotations

from mcq.pipeline import export_gold, run_pipeline
from mcq.validators import QUESTION_VALIDATOR, RULE_VALIDATOR, validate_strict


def test_full_pipeline_exploratory_blocks_gold(events, thresholds_exploratory,
                                               fake_client, generate_prompt,
                                               review_prompt, out_dir):
    summary = run_pipeline(
        events, thresholds_exploratory, fake_client, generate_prompt, review_prompt,
        profile="exploratory", out_dir=out_dir,
    )
    c = summary["counts"]
    # At least the "chest pain -> CT Scan" rule should be accepted.
    assert c["n_rules_accepted"] >= 1
    assert c["n_locked"] >= 1
    assert c["n_candidates"] >= 1
    assert c["n_candidate_passed"] >= 1
    # Exploratory profile never exports gold (fail-closed).
    assert c["n_gold"] == 0

    # Artifacts written.
    assert (out_dir / "conditional_rules.jsonl").exists()
    assert (out_dir / "questions_candidates.jsonl").exists()
    assert (out_dir / "questions_reviewed.jsonl").exists()
    assert (out_dir / "questions_gold.jsonl").exists()

    # Every rule conforms to the strict schema.
    for rule in _read(out_dir / "conditional_rules.jsonl"):
        validate_strict(RULE_VALIDATOR, rule)

    # Every candidate conforms to the strict question schema.
    for q in _read(out_dir / "questions_reviewed.jsonl"):
        validate_strict(QUESTION_VALIDATOR, q)


def test_full_pipeline_formal_requires_two_features(events, thresholds_formal,
                                                    fake_client, generate_prompt,
                                                    review_prompt, out_dir):
    summary = run_pipeline(
        events, thresholds_formal, fake_client, generate_prompt, review_prompt,
        profile="formal", out_dir=out_dir,
    )
    # Single-symptom conditions are below min_conditions=2 in the formal profile,
    # so no rules are mined (fail-closed rather than fabricating features).
    assert summary["counts"]["n_rules_accepted"] == 0


def _read(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


import json  # noqa: E402
