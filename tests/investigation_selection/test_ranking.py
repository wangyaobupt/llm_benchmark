from data_pipeline.investigation_selection.ranking import benjamini_hochberg, contingency, statistics, subject_bootstrap_units


def test_zero_target_documents_change_denominator_and_are_retained():
    table = contingency(["d1", "d2"], ["d1"], ["d1", "d2", "d3"])
    assert table.as_dict() == {"a": 1, "b": 1, "c": 0, "d": 1, "n_x": 2, "n_y": 1, "n_xy": 1, "n_total": 3}
    assert statistics(table)["n_total"] == 3


def test_statistics_are_recomputable_from_integer_table():
    table = contingency(["d1", "d2"], ["d2", "d3"], ["d1", "d2", "d3", "d4"])
    result = statistics(table)
    assert result["probability"] == 0.5
    assert result["lift"] == 1.0
    assert result["a"] + result["b"] + result["c"] + result["d"] == result["n_total"]


def test_subject_bootstrap_keeps_repeat_visits_in_one_unit():
    units = subject_bootstrap_units([
        {"subject_ref": "s1", "decision_id": "d2"},
        {"subject_ref": "s1", "decision_id": "d1"},
        {"subject_ref": "s2", "decision_id": "d3"},
    ])
    assert units == (("d1", "d2"), ("d3",))


def test_bh_manifest_declares_complete_family_and_is_deterministic():
    first = benjamini_hochberg({"z": 0.04, "a": 0.01, "b": 0.2}, family="track=lab|class=panel")
    second = benjamini_hochberg({"b": 0.2, "a": 0.01, "z": 0.04}, family="track=lab|class=panel")
    assert first == second
    assert first["keys"] == ["a", "z", "b"]
