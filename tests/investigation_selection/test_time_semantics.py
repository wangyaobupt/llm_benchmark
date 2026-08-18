from data_pipeline.investigation_selection.source_grouping import attach_source_groups


def test_lab_specimen_group_is_stable_and_received_time_is_not_invented() -> None:
    events = [
        {
            "source_table": "hosp.labevents",
            "source_row_id": "l1",
            "specimen_id": "s77",
            "charttime": "2100-01-01 08:35:00",
            "storetime": "2100-01-01 09:25:00",
            "specimen_received_time": "2100-01-01 08:40:00",
        },
        {"source_table": "hosp.labevents", "source_row_id": "l2", "specimen_id": "s77"},
    ]
    first = attach_source_groups(events)
    second = attach_source_groups(events)
    assert first.rows[0]["source_group_id"] == first.rows[1]["source_group_id"]
    assert first.rows[0]["source_group_id"] == second.rows[0]["source_group_id"]
    assert all("specimen_received_time" not in row for row in first.rows)


def test_missing_specimen_group_is_explicitly_excluded() -> None:
    result = attach_source_groups([{"source_table": "hosp.labevents", "source_row_id": "l1"}])
    assert result.rows == []
    assert result.exclusions[0]["reason_codes"] == ["SPECIMEN_GROUP_MISSING"]

