"""Unit tests for the 8-gate rule mining."""
from __future__ import annotations

from mcq.catalog import build_catalog
from mcq.conditions import extract_condition_frame
from mcq.mining import mine_rules


def _mine(events, thresholds):
    catalog = build_catalog(events)
    cond = extract_condition_frame(events)
    return mine_rules(events, cond, catalog, thresholds)


def test_abdominal_pain_rule_accepted(events, thresholds_exploratory):
    # Under lift (selectivity) ranking, "abdominal pain" has a clear
    # discriminative answer (Ultrasound lift >> CT Scan lift), unlike "chest
    # pain" whose two candidates (General Xray / CT Scan) are close in lift.
    accepted, rejected = _mine(events, thresholds_exploratory)
    by_cond = {", ".join(r["condition_display_names"]): r for r in accepted}
    assert "abdominal pain" in by_cond
    rule = by_cond["abdominal pain"]
    assert rule["status"] == "accepted"
    assert rule["target_investigation_name"] == "Ultrasound"
    assert rule["rejection_reasons"] == []
    # Basic consistency: n_xy <= n_x, probabilities in [0, 1].
    assert rule["n_xy"] <= rule["n_x"]
    assert 0 <= rule["smoothed_probability"] <= 1
    assert rule["lift"] >= 1.0
    assert rule["probability_gap"] is not None and rule["probability_gap"] > 0


def test_strict_gap_rejects_rule(events):
    thresholds = dict(load_exploratory())
    thresholds["min_lift_gap"] = 10.0  # impossible lift gap
    accepted, rejected = _mine(events, thresholds)
    assert not accepted
    assert any("ambiguous_probability_gap" in r["rejection_reasons"] for r in rejected)


def test_low_support_rejected(events):
    thresholds = dict(load_exploratory())
    thresholds["min_x_support"] = 1000
    accepted, rejected = _mine(events, thresholds)
    assert not accepted
    assert any("low_x_support" in r["rejection_reasons"] for r in rejected)


def test_rejected_rules_carry_stable_reasons(events, thresholds_exploratory):
    thresholds = dict(thresholds_exploratory)
    thresholds["min_bootstrap_stability"] = 1.0  # nearly impossible
    _, rejected = _mine(events, thresholds)
    assert all(r["status"] == "rejected" for r in rejected)
    assert all(r["rejection_reasons"] for r in rejected)


def load_exploratory():
    from mcq.config_loader import load_thresholds
    return load_thresholds("exploratory")
