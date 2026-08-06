from __future__ import annotations

from dataclasses import dataclass

from mimic_episode.source_catalog import SOURCE_BY_KEY


@dataclass(frozen=True)
class GenericEventSpec:
    source_key: str
    from_sql: str
    event_id_expr: str
    native_row_key_expr: str
    subject_expr: str
    hadm_expr: str
    contact_expr: str
    event_type: str
    event_subtype_expr: str
    event_time_expr: str
    available_time_expr: str
    recorded_time_expr: str
    start_time_expr: str
    end_time_expr: str
    time_precision: str
    status_expr: str
    decision_level: str
    concept_id_expr: str
    concept_name_expr: str
    raw_code_expr: str
    raw_value_expr: str
    raw_unit_expr: str
    flag_expr: str = "NULL::VARCHAR"
    allow_temporal: bool = False
    group_rows: bool = False

    @property
    def source_table(self) -> str:
        path = SOURCE_BY_KEY[self.source_key].relative_path
        return path.removesuffix(".csv.gz")

    @property
    def source_version(self) -> str:
        return SOURCE_BY_KEY[self.source_key].version


def _md5_group_key(prefix: str, *expressions: str) -> str:
    joined = ", ".join(f"COALESCE(CAST({expr} AS VARCHAR), '')" for expr in expressions)
    return f"'{prefix}:' || md5(concat_ws('|', {joined}))"


def _md5_key(prefix: str, *expressions: str) -> str:
    return _md5_group_key(prefix, *expressions, "r._source_row_number")


GENERIC_EVENT_SPECS: tuple[GenericEventSpec, ...] = (
    GenericEventSpec(
        "transfers",
        "raw_transfers r",
        "'TRANSFER:' || r.transfer_id",
        "'transfer_id=' || r.transfer_id",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "'TR:' || r.transfer_id",
        "transfer",
        "r.eventtype",
        "TRY_CAST(r.intime AS TIMESTAMP)",
        "TRY_CAST(r.intime AS TIMESTAMP)",
        "TRY_CAST(r.intime AS TIMESTAMP)",
        "TRY_CAST(r.intime AS TIMESTAMP)",
        "TRY_CAST(r.outtime AS TIMESTAMP)",
        "timestamp",
        "r.eventtype",
        "observed_decision",
        "NULL::VARCHAR",
        "r.careunit",
        "NULL::VARCHAR",
        "r.eventtype",
        "NULL::VARCHAR",
    ),
    GenericEventSpec(
        "services",
        "raw_services r",
        _md5_key("SERVICE", "r.subject_id", "r.hadm_id", "r.transfertime", "r.curr_service"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'hadm_id=' || r.hadm_id, "
        "'transfertime=' || r.transfertime, 'curr_service=' || COALESCE(r.curr_service, ''))",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "NULL::VARCHAR",
        "service_transfer",
        "r.curr_service",
        "TRY_CAST(r.transfertime AS TIMESTAMP)",
        "TRY_CAST(r.transfertime AS TIMESTAMP)",
        "TRY_CAST(r.transfertime AS TIMESTAMP)",
        "TRY_CAST(r.transfertime AS TIMESTAMP)",
        "NULL::TIMESTAMP",
        "timestamp",
        "r.curr_service",
        "observed_decision",
        "NULL::VARCHAR",
        "r.curr_service",
        "r.prev_service",
        "r.curr_service",
        "NULL::VARCHAR",
    ),
    GenericEventSpec(
        "poe",
        "raw_poe r",
        "'POE:' || r.poe_id",
        "'poe_id=' || r.poe_id",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "NULL::VARCHAR",
        "provider_order",
        "r.order_type",
        "TRY_CAST(r.ordertime AS TIMESTAMP)",
        "TRY_CAST(r.ordertime AS TIMESTAMP)",
        "TRY_CAST(r.ordertime AS TIMESTAMP)",
        "TRY_CAST(r.ordertime AS TIMESTAMP)",
        "NULL::TIMESTAMP",
        "timestamp",
        "COALESCE(r.transaction_type, r.order_status)",
        "observed_decision",
        "r.order_type",
        "COALESCE(r.order_subtype, r.order_type)",
        "r.order_type",
        "r.order_subtype",
        "NULL::VARCHAR",
        group_rows=True,
    ),
    GenericEventSpec(
        "pharmacy",
        "raw_pharmacy r",
        "'PHARM:' || r.pharmacy_id",
        "'pharmacy_id=' || r.pharmacy_id",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "NULL::VARCHAR",
        "pharmacy_order",
        "r.proc_type",
        "COALESCE(TRY_CAST(r.starttime AS TIMESTAMP), TRY_CAST(r.entertime AS TIMESTAMP))",
        "COALESCE(TRY_CAST(r.verifiedtime AS TIMESTAMP), TRY_CAST(r.entertime AS TIMESTAMP))",
        "TRY_CAST(r.entertime AS TIMESTAMP)",
        "TRY_CAST(r.starttime AS TIMESTAMP)",
        "TRY_CAST(r.stoptime AS TIMESTAMP)",
        "timestamp",
        "r.status",
        "observed_decision",
        "NULL::VARCHAR",
        "r.medication",
        "NULL::VARCHAR",
        "r.medication",
        "r.route",
        group_rows=True,
    ),
    GenericEventSpec(
        "prescriptions",
        "raw_prescriptions r",
        _md5_key("RX", "r.subject_id", "r.pharmacy_id", "r.poe_seq", "r.drug", "r.starttime"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'pharmacy_id=' || r.pharmacy_id, "
        "'poe_seq=' || COALESCE(r.poe_seq, ''), 'drug=' || COALESCE(r.drug, ''), "
        "'starttime=' || COALESCE(r.starttime, ''))",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "NULL::VARCHAR",
        "prescription",
        "r.drug_type",
        "TRY_CAST(r.starttime AS TIMESTAMP)",
        "TRY_CAST(r.starttime AS TIMESTAMP)",
        "TRY_CAST(r.starttime AS TIMESTAMP)",
        "TRY_CAST(r.starttime AS TIMESTAMP)",
        "TRY_CAST(r.stoptime AS TIMESTAMP)",
        "timestamp",
        "r.drug_type",
        "observed_decision",
        "COALESCE(r.ndc, r.gsn, r.formulary_drug_cd)",
        "r.drug",
        "COALESCE(r.ndc, r.gsn, r.formulary_drug_cd)",
        "r.dose_val_rx",
        "r.dose_unit_rx",
    ),
    GenericEventSpec(
        "emar",
        "raw_emar r",
        "'EMAR:' || r.emar_id",
        "'emar_id=' || r.emar_id",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "NULL::VARCHAR",
        "medication_administration",
        "r.event_txt",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "TRY_CAST(r.storetime AS TIMESTAMP)",
        "TRY_CAST(r.storetime AS TIMESTAMP)",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "NULL::TIMESTAMP",
        "timestamp",
        "r.event_txt",
        "observed_decision",
        "NULL::VARCHAR",
        "r.medication",
        "NULL::VARCHAR",
        "r.medication",
        "NULL::VARCHAR",
        group_rows=True,
    ),
    GenericEventSpec(
        "diagnoses_icd",
        "raw_diagnoses_icd r LEFT JOIN raw_d_icd_diagnoses d "
        "ON d.icd_code = r.icd_code AND d.icd_version = r.icd_version",
        _md5_key("DX", "r.subject_id", "r.hadm_id", "r.seq_num", "r.icd_code", "r.icd_version"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'hadm_id=' || r.hadm_id, "
        "'seq_num=' || r.seq_num, 'icd_code=' || r.icd_code, 'icd_version=' || r.icd_version)",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "NULL::VARCHAR",
        "diagnosis_code",
        "'ICD-' || r.icd_version",
        "NULL::TIMESTAMP",
        "NULL::TIMESTAMP",
        "NULL::TIMESTAMP",
        "NULL::TIMESTAMP",
        "NULL::TIMESTAMP",
        "unknown",
        "'post_episode_only'",
        "observed_decision",
        "r.icd_code",
        "d.long_title",
        "r.icd_code",
        "d.long_title",
        "NULL::VARCHAR",
    ),
    GenericEventSpec(
        "procedures_icd",
        "raw_procedures_icd r LEFT JOIN raw_d_icd_procedures d "
        "ON d.icd_code = r.icd_code AND d.icd_version = r.icd_version",
        _md5_key("PROC", "r.subject_id", "r.hadm_id", "r.seq_num", "r.icd_code", "r.icd_version"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'hadm_id=' || r.hadm_id, "
        "'seq_num=' || r.seq_num, 'icd_code=' || r.icd_code, 'icd_version=' || r.icd_version)",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "NULL::VARCHAR",
        "procedure_code",
        "'ICD-' || r.icd_version",
        "TRY_CAST(r.chartdate AS TIMESTAMP)",
        "NULL::TIMESTAMP",
        "NULL::TIMESTAMP",
        "TRY_CAST(r.chartdate AS TIMESTAMP)",
        "NULL::TIMESTAMP",
        "date",
        "'post_episode_only'",
        "observed_decision",
        "r.icd_code",
        "d.long_title",
        "r.icd_code",
        "d.long_title",
        "NULL::VARCHAR",
    ),
    GenericEventSpec(
        "hcpcsevents",
        "raw_hcpcsevents r",
        _md5_key("HCPCS", "r.subject_id", "r.hadm_id", "r.chartdate", "r.seq_num", "r.hcpcs_cd"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'hadm_id=' || r.hadm_id, "
        "'chartdate=' || r.chartdate, 'seq_num=' || r.seq_num, 'hcpcs_cd=' || r.hcpcs_cd)",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "NULL::VARCHAR",
        "hcpcs_event",
        "r.hcpcs_cd",
        "TRY_CAST(r.chartdate AS TIMESTAMP)",
        "NULL::TIMESTAMP",
        "NULL::TIMESTAMP",
        "TRY_CAST(r.chartdate AS TIMESTAMP)",
        "NULL::TIMESTAMP",
        "date",
        "NULL::VARCHAR",
        "observed_decision",
        "r.hcpcs_cd",
        "r.short_description",
        "r.hcpcs_cd",
        "r.short_description",
        "NULL::VARCHAR",
    ),
    GenericEventSpec(
        "drgcodes",
        "raw_drgcodes r",
        _md5_key("DRG", "r.subject_id", "r.hadm_id", "r.drg_type", "r.drg_code"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'hadm_id=' || r.hadm_id, "
        "'drg_type=' || r.drg_type, 'drg_code=' || r.drg_code)",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "NULL::VARCHAR",
        "drg_code",
        "r.drg_type",
        "NULL::TIMESTAMP",
        "NULL::TIMESTAMP",
        "NULL::TIMESTAMP",
        "NULL::TIMESTAMP",
        "NULL::TIMESTAMP",
        "unknown",
        "'post_episode_only'",
        "observed_decision",
        "r.drg_code",
        "r.description",
        "r.drg_code",
        "r.description",
        "NULL::VARCHAR",
    ),
    GenericEventSpec(
        "triage",
        "raw_triage r LEFT JOIN typed_edstays e "
        "ON e.stay_id = TRY_CAST(r.stay_id AS BIGINT) "
        "AND e.subject_id = TRY_CAST(r.subject_id AS BIGINT)",
        "'EDTRIAGE:' || r.stay_id",
        "'stay_id=' || r.stay_id",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "NULL::BIGINT",
        "'ED:' || r.stay_id",
        "ed_triage",
        "'triage'",
        "e.intime",
        "e.intime",
        "e.intime",
        "e.intime",
        "NULL::TIMESTAMP",
        "encounter_start_proxy",
        "r.acuity",
        "observed_decision",
        "'chief_complaint'",
        "'ED triage'",
        "'chief_complaint'",
        "r.chiefcomplaint",
        "NULL::VARCHAR",
    ),
    GenericEventSpec(
        "vitalsign",
        "raw_vitalsign r",
        _md5_key("EDVITAL", "r.subject_id", "r.stay_id", "r.charttime"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'stay_id=' || r.stay_id, "
        "'charttime=' || r.charttime)",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "NULL::BIGINT",
        "'ED:' || r.stay_id",
        "ed_vital_signs",
        "'serial_vitals'",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "NULL::TIMESTAMP",
        "timestamp",
        "NULL::VARCHAR",
        "observed_decision",
        "'vital_signs'",
        "'ED vital signs'",
        "'vital_signs'",
        "concat_ws('; ', 'HR=' || COALESCE(r.heartrate, ''), 'SpO2=' || COALESCE(r.o2sat, ''), "
        "'BP=' || COALESCE(r.sbp, '') || '/' || COALESCE(r.dbp, ''))",
        "NULL::VARCHAR",
    ),
    GenericEventSpec(
        "ed_diagnosis",
        "raw_ed_diagnosis r LEFT JOIN typed_edstays e "
        "ON e.stay_id = TRY_CAST(r.stay_id AS BIGINT) "
        "AND e.subject_id = TRY_CAST(r.subject_id AS BIGINT)",
        _md5_key("EDDX", "r.subject_id", "r.stay_id", "r.seq_num", "r.icd_code"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'stay_id=' || r.stay_id, "
        "'seq_num=' || r.seq_num, 'icd_code=' || r.icd_code)",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "NULL::BIGINT",
        "'ED:' || r.stay_id",
        "ed_diagnosis_code",
        "'ICD-' || r.icd_version",
        "e.outtime",
        "NULL::TIMESTAMP",
        "NULL::TIMESTAMP",
        "e.outtime",
        "NULL::TIMESTAMP",
        "encounter_end_proxy",
        "'post_episode_only'",
        "observed_decision",
        "r.icd_code",
        "r.icd_title",
        "r.icd_code",
        "r.icd_title",
        "NULL::VARCHAR",
    ),
    GenericEventSpec(
        "medrecon",
        "raw_medrecon r",
        _md5_key("EDMEDREC", "r.subject_id", "r.stay_id", "r.charttime", "r.etc_rn", "r.name"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'stay_id=' || r.stay_id, "
        "'charttime=' || COALESCE(r.charttime, ''), 'etc_rn=' || r.etc_rn, "
        "'name=' || COALESCE(r.name, ''))",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "NULL::BIGINT",
        "'ED:' || r.stay_id",
        "medication_reconciliation",
        "r.etcdescription",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "NULL::TIMESTAMP",
        "timestamp",
        "NULL::VARCHAR",
        "observed_decision",
        "COALESCE(r.ndc, r.gsn, r.etccode)",
        "r.name",
        "COALESCE(r.ndc, r.gsn, r.etccode)",
        "r.name",
        "NULL::VARCHAR",
    ),
    GenericEventSpec(
        "pyxis",
        "raw_pyxis r",
        _md5_key("EDPYXIS", "r.subject_id", "r.stay_id", "r.charttime", "r.med_rn", "r.gsn_rn", "r.name"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'stay_id=' || r.stay_id, "
        "'charttime=' || COALESCE(r.charttime, ''), 'med_rn=' || r.med_rn, "
        "'gsn_rn=' || r.gsn_rn, 'name=' || COALESCE(r.name, ''))",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "NULL::BIGINT",
        "'ED:' || r.stay_id",
        "ed_medication_dispense",
        "'pyxis'",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "NULL::TIMESTAMP",
        "timestamp",
        "'dispensed'",
        "observed_decision",
        "r.gsn",
        "r.name",
        "r.gsn",
        "r.name",
        "NULL::VARCHAR",
    ),
    GenericEventSpec(
        "chartevents",
        "raw_chartevents r LEFT JOIN raw_d_items d ON d.itemid = r.itemid",
        _md5_group_key("ICUCHART", "r.subject_id", "r.stay_id", "r.charttime"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'stay_id=' || r.stay_id, "
        "'charttime=' || r.charttime, 'itemid=' || r.itemid, "
        "'storetime=' || COALESCE(r.storetime, ''), 'value=' || COALESCE(r.value, ''))",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "'ICU:' || r.stay_id",
        "icu_observation",
        "'chart_batch'",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "TRY_CAST(r.storetime AS TIMESTAMP)",
        "TRY_CAST(r.storetime AS TIMESTAMP)",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "NULL::TIMESTAMP",
        "timestamp",
        "r.warning",
        "observed_decision",
        "r.itemid",
        "d.label",
        "r.itemid",
        "r.value",
        "r.valueuom",
        "r.warning",
        group_rows=True,
    ),
    GenericEventSpec(
        "datetimeevents",
        "raw_datetimeevents r LEFT JOIN raw_d_items d ON d.itemid = r.itemid",
        _md5_key("ICUDATETIME", "r.subject_id", "r.stay_id", "r.charttime", "r.itemid", "r.value"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'stay_id=' || r.stay_id, "
        "'charttime=' || r.charttime, 'itemid=' || r.itemid, 'value=' || COALESCE(r.value, ''))",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "'ICU:' || r.stay_id",
        "icu_datetime_observation",
        "d.category",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "TRY_CAST(r.storetime AS TIMESTAMP)",
        "TRY_CAST(r.storetime AS TIMESTAMP)",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "NULL::TIMESTAMP",
        "timestamp",
        "r.warning",
        "observed_decision",
        "r.itemid",
        "d.label",
        "r.itemid",
        "r.value",
        "r.valueuom",
        "r.warning",
    ),
    GenericEventSpec(
        "ingredientevents",
        "raw_ingredientevents r LEFT JOIN raw_d_items d ON d.itemid = r.itemid",
        _md5_key("ICUINGREDIENT", "r.subject_id", "r.stay_id", "r.orderid", "r.itemid", "r.starttime"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'stay_id=' || r.stay_id, "
        "'orderid=' || r.orderid, 'itemid=' || r.itemid, 'starttime=' || r.starttime)",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "'ICU:' || r.stay_id",
        "icu_ingredient_input",
        "d.category",
        "TRY_CAST(r.starttime AS TIMESTAMP)",
        "TRY_CAST(r.storetime AS TIMESTAMP)",
        "TRY_CAST(r.storetime AS TIMESTAMP)",
        "TRY_CAST(r.starttime AS TIMESTAMP)",
        "TRY_CAST(r.endtime AS TIMESTAMP)",
        "timestamp",
        "r.statusdescription",
        "observed_decision",
        "r.itemid",
        "d.label",
        "r.itemid",
        "r.amount",
        "r.amountuom",
    ),
    GenericEventSpec(
        "inputevents",
        "raw_inputevents r LEFT JOIN raw_d_items d ON d.itemid = r.itemid",
        _md5_key("ICUINPUT", "r.subject_id", "r.stay_id", "r.orderid", "r.itemid", "r.starttime"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'stay_id=' || r.stay_id, "
        "'orderid=' || r.orderid, 'itemid=' || r.itemid, 'starttime=' || r.starttime)",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "'ICU:' || r.stay_id",
        "icu_input",
        "r.ordercategoryname",
        "TRY_CAST(r.starttime AS TIMESTAMP)",
        "TRY_CAST(r.storetime AS TIMESTAMP)",
        "TRY_CAST(r.storetime AS TIMESTAMP)",
        "TRY_CAST(r.starttime AS TIMESTAMP)",
        "TRY_CAST(r.endtime AS TIMESTAMP)",
        "timestamp",
        "r.statusdescription",
        "observed_decision",
        "r.itemid",
        "d.label",
        "r.itemid",
        "r.amount",
        "r.amountuom",
    ),
    GenericEventSpec(
        "outputevents",
        "raw_outputevents r LEFT JOIN raw_d_items d ON d.itemid = r.itemid",
        _md5_key("ICUOUTPUT", "r.subject_id", "r.stay_id", "r.charttime", "r.itemid", "r.value"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'stay_id=' || r.stay_id, "
        "'charttime=' || r.charttime, 'itemid=' || r.itemid, 'value=' || COALESCE(r.value, ''))",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "'ICU:' || r.stay_id",
        "icu_output",
        "d.category",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "TRY_CAST(r.storetime AS TIMESTAMP)",
        "TRY_CAST(r.storetime AS TIMESTAMP)",
        "TRY_CAST(r.charttime AS TIMESTAMP)",
        "NULL::TIMESTAMP",
        "timestamp",
        "NULL::VARCHAR",
        "observed_decision",
        "r.itemid",
        "d.label",
        "r.itemid",
        "r.value",
        "r.valueuom",
    ),
    GenericEventSpec(
        "procedureevents",
        "raw_procedureevents r LEFT JOIN raw_d_items d ON d.itemid = r.itemid",
        _md5_key("ICUPROC", "r.subject_id", "r.stay_id", "r.orderid", "r.itemid", "r.starttime"),
        "concat_ws('|', 'subject_id=' || r.subject_id, 'stay_id=' || r.stay_id, "
        "'orderid=' || r.orderid, 'itemid=' || r.itemid, 'starttime=' || r.starttime)",
        "TRY_CAST(r.subject_id AS BIGINT)",
        "TRY_CAST(r.hadm_id AS BIGINT)",
        "'ICU:' || r.stay_id",
        "icu_procedure",
        "r.ordercategoryname",
        "TRY_CAST(r.starttime AS TIMESTAMP)",
        "TRY_CAST(r.storetime AS TIMESTAMP)",
        "TRY_CAST(r.storetime AS TIMESTAMP)",
        "TRY_CAST(r.starttime AS TIMESTAMP)",
        "TRY_CAST(r.endtime AS TIMESTAMP)",
        "timestamp",
        "r.statusdescription",
        "observed_decision",
        "r.itemid",
        "d.label",
        "r.itemid",
        "r.value",
        "r.valueuom",
    ),
)


def generic_event_select(spec: GenericEventSpec) -> str:
    if spec.group_rows:
        return f"""
WITH source_rows AS (
    SELECT
        {spec.event_id_expr} AS event_id,
        {spec.subject_expr} AS subject_id,
        {spec.hadm_expr} AS native_hadm_id,
        {spec.contact_expr} AS native_contact_id,
        {spec.event_subtype_expr} AS event_subtype,
        {spec.event_time_expr} AS event_time,
        {spec.available_time_expr} AS available_time,
        {spec.recorded_time_expr} AS recorded_time,
        {spec.start_time_expr} AS start_time,
        {spec.end_time_expr} AS end_time,
        {spec.status_expr} AS status
    FROM {spec.from_sql}
)
SELECT
    event_id,
    event_id AS event_group_id,
    ANY_VALUE(subject_id) AS subject_id,
    ANY_VALUE(native_hadm_id) AS native_hadm_id,
    ANY_VALUE(native_contact_id) AS native_contact_id,
    '{spec.event_type}' AS event_type,
    ANY_VALUE(event_subtype) AS event_subtype,
    MIN(event_time) AS event_time,
    MAX(available_time) AS available_time,
    MAX(recorded_time) AS recorded_time,
    MIN(start_time) AS start_time,
    MAX(end_time) AS end_time,
    '{spec.time_precision}' AS time_precision,
    MAX(status) AS status,
    '{spec.decision_level}' AS decision_evidence_level,
    {str(spec.allow_temporal).upper()} AS allow_temporal,
    '{spec.source_table}' AS source_table,
    '{spec.source_version}' AS source_version
FROM source_rows
GROUP BY event_id
""".strip()
    return f"""
SELECT DISTINCT
    {spec.event_id_expr} AS event_id,
    {spec.event_id_expr} AS event_group_id,
    {spec.subject_expr} AS subject_id,
    {spec.hadm_expr} AS native_hadm_id,
    {spec.contact_expr} AS native_contact_id,
    '{spec.event_type}' AS event_type,
    {spec.event_subtype_expr} AS event_subtype,
    {spec.event_time_expr} AS event_time,
    {spec.available_time_expr} AS available_time,
    {spec.recorded_time_expr} AS recorded_time,
    {spec.start_time_expr} AS start_time,
    {spec.end_time_expr} AS end_time,
    '{spec.time_precision}' AS time_precision,
    {spec.status_expr} AS status,
    '{spec.decision_level}' AS decision_evidence_level,
    {str(spec.allow_temporal).upper()} AS allow_temporal,
    '{spec.source_table}' AS source_table,
    '{spec.source_version}' AS source_version
FROM {spec.from_sql}
""".strip()


def generic_item_select(spec: GenericEventSpec) -> str:
    return f"""
SELECT
    'ITEM:{spec.source_key}:' || CAST(r._source_row_number AS VARCHAR) AS item_event_id,
    {spec.event_id_expr} AS event_id,
    {spec.native_row_key_expr} AS native_row_key,
    {spec.concept_id_expr} AS concept_id,
    {spec.concept_name_expr} AS concept_name,
    {spec.raw_code_expr} AS raw_code,
    {spec.raw_value_expr} AS raw_value,
    {spec.raw_unit_expr} AS raw_unit,
    TRY_CAST({spec.raw_value_expr} AS DOUBLE) AS normalized_value,
    {spec.raw_unit_expr} AS normalized_unit,
    {spec.flag_expr} AS flag,
    r._source_row_number AS item_ordinal,
    to_json(r) AS raw_payload,
    '{spec.source_table}' AS source_table,
    '{spec.source_version}' AS source_version
FROM {spec.from_sql}
""".strip()


def generic_events_sql() -> str:
    return "\nUNION ALL\n".join(
        generic_event_select(spec) for spec in GENERIC_EVENT_SPECS
    )


def generic_items_sql() -> str:
    return "\nUNION ALL\n".join(
        generic_item_select(spec) for spec in GENERIC_EVENT_SPECS
    )
