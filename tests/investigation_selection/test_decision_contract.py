from data_pipeline.investigation_selection.catalog_lock import build_catalog_lock
from data_pipeline.investigation_selection.eligibility import load_eligibility_policy
from evaluation_pipeline.governance.protocol import load_protocol_bundle, validate_protocol_bundle
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_protocol_decision_contract_is_conditional_order_choice() -> None:
    bundle = load_protocol_bundle(
        ROOT / "config/investigation-selection/protocol.yaml",
        ROOT / "schemas/investigation-selection-protocol.schema.json",
        ROOT / "config/investigation-selection/reason-code-registry.yaml",
    )
    report = validate_protocol_bundle(bundle)
    assert report["valid"] is True
    contract = bundle["protocol"]["scientific_protocol"]["decision_contract"]
    assert contract["decision_semantics"] == "conditional_order_choice"
    assert contract["lab_result_proxy"]["target_time_field"] == "storetime"
    assert contract["lab_result_proxy"]["occurrence_time_field"] == "charttime"
    assert contract["panel_policy"]["main_analysis_count"] == "once_per_panel"
    assert contract["panel_policy"]["panel_complete_time"] == "max_required_component_storetime"
    assert report["freeze_ready"] is True


def test_thousand_case_subtypes_are_all_classified() -> None:
    import json

    policy = load_eligibility_policy()
    audit = json.loads(
        (ROOT / "data/derived/investigation_timepoint/poe-subtype-audit-1000.json").read_text(
            encoding="utf-8"
        )
    )
    leftover = []
    for row in audit:
        status = policy.classify(row["order_type"], row["order_subtype"])
        if status == "review_required":
            leftover.append((row["order_type"], row["order_subtype"], row["count"]))
    assert leftover == []


def test_catalog_lock_is_deterministic() -> None:
    first = build_catalog_lock()
    second = build_catalog_lock()
    assert first == second
    assert first["lab_result_proxy_target_time_field"] == "storetime"
    assert first["decision_semantics"] == "conditional_order_choice"
    assert len(first["catalog_lock_sha256"]) == 64
