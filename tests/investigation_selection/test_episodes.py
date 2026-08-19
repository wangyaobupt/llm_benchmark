from data_pipeline.investigation_selection.episodes import build_investigation_episodes


def test_poe_burst_deduplicates_but_keeps_generic_lab_as_category() -> None:
    result = build_investigation_episodes([
        {"event_id": "o1", "event_kind": "laboratory_ordered", "order_type": "Lab", "preferred_name": "Lab", "source_group_id": "poe:1", "event_time": "2100-01-01 08:00:00", "available_time": "2100-01-01 08:00:00", "lifecycle_action": "create"},
        {"event_id": "o2", "event_kind": "laboratory_ordered", "order_type": "Lab", "preferred_name": "Lab", "source_group_id": "poe:1", "event_time": "2100-01-01 08:10:00", "available_time": "2100-01-01 08:10:00", "lifecycle_action": "create"},
    ])
    assert len(result.episodes) == 1
    assert result.episodes[0]["track_id"] == "generic_lab_order"
    assert result.episodes[0]["candidate_specificity"] == "category"
    assert "ORDER_CONTENT_CATEGORY_ONLY" in result.episodes[0]["reason_codes"]


def test_lab_result_bundle_partial_panel_is_not_complete() -> None:
    result = build_investigation_episodes([
        {"event_id": "r1", "event_kind": "laboratory_resulted", "source_table": "hosp.labevents", "preferred_name": "RBC", "candidate_id": "lab:rbc", "candidate_level": "component", "source_group_id": "lab-specimen:1", "event_time": "2100-01-01 08:00:00", "available_time": "2100-01-01 08:05:00", "required_components": ["RBC", "HGB"], "observed_components": ["RBC"], "panel_definition_status": "frozen"},
    ])
    assert len(result.episodes) == 1
    assert result.episodes[0]["panel_completeness"] == "partial"
    assert "PANEL_INCOMPLETE" in result.episodes[0]["reason_codes"]


def test_lab_result_components_on_one_specimen_are_separate_episodes() -> None:
    result = build_investigation_episodes([
        {"event_id": "r1", "event_kind": "laboratory_resulted", "source_table": "hosp.labevents", "preferred_name": "Potassium", "candidate_id": "lab:k", "source_group_id": "lab-specimen:1", "event_time": "2100-01-01 08:00:00", "available_time": "2100-01-01 08:30:00"},
        {"event_id": "r2", "event_kind": "laboratory_resulted", "source_table": "hosp.labevents", "preferred_name": "Troponin T", "candidate_id": "lab:tnt", "source_group_id": "lab-specimen:1", "event_time": "2100-01-01 08:00:00", "available_time": "2100-01-01 08:40:00"},
    ])
    names = {row["candidate_name"] for row in result.episodes}
    assert names == {"Potassium", "Troponin T"}
    assert all(row["source_group_id"] == "lab-specimen:1" for row in result.episodes)


def test_order_and_result_tracks_never_link_by_time() -> None:
    result = build_investigation_episodes([
        {"event_id": "o1", "track_id": "generic_lab_order", "candidate_level": "category", "candidate_id": "generic_lab", "preferred_name": "Lab", "source_group_id": "poe:1", "event_time": "2100-01-01 08:00:00", "available_time": "2100-01-01 08:00:00"},
        {"event_id": "r1", "track_id": "lab_result_proxy", "candidate_id": "lab:glucose", "preferred_name": "Glucose", "source_group_id": "specimen:1", "event_time": "2100-01-01 08:05:00", "available_time": "2100-01-01 08:15:00", "panel_definition_status": "frozen"},
    ])
    tracks = {row["track_id"] for row in result.episodes}
    assert tracks == {"generic_lab_order", "lab_result_proxy"}
    assert all(row["source_group_id"] != "poe:1" or row["track_id"] == "generic_lab_order" for row in result.episodes)
    assert all(row["source_group_id"] != "specimen:1" or row["track_id"] == "lab_result_proxy" for row in result.episodes)

