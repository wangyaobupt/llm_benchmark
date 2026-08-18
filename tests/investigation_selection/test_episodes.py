from data_pipeline.investigation_selection.episodes import build_investigation_episodes


def test_poe_burst_deduplicates_but_keeps_generic_lab_as_category() -> None:
    result = build_investigation_episodes([
        {"event_id": "o1", "event_kind": "laboratory_ordered", "order_type": "Lab", "preferred_name": "Lab", "source_group_id": "poe:1", "event_time": "2100-01-01 08:00:00", "available_time": "2100-01-01 08:00:00"},
        {"event_id": "o2", "event_kind": "laboratory_ordered", "order_type": "Lab", "preferred_name": "Lab", "source_group_id": "poe:1", "event_time": "2100-01-01 08:10:00", "available_time": "2100-01-01 08:10:00"},
    ])
    assert result.episodes == []
    assert any("ORDER_CONTENT_CATEGORY_ONLY" in row["reason_codes"] for row in result.exclusions)


def test_lab_result_bundle_partial_panel_is_not_complete() -> None:
    result = build_investigation_episodes([
        {"event_id": "r1", "event_kind": "laboratory_resulted", "source_table": "hosp.labevents", "preferred_name": "RBC", "candidate_id": "lab:rbc", "candidate_level": "component", "source_group_id": "lab-specimen:1", "event_time": "2100-01-01 08:00:00", "available_time": "2100-01-01 08:05:00", "required_components": ["RBC", "HGB"], "observed_components": ["RBC"], "panel_definition_status": "frozen"},
    ])
    assert result.episodes == []
    assert "PANEL_INCOMPLETE" in result.exclusions[-1]["reason_codes"]


def test_order_and_result_tracks_never_link_by_time() -> None:
    result = build_investigation_episodes([
        {"event_id": "o1", "track_id": "generic_lab_order", "candidate_level": "category", "candidate_id": "generic_lab", "preferred_name": "Lab", "source_group_id": "poe:1", "event_time": "2100-01-01 08:00:00", "available_time": "2100-01-01 08:00:00"},
        {"event_id": "r1", "track_id": "lab_result_proxy", "candidate_id": "lab:glucose", "preferred_name": "Glucose", "source_group_id": "specimen:1", "event_time": "2100-01-01 08:05:00", "available_time": "2100-01-01 08:15:00", "panel_definition_status": "frozen"},
    ])
    assert {row["track_id"] for row in result.episodes} == {"lab_result_proxy"}
    assert all("poe:1" not in row["source_group_id"] for row in result.episodes)

