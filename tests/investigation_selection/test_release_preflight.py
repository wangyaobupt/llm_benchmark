from data_pipeline.investigation_selection.release_preflight import audit_release_inputs, record_final_test_run


def valid_inputs():
    return {
        "protocol": {"status": "frozen", "protocol_lock_sha256": "p"},
        "split": {"roles": {"development": ["s1"], "validation": ["s2"], "final_test": ["s3"]}, "previous_exposure_none": 1},
        "artifacts": {"protocol": "p", "catalog": "c", "panel": "pa", "diagnosis": "d", "feature_whitelist": "f"},
    }


def test_current_w1_state_is_explicitly_blocked():
    result = audit_release_inputs(protocol={"status": "draft"}, split={"roles": {"development": ["s1"], "validation": [], "final_test": []}, "previous_exposure_none": 0}, artifacts={}, final_test_subjects=[])
    assert not result.ready
    assert "PROTOCOL_NOT_FROZEN" in result.blockers
    assert "FINAL_TEST_SUBJECTS_EMPTY" in result.blockers
    assert result.manifest["final_test_read"] is False


def test_ready_preflight_allows_exactly_one_non_tuning_run():
    inputs = valid_inputs()
    result = audit_release_inputs(**inputs, final_test_subjects=["s3"])
    assert result.ready
    run = record_final_test_run(result=result, metrics={"recall_at_10": 0.5})
    assert run["run_count"] == 1
    assert run["final_test_single_run"] is True


def test_overlap_or_prior_exposure_blocks_even_with_nonempty_roles():
    inputs = valid_inputs()
    inputs["split"]["roles"]["final_test"] = ["s1"]
    inputs["split"]["previous_exposure_none"] = 1
    result = audit_release_inputs(**inputs, final_test_subjects=["s1"])
    assert not result.ready
    assert "SPLIT_SUBJECT_OVERLAP" in result.blockers


def test_rehearsal_mode_runs_only_on_fixture_subjects_and_never_mutates_gold():
    inputs = valid_inputs()
    inputs["protocol"] = {"status": "draft"}
    inputs["split"]["roles"] = {"development": ["fixture:d1"], "validation": ["fixture:v1"], "final_test": ["fixture:t1"]}
    inputs["split"]["previous_exposure_none"] = 1
    result = audit_release_inputs(**inputs, final_test_subjects=["fixture:t1"], mode="rehearsal")
    assert result.ready
    assert result.manifest["official_final_test"] is False
    run = record_final_test_run(result=result, metrics={"recall_at_10": 0.5})
    assert run["official_final_test"] is False
    assert run["gold_mutated"] is False
