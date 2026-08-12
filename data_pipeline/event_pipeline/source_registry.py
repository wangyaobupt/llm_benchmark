"""Closed-world source catalog, fact ownership, and transformer routing."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

from .models import IdentityStrategy, SourceOrigin, SourceSpec, TimePolicy


SOURCE_CATALOG_VERSION = "1.0.0"

TIME_POLICIES: dict[str, TimePolicy] = {
    policy.policy_id: policy
    for policy in (
        TimePolicy(
            "triage_no_time_v1",
            "null",
            "null",
            "null",
            "keep_null_and_flag_time_unavailable",
            "ED triage has no source timestamp.",
        ),
        TimePolicy(
            "chart_only_v1",
            "charttime",
            "null",
            "null",
            "keep_available_and_recorded_null",
            "The source exposes occurrence time but no reliable availability time.",
        ),
        TimePolicy(
            "chart_store_v1",
            "charttime_or_chartdate",
            "storetime",
            "storetime_or_storedate",
            "keep_missing_store_time_null_and_flag",
            "Result occurrence and database availability remain distinct.",
        ),
        TimePolicy(
            "poe_timeline_v1",
            "event_time",
            "event_time",
            "null",
            "reject_missing_order_time_when_semantics_require_it",
            "The derived POE timeline preserves and cross-checks raw ordertime.",
        ),
        TimePolicy(
            "prescription_poe_link_v1",
            "supporting_poe_timeline.event_time",
            "supporting_poe_timeline.event_time",
            "null",
            "keep_unresolved_time_null",
            "Prescription starttime must not be substituted for ordertime.",
        ),
        TimePolicy(
            "pharmacy_workflow_v1",
            "entertime",
            "entertime",
            "verifiedtime",
            "keep_missing_entry_time_null_and_flag",
            "Pharmacy rows describe workflow entry and verification.",
        ),
        TimePolicy(
            "emar_chart_store_v1",
            "charttime",
            "storetime",
            "storetime",
            "keep_missing_source_time_null_and_flag",
            "eMAR charting and storage times remain unmodified.",
        ),
        TimePolicy(
            "service_transfer_v1",
            "transfertime",
            "transfertime",
            "null",
            "reject_missing_event_time",
            "Service transfer time is immediately available as a structured fact.",
        ),
        TimePolicy(
            "transfer_intime_v1",
            "intime",
            "null",
            "null",
            "keep_availability_null_and_flag",
            "Transfer occurrence is known but source availability is not.",
        ),
        TimePolicy(
            "post_hoc_no_time_v1",
            "null",
            "null",
            "null",
            "keep_null_and_mark_post_hoc",
            "Coded diagnoses are retrospective and have no reliable event time.",
        ),
        TimePolicy(
            "post_hoc_chartdate_v1",
            "chartdate",
            "null",
            "null",
            "keep_availability_null_and_mark_post_hoc",
            "Coded procedures retain their chart date but remain retrospective.",
        ),
        TimePolicy(
            "icu_interval_completion_v1",
            "starttime",
            "max(endtime,storetime)",
            "storetime",
            "route_unexplained_inversion_to_review",
            "Completed interval facts must not be exposed before completion.",
        ),
        TimePolicy(
            "icu_output_chart_store_v1",
            "charttime",
            "storetime",
            "storetime",
            "route_unexplained_inversion_to_review",
            "Output occurrence and chart storage remain separate.",
        ),
        TimePolicy(
            "radiology_chart_store_v1",
            "charttime",
            "storetime",
            "storetime",
            "reject_unexplained_availability_inversion",
            "Imaging reports become available at storage time.",
        ),
        TimePolicy(
            "discharge_post_hoc_v1",
            "charttime",
            "storetime",
            "storetime",
            "mark_post_hoc_and_explain_inversion",
            "Discharge documents are retrospective regardless of storage time.",
        ),
        TimePolicy(
            "support_poe_v1",
            "ordertime",
            "ordertime",
            "null",
            "support_only_no_event_emission",
            "Raw POE rows cross-check the derived POE timeline.",
        ),
        TimePolicy(
            "support_parent_inherit_v1",
            "inherit_fact_owner",
            "inherit_fact_owner",
            "inherit_fact_owner",
            "support_only_no_event_emission",
            "Detail rows enrich their parent fact and do not emit events.",
        ),
        TimePolicy(
            "support_icu_interval_v1",
            "starttime",
            "max(endtime,storetime)",
            "storetime",
            "support_only_no_event_emission",
            "Ingredient rows support their owning ICU input interval.",
        ),
        TimePolicy(
            "context_only_v1",
            "not_applicable",
            "not_applicable",
            "not_applicable",
            "context_only_no_event_emission",
            "Context tables define encounter or administrative background only.",
        ),
    )
}


def _identity(keys: str) -> tuple[IdentityStrategy, tuple[str, ...]]:
    fields = tuple(keys.split())
    if not fields:
        return "canonical_row_hash_with_occurrence", ()
    return ("native_key" if len(fields) == 1 else "composite_key"), fields


def _source_table(module: str, table: str) -> str:
    prefix = {
        "mimic_iv_hosp": "hosp",
        "mimic_iv_icu": "icu",
        "mimic_iv_ed": "ed",
        "mimic_iv_note": "note",
    }[module]
    return f"{prefix}.{table}"


def _event(
    module: str,
    table: str,
    keys: str,
    transformer: str,
    time_policy: str,
    evidence_phase: str,
    reason: str,
    *,
    origin: SourceOrigin = "raw",
    supports: tuple[str, ...] = (),
) -> SourceSpec:
    strategy, fields = _identity(keys)
    path = _source_table(module, table)
    return SourceSpec(
        module=module,
        table=table,
        origin=origin,
        role="event",
        fact_owner=path,
        supports=supports,
        identity_strategy=strategy,
        native_key_fields=fields,
        time_policy=time_policy,
        evidence_phase=evidence_phase,
        transformer_name=transformer,
        inclusion_reason=reason,
        exclusion_reason=None,
    )


def _support(
    module: str,
    table: str,
    keys: str,
    fact_owner: str,
    time_policy: str,
    reason: str,
) -> SourceSpec:
    strategy, fields = _identity(keys)
    return SourceSpec(
        module=module,
        table=table,
        origin="raw",
        role="support",
        fact_owner=fact_owner,
        supports=(fact_owner,),
        identity_strategy=strategy,
        native_key_fields=fields,
        time_policy=time_policy,
        evidence_phase=None,
        transformer_name=None,
        inclusion_reason=reason,
        exclusion_reason=None,
    )


def _context(module: str, table: str, keys: str, reason: str) -> SourceSpec:
    strategy, fields = _identity(keys)
    return SourceSpec(
        module=module,
        table=table,
        origin="raw",
        role="context",
        fact_owner=None,
        supports=(),
        identity_strategy=strategy,
        native_key_fields=fields,
        time_policy="context_only_v1",
        evidence_phase=None,
        transformer_name=None,
        inclusion_reason=reason,
        exclusion_reason=None,
    )


SOURCE_CATALOG: tuple[SourceSpec, ...] = (
    # Existing event sources retain their order and identity fields so their IDs
    # remain stable when later cleaning stages intentionally add new facts.
    _event("mimic_iv_ed", "triage", "subject_id stay_id", "transform_ed_triage", "triage_no_time_v1", "source_event", "ED triage owns chief complaint, acuity, and triage vital facts."),
    _event("mimic_iv_ed", "vitalsign", "subject_id stay_id charttime", "transform_ed_vitals", "chart_only_v1", "source_event", "ED vitalsign owns timestamped ED vital measurements."),
    _event("mimic_iv_hosp", "labevents", "labevent_id", "transform_labevent", "chart_store_v1", "source_event", "Laboratory rows own resulted laboratory facts."),
    _event("mimic_iv_hosp", "microbiologyevents", "microevent_id", "transform_microbiology", "chart_store_v1", "source_event", "Microbiology rows own resulted microbiology facts."),
    _event("mimic_iv_hosp", "poe_timeline", "subject_id poe_id poe_seq", "transform_poe_timeline", "poe_timeline_v1", "source_event", "Validated POE timeline rows own clinical order lifecycle facts.", origin="derived", supports=("hosp.prescriptions",)),
    _event("mimic_iv_hosp", "prescriptions", "", "transform_prescription", "prescription_poe_link_v1", "source_event", "Prescription rows own medication order facts.", supports=("hosp.emar", "hosp.pharmacy")),
    _event("mimic_iv_hosp", "pharmacy", "pharmacy_id", "transform_pharmacy", "pharmacy_workflow_v1", "source_event", "Pharmacy rows own pharmacy workflow status facts.", supports=("hosp.emar",)),
    _event("mimic_iv_hosp", "emar", "subject_id emar_id emar_seq", "transform_emar", "emar_chart_store_v1", "source_event", "eMAR rows own medication administration documentation facts."),
    _event("mimic_iv_hosp", "services", "subject_id hadm_id transfertime curr_service", "transform_service", "service_transfer_v1", "source_event", "Service rows own clinical service changes."),
    _event("mimic_iv_hosp", "transfers", "transfer_id", "transform_transfer", "transfer_intime_v1", "source_event", "Transfer rows own patient location transition facts."),
    _event("mimic_iv_hosp", "procedures_icd", "subject_id hadm_id seq_num", "transform_procedure_icd", "post_hoc_chartdate_v1", "post_hoc", "ICD procedure rows own retrospective coded procedure facts."),
    _event("mimic_iv_icu", "procedureevents", "subject_id stay_id orderid itemid starttime", "transform_icu_procedure", "icu_interval_completion_v1", "source_event", "ICU procedure rows own performed procedure intervals."),
    _event("mimic_iv_note", "radiology", "subject_id note_id", "transform_radiology_note", "radiology_chart_store_v1", "source_event", "Radiology notes own imaging report document facts."),
    _event("mimic_iv_note", "discharge", "subject_id note_id", "transform_discharge_note", "discharge_post_hoc_v1", "post_hoc", "Discharge notes own retrospective discharge document facts."),
    # Newly declared fact owners. Existing transformers are activated by the
    # registry, but this contract stage does not rebuild published Parquet.
    _event("mimic_iv_hosp", "diagnoses_icd", "subject_id hadm_id seq_num", "transform_diagnosis", "post_hoc_no_time_v1", "post_hoc", "Hospital diagnosis rows own retrospective coded condition facts."),
    _event("mimic_iv_ed", "diagnosis", "subject_id stay_id seq_num", "transform_ed_diagnosis", "post_hoc_no_time_v1", "post_hoc", "ED diagnosis rows own retrospective ED coded condition facts."),
    _event("mimic_iv_hosp", "hcpcsevents", "subject_id hadm_id chartdate hcpcs_cd seq_num", "transform_hcpcs", "post_hoc_chartdate_v1", "post_hoc", "HCPCS rows own retrospective coded service/procedure facts."),
    _event("mimic_iv_ed", "medrecon", "", "transform_ed_medrecon", "chart_only_v1", "source_event", "ED medication reconciliation owns medication history/reconciliation facts."),
    _event("mimic_iv_ed", "pyxis", "subject_id stay_id charttime med_rn gsn_rn", "transform_ed_pyxis", "chart_only_v1", "source_event", "ED Pyxis rows own medication dispense/access facts, not administration."),
    _event("mimic_iv_icu", "inputevents", "subject_id stay_id orderid itemid starttime", "transform_icu_input", "icu_interval_completion_v1", "source_event", "ICU input rows own administered input/infusion intervals."),
    _event("mimic_iv_icu", "outputevents", "", "transform_icu_output", "icu_output_chart_store_v1", "source_event", "ICU output rows own measured output facts."),
    # Support rows are loaded and traceable but never transformed independently.
    _support("mimic_iv_hosp", "poe", "subject_id poe_id poe_seq", "hosp.poe_timeline", "support_poe_v1", "Raw POE rows cross-check derived order action and time without duplicating facts."),
    _support("mimic_iv_hosp", "poe_detail", "subject_id poe_id poe_seq field_name", "hosp.poe_timeline", "support_parent_inherit_v1", "POE detail rows enrich their owning order facts."),
    _support("mimic_iv_hosp", "emar_detail", "", "hosp.emar", "support_parent_inherit_v1", "eMAR detail rows enrich dose, route, product, and infusion attributes."),
    _support("mimic_iv_icu", "ingredientevents", "subject_id stay_id orderid itemid starttime", "icu.inputevents", "support_icu_interval_v1", "Ingredient rows describe components of owning ICU inputs and must not duplicate administration facts."),
    _support("mimic_iv_note", "radiology_detail", "", "note.radiology", "support_parent_inherit_v1", "Radiology detail rows enrich their owning report document."),
    _support("mimic_iv_note", "discharge_detail", "note_id field_ordinal", "note.discharge", "support_parent_inherit_v1", "Discharge detail rows enrich their owning discharge document."),
    # Context rows define patient and encounter boundaries or deferred semantics.
    _context("mimic_iv_hosp", "patients", "subject_id", "Patient demographics provide subject context and do not emit clinical facts."),
    _context("mimic_iv_hosp", "admissions", "subject_id hadm_id", "Admission rows define hospital encounter boundaries and administrative context."),
    _context("mimic_iv_hosp", "drgcodes", "", "DRG rows are end-of-stay administrative grouping context, not independent clinical facts."),
    _context("mimic_iv_icu", "icustays", "stay_id", "ICU stay rows define ICU encounter boundaries."),
    _context("mimic_iv_icu", "datetimeevents", "", "ICU datetime value semantics remain deferred until value-time rules are frozen."),
    _context("mimic_iv_ed", "edstays", "stay_id", "ED stay rows define ED encounter boundaries and disposition context."),
)


EVENT_SOURCE_REGISTRY: tuple[SourceSpec, ...] = tuple(
    spec for spec in SOURCE_CATALOG if spec.role == "event"
)

# Compatibility name for callers that historically meant event-generating
# sources. New code should use EVENT_SOURCE_REGISTRY explicitly.
SOURCE_REGISTRY = EVENT_SOURCE_REGISTRY
SOURCE_BY_PATH = {(spec.module, spec.table): spec for spec in SOURCE_CATALOG}
REGISTERED_SOURCE_PATHS = frozenset(SOURCE_BY_PATH)
REQUIRED_SOURCE_PATHS = frozenset(
    (spec.module, spec.table) for spec in SOURCE_CATALOG if spec.required
)

UPSTREAM_EXCLUDED_SOURCES: dict[str, str] = {
    "icu.chartevents": "High-volume bedside monitoring was explicitly excluded upstream.",
    "hosp.omr": "OMR lacks native hadm_id and cannot be attributed to an admission safely.",
}


def _catalog_payload() -> dict[str, object]:
    return {
        "version": SOURCE_CATALOG_VERSION,
        "time_policies": [asdict(TIME_POLICIES[key]) for key in sorted(TIME_POLICIES)],
        "sources": [asdict(spec) for spec in SOURCE_CATALOG],
        "upstream_excluded_sources": UPSTREAM_EXCLUDED_SOURCES,
    }


SOURCE_CATALOG_SHA256 = hashlib.sha256(
    json.dumps(
        _catalog_payload(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


def validate_source_catalog() -> None:
    errors: list[str] = []
    paths = [spec.source_table for spec in SOURCE_CATALOG]
    if len(paths) != len(set(paths)):
        errors.append("duplicate source_table path")
    event_paths = {spec.source_table for spec in EVENT_SOURCE_REGISTRY}
    for spec in SOURCE_CATALOG:
        if spec.time_policy not in TIME_POLICIES:
            errors.append(f"{spec.source_table}: unknown time policy {spec.time_policy}")
        if not spec.inclusion_reason and spec.role != "excluded":
            errors.append(f"{spec.source_table}: inclusion reason missing")
        if spec.role == "event":
            if spec.fact_owner != spec.source_table:
                errors.append(f"{spec.source_table}: event fact owner must be itself")
            if not spec.transformer_name:
                errors.append(f"{spec.source_table}: transformer missing")
            if spec.evidence_phase not in {"source_event", "post_hoc", "administrative_end"}:
                errors.append(f"{spec.source_table}: evidence phase invalid")
        else:
            if spec.transformer_name is not None:
                errors.append(f"{spec.source_table}: non-event source has transformer")
            if spec.evidence_phase is not None:
                errors.append(f"{spec.source_table}: non-event source has evidence phase")
        if spec.role == "support" and spec.fact_owner not in event_paths:
            errors.append(f"{spec.source_table}: support fact owner is not an event source")
        if spec.role == "context" and spec.fact_owner is not None:
            errors.append(f"{spec.source_table}: context must not own facts")
        if spec.role == "excluded" and not spec.exclusion_reason:
            errors.append(f"{spec.source_table}: exclusion reason missing")
        fields = spec.native_key_fields
        if spec.identity_strategy == "native_key" and len(fields) != 1:
            errors.append(f"{spec.source_table}: native_key requires one field")
        if spec.identity_strategy == "composite_key" and len(fields) < 2:
            errors.append(f"{spec.source_table}: composite_key requires multiple fields")
        if spec.identity_strategy == "canonical_row_hash_with_occurrence" and fields:
            errors.append(f"{spec.source_table}: row hash strategy must not declare key fields")
    if errors:
        raise ValueError("invalid source catalog:\n- " + "\n- ".join(errors))


validate_source_catalog()
