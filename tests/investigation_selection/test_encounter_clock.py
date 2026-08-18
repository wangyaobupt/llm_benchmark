from data_pipeline.investigation_selection.encounter_clock import build_encounter_clock


def test_ed_arrival_and_registration_are_separate() -> None:
    result = build_encounter_clock(
        [{"hadm_id": "h1", "admittime": "2100-01-01 09:00:00", "edregtime": "2100-01-01 08:55:00", "dischtime": "2100-01-02 09:00:00"}],
        [{"hadm_id": "h1", "stay_id": "e1", "intime": "2100-01-01 08:50:00", "outtime": "2100-01-01 09:30:00"}],
    )
    row = result.rows[0]
    assert row["origin_type"] == "ed_arrival"
    assert row["origin_time"] == "2100-01-01 08:50:00"
    assert row["ed_registration_time"] == "2100-01-01 08:55:00"
    assert row["hospital_admit_time"] == "2100-01-01 09:00:00"


def test_multiple_ed_stays_are_excluded_not_coalesced() -> None:
    result = build_encounter_clock(
        [{"hadm_id": "h1", "admittime": "2100-01-01 09:00:00"}],
        [
            {"hadm_id": "h1", "intime": "2100-01-01 08:00:00", "outtime": "2100-01-01 08:30:00"},
            {"hadm_id": "h1", "intime": "2100-01-01 08:40:00", "outtime": "2100-01-01 09:00:00"},
        ],
    )
    assert result.rows == []
    assert result.exclusions[0]["reason_codes"] == ["ENCOUNTER_ORIGIN_AMBIGUOUS"]


def test_reversed_interval_is_excluded() -> None:
    result = build_encounter_clock(
        [{"hadm_id": "h1", "admittime": "2100-01-02 09:00:00", "dischtime": "2100-01-01 09:00:00"}],
        [],
    )
    assert result.exclusions[0]["reason_codes"] == ["ENCOUNTER_TIME_INVERTED"]

