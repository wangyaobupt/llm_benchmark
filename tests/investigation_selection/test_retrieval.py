from data_pipeline.investigation_selection.retrieval import RetrievalContractError, RetrievalIndex, eligible_features


def row(decision_id, subject_ref, features, *, track_id="lab", candidate_class="lab", window_id="pre"):
    return {
        "decision_id": decision_id,
        "subject_ref": subject_ref,
        "track_id": track_id,
        "candidate_class": candidate_class,
        "window_id": window_id,
        "features": features,
        "split": "development",
    }


def test_binary_tfidf_deduplicates_repeated_rows_and_excludes_same_subject():
    index = RetrievalIndex(configuration="binary_tfidf").fit([
        row("d1", "s1", ["cbc", "troponin", "troponin"]),
        row("d2", "s2", ["troponin", "echo"]),
    ])
    result = index.retrieve([row("q1", "s1", ["troponin", "echo"])], top_k=5)[0]
    assert [item["decision_id"] for item in result.neighbors] == ["d2"]
    assert index.manifest["fit_split"] == "development"
    assert index.manifest["validation_or_final_test_read"] is False


def test_all_four_configurations_return_deterministic_neighbors():
    documents = [row("d1", "s1", {"a": 2, "b": 1}), row("d2", "s2", {"a": 1, "c": 3})]
    for configuration in ("frequency", "binary_tfidf", "log_count_tfidf", "bm25"):
        index = RetrievalIndex(configuration=configuration).fit(documents)
        first = index.retrieve([row("q", "s3", {"a": 1})])[0]
        second = index.retrieve([row("q", "s3", {"a": 1})])[0]
        assert first.neighbors == second.neighbors
        assert first.neighbors[0]["decision_id"] == "d1"


def test_oov_and_empty_query_have_explicit_audit_and_refusal():
    index = RetrievalIndex().fit([row("d1", "s1", ["a"])])
    oov = index.retrieve([row("q", "s2", ["missing"])])[0]
    assert oov.audit["oov_count"] == 1
    assert "NO_ELIGIBLE_NEIGHBORS" in oov.refusal_reasons
    empty = index.retrieve([row("q2", "s2", {"patient_id": 1, "x": {"evidence_phase": "post_hoc"}})])[0]
    assert "IDENTITY_FEATURE_EXCLUDED" in empty.refusal_reasons
    assert "POST_HOC_FEATURE_EXCLUDED" in empty.refusal_reasons
    assert "NO_ELIGIBLE_FEATURES" in empty.refusal_reasons


def test_fit_rejects_non_development_documents_and_duplicate_ids():
    try:
        RetrievalIndex().fit([row("d1", "s1", ["a"],)])
        RetrievalIndex().fit([dict(row("d1", "s1", ["a"])), dict(row("d1", "s2", ["b"]))])
    except RetrievalContractError:
        pass
    else:
        raise AssertionError("duplicate development IDs must be rejected")

    validation = row("v1", "s2", ["a"])
    validation["split"] = "validation"
    try:
        RetrievalIndex().fit([validation])
    except RetrievalContractError:
        pass
    else:
        raise AssertionError("validation documents must not fit the index")


def test_feature_filtering_keeps_counts_only_for_eligible_features():
    features, rejected = eligible_features({
        "features": {
            "ok": 2,
            "patient_id": 1,
            "late": {"evidence_phase": "post_hoc"},
            "unfrozen": {"ner_frozen": False},
        }
    })
    assert features == {"ok": 2.0}
    assert rejected == {"IDENTITY_FEATURE_EXCLUDED": 1, "POST_HOC_FEATURE_EXCLUDED": 1, "UNFROZEN_NER_EXCLUDED": 1}
