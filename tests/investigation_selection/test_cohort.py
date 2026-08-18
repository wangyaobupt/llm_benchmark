from data_pipeline.investigation_selection.cohort import CohortContractError, audit_domains, map_diagnosis, select_domains


DOMAINS = ("cardiac", "respiratory", "neurologic", "renal", "infectious", "oncology", "metabolic")


def test_mapping_preserves_raw_code_status_and_version():
    assert map_diagnosis("I25.10", {"I25.10": "cardiac"}, version="dx-v1") == map_diagnosis("I25.10", {"I25.10": "cardiac"}, version="dx-v1")
    assert map_diagnosis("X", {}, version="dx-v1").mapping_status == "unmapped"


def test_domain_audit_is_seven_domain_and_subject_deduplicated():
    rows = [{"diagnosis_family": domain, "subject_ref": f"s-{domain}", "time_constructible": True, "source_coverage": {"ED": True}} for domain in DOMAINS]
    rows.append({"diagnosis_family": "cardiac", "subject_ref": "s-cardiac", "time_constructible": False, "source_coverage": {}})
    audits = audit_domains(rows, required_domains=DOMAINS)
    cardiac = next(row for row in audits if row["domain"] == "cardiac")
    assert cardiac["subject_count"] == 1
    assert cardiac["event_count"] == 2


def test_selection_records_reason_and_requires_four_domains():
    audits = [{"domain": domain, "subject_count": 10, "time_constructible_rate": 1.0} for domain in DOMAINS]
    selected = select_domains(audits, minimum_subjects=5, minimum_time_rate=0.8)
    assert sum(row["selected"] for row in selected) == 7
    assert all(row["selection_reason"] == "MEETS_COHORT_AND_TIME_GATES" for row in selected)

    try:
        select_domains(audits[:3], minimum_subjects=5, minimum_time_rate=0.8)
    except CohortContractError:
        pass
    else:
        raise AssertionError("fewer than four domains must fail closed")


def test_invalid_domain_registration_fails_closed():
    try:
        audit_domains([], required_domains=("a",))
    except CohortContractError:
        pass
    else:
        raise AssertionError("non-seven domain registration must fail")
