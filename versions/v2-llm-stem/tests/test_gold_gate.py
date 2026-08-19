"""Unit tests for the fail-closed gold gate."""
from __future__ import annotations

from mcq.pipeline import export_gold


def _q(automatic="candidate_passed", human="approved",
       schema_version="1.0.0", prompt_version="1.0.0"):
    return {
        "question_id": f"iq_{schema_version}_{automatic}_{human}".replace(".", "_")[:40],
        "schema_version": schema_version,
        "prompt_version": prompt_version,
        "automatic_review_status": automatic,
        "human_review_status": human,
        "stem": "x", "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
    }


def test_gold_requires_every_gate():
    reviewed = [
        _q(),                                          # 0: should pass
        _q(human="pending"),                           # 1: no human approval
        _q(human="rejected"),                          # 2: human rejected
        _q(automatic="candidate_rejected"),            # 3: auto rejected
        _q(automatic="pending"),                       # 4: auto pending
    ]
    gold = export_gold(reviewed, profile="formal")
    assert gold == [reviewed[0]]


def test_exploratory_never_exports_gold():
    reviewed = [_q()]
    assert export_gold(reviewed, profile="exploratory") == []


def test_release_policy_blocks_disallowed_versions():
    reviewed = [_q(schema_version="0.9.0")]
    gold = export_gold(
        reviewed, profile="formal",
        release_policy={"allowed_schema_versions": ["1.0.0"],
                        "allowed_prompt_versions": ["1.0.0"]},
    )
    assert gold == []


def test_human_review_status_apply():
    from mcq.pipeline import apply_human_decisions

    reviewed = [dict(_q(), question_id="iq_x"), dict(_q(), question_id="iq_y")]
    out = apply_human_decisions(reviewed, {"iq_x": "approved", "iq_y": "revise"})
    assert out[0]["human_review_status"] == "approved"
    # "revise" is not an approval -> rejected (not gold-eligible).
    assert out[1]["human_review_status"] == "rejected"
