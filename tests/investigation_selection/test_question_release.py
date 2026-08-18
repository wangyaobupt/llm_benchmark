from data_pipeline.investigation_selection.question_release import QuestionReleaseError, build_candidate_question, release_gold, review_record, validate_question


def rule(**extra):
    return {"rule_id": "r-new", "validation_status": "validated", "track_id": "lab", "candidate_class": "lab", "selected_candidate_id": "troponin", "rule_lineage_sha256": "rule-hash", **extra}


def decision(**extra):
    return {"decision_id": "d1", "subject_ref": "s1", "track_id": "lab", "candidate_class": "lab", "protocol_lock_sha256": "protocol-hash", "subject_split_manifest_sha256": "split-hash", "decision_evidence": [{"event_id": "e1", "feature": "cbc", "occurrence_time": "2020-01-01", "available_time": "2020-01-01", "visibility_status": "visible"}], **extra}


def options():
    return [{"candidate_id": "troponin", "label": "Troponin"}, {"candidate_id": "cbc", "label": "CBC"}]


def test_answer_is_taken_from_validated_rule_and_evidence_is_whitelisted():
    question = build_candidate_question(rule=rule(), decision=decision(), stem="Which test is most likely?", options=options())
    validation = validate_question(question, allowed_rule_ids={"r-new"})
    assert validation.valid
    assert question["answer_candidate_id"] == "troponin"
    assert question["gold_status"] == "zero_unapproved"


def test_legacy_or_unvalidated_rule_and_extra_evidence_fail_closed():
    try:
        build_candidate_question(rule=rule(rule_id="legacy_134"), decision=decision(), stem="x", options=options())
    except QuestionReleaseError:
        pass
    else:
        raise AssertionError("legacy rule must be rejected")
    bad = decision(decision_evidence=[{"event_id": "e1", "patient_name": "not allowed"}])
    try:
        build_candidate_question(rule=rule(), decision=bad, stem="x", options=options())
    except QuestionReleaseError:
        pass
    else:
        raise AssertionError("non-whitelisted evidence must be rejected")


def test_reviews_require_all_checks_and_gold_stays_zero_until_signed():
    question = build_candidate_question(rule=rule(), decision=decision(), stem="x", options=options())
    checks = {"factual_correctness": True, "time_visibility": True, "comparison_reasonable": True, "behavior_normative_boundary": True, "answer_unique": True}
    program = review_record(question_id=question["question_id"], reviewer_id="auto-1", review_type="independent_program", checks=checks, signed=True)
    clinical = review_record(question_id=question["question_id"], reviewer_id="clinician-1", review_type="clinical", checks=checks, signed=True)
    released = release_gold(question, program_review=program, clinical_review=clinical, gold_type="pattern_rule_concordance")
    assert released["gold_status"] == "approved"
    assert "同类最可能选择" in released["label"]


def test_normative_gold_requires_normative_source():
    checks = {"factual_correctness": True, "time_visibility": True, "comparison_reasonable": True, "behavior_normative_boundary": True, "answer_unique": True}
    program = review_record(question_id="r-new:d1", reviewer_id="auto-1", review_type="independent_program", checks=checks, signed=True)
    clinical = review_record(question_id="r-new:d1", reviewer_id="clinician-1", review_type="clinical", checks=checks, signed=True)
    question = build_candidate_question(rule=rule(), decision=decision(), stem="x", options=options())
    try:
        release_gold(question, program_review=program, clinical_review=clinical, gold_type="clinical_best_decision")
    except QuestionReleaseError:
        pass
    else:
        raise AssertionError("normative gold needs a normative source")
