"""Unit tests for distractor selection and A-D option locking."""
from __future__ import annotations

from mcq.catalog import build_catalog
from mcq.conditions import extract_condition_frame
from mcq.distractors import lock_options, select_distractors
from mcq.mining import mine_rules


def _accepted(events, thresholds):
    catalog = build_catalog(events)
    cond = extract_condition_frame(events)
    return mine_rules(events, cond, catalog, thresholds)[0]


def test_lock_is_deterministic(events, thresholds_exploratory):
    catalog = build_catalog(events)
    accepted = _accepted(events, thresholds_exploratory)
    locked1, _ = lock_options(accepted, catalog)
    locked2, _ = lock_options(accepted, catalog)
    assert locked1 == locked2


def test_options_have_four_unique_and_correct_answer(events, thresholds_exploratory):
    catalog = build_catalog(events)
    accepted = _accepted(events, thresholds_exploratory)
    locked, failures = lock_options(accepted, catalog)
    assert not failures
    assert locked
    for item in locked:
        opts = item["options"]
        assert set(opts.keys()) == {"A", "B", "C", "D"}
        assert len(set(opts.values())) == 4
        assert opts[item["correct_option"]] == item["correct_answer"]
        # distractors never equal the answer
        assert item["correct_answer"] not in [
            opts[l] for l in "ABCD" if l != item["correct_option"]
        ]


def test_three_distractors_selected(events, thresholds_exploratory):
    catalog = build_catalog(events)
    distractors = select_distractors("imaging", "CT Scan", catalog)
    assert len(distractors) == 3
    assert "CT Scan" not in distractors


def test_distractors_exclude_finer_granularity(events):
    """C2: body-part / interventional imaging names ("procedure" tier) must not
    be distractors for modality-level ("specific") answers like "CT Scan"."""
    from mcq.catalog import Catalog, InvestigationConcept, image_granularity

    catalog = build_catalog(events)
    # The synthetic pool contains "MRI Brain" and "CT Angiogram" (procedure
    # tier); they must be excluded, leaving only modality-tier candidates.
    imaging = catalog.pool["imaging"]
    proc = [c.canonical_name for c in imaging if image_granularity(c.canonical_name) == "procedure"]
    assert proc, "fixture should contain at least one procedure-tier imaging name"

    distractors = select_distractors("imaging", "CT Scan", catalog)
    assert len(distractors) == 3
    assert not set(distractors) & set(proc)
    # All returned distractors are modality-tier ("specific").
    for d in distractors:
        assert image_granularity(d) == "specific"


def test_insufficient_distractors(events, thresholds_exploratory):
    from mcq.catalog import Catalog, InvestigationConcept

    catalog = build_catalog(events)
    accepted = _accepted(events, thresholds_exploratory)
    # Build a catalog whose imaging pool has only 2 items -> cannot make 3
    # distractors for the "CT Scan" target.
    tiny = Catalog(
        answers=catalog.answers,
        pool={
            "imaging": [
                InvestigationConcept("cand_a", "CT Scan", "imaging", "ct", "specific", True, 30),
                InvestigationConcept("cand_b", "General Xray", "imaging", "xray", "specific", True, 5),
            ],
            "clinical_order": catalog.pool["clinical_order"],
            "laboratory": catalog.pool["laboratory"],
        },
    )
    locked, failures = lock_options(accepted, tiny)
    assert failures
    assert all(f["error_type"] == "insufficient_distractors" for f in failures)
    assert len(locked) == 0
