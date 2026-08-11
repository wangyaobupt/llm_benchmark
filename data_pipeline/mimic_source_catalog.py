"""Shared locked MIMIC source-file, header, and type contracts."""

from __future__ import annotations

import csv
import gzip
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceSpec:
    key: str
    relative_path: str
    header: tuple[str, ...]
    version: str


def _spec(
    key: str,
    relative_path: str,
    header: str,
    version: str,
) -> SourceSpec:
    return SourceSpec(key, relative_path, tuple(header.split()), version)


SOURCE_SPECS: tuple[SourceSpec, ...] = (
    _spec(
        "patients",
        "mimic-iv-3.1/hosp/patients.csv.gz",
        "subject_id gender anchor_age anchor_year anchor_year_group dod",
        "3.1",
    ),
    _spec(
        "admissions",
        "mimic-iv-3.1/hosp/admissions.csv.gz",
        "subject_id hadm_id admittime dischtime deathtime admission_type "
        "admit_provider_id admission_location discharge_location insurance language "
        "marital_status race edregtime edouttime hospital_expire_flag",
        "3.1",
    ),
    _spec(
        "transfers",
        "mimic-iv-3.1/hosp/transfers.csv.gz",
        "subject_id hadm_id transfer_id eventtype careunit intime outtime",
        "3.1",
    ),
    _spec(
        "services",
        "mimic-iv-3.1/hosp/services.csv.gz",
        "subject_id hadm_id transfertime prev_service curr_service",
        "3.1",
    ),
    _spec(
        "labevents",
        "mimic-iv-3.1/hosp/labevents.csv.gz",
        "labevent_id subject_id hadm_id specimen_id itemid order_provider_id "
        "charttime storetime value valuenum valueuom ref_range_lower ref_range_upper "
        "flag priority comments",
        "3.1",
    ),
    _spec(
        "d_labitems",
        "mimic-iv-3.1/hosp/d_labitems.csv.gz",
        "itemid label fluid category",
        "3.1",
    ),
    _spec(
        "microbiologyevents",
        "mimic-iv-3.1/hosp/microbiologyevents.csv.gz",
        "microevent_id subject_id hadm_id micro_specimen_id order_provider_id chartdate "
        "charttime spec_itemid spec_type_desc test_seq storedate storetime test_itemid "
        "test_name org_itemid org_name isolate_num quantity ab_itemid ab_name "
        "dilution_text dilution_comparison dilution_value interpretation comments",
        "3.1",
    ),
    _spec(
        "omr",
        "mimic-iv-3.1/hosp/omr.csv.gz",
        "subject_id chartdate seq_num result_name result_value",
        "3.1",
    ),
    _spec(
        "poe",
        "mimic-iv-3.1/hosp/poe.csv.gz",
        "poe_id poe_seq subject_id hadm_id ordertime order_type order_subtype "
        "transaction_type discontinue_of_poe_id discontinued_by_poe_id "
        "order_provider_id order_status",
        "3.1",
    ),
    _spec(
        "poe_detail",
        "mimic-iv-3.1/hosp/poe_detail.csv.gz",
        "poe_id poe_seq subject_id field_name field_value",
        "3.1",
    ),
    _spec(
        "pharmacy",
        "mimic-iv-3.1/hosp/pharmacy.csv.gz",
        "subject_id hadm_id pharmacy_id poe_id starttime stoptime medication proc_type "
        "status entertime verifiedtime route frequency disp_sched infusion_type "
        "sliding_scale lockout_interval basal_rate one_hr_max doses_per_24_hrs duration "
        "duration_interval expiration_value expiration_unit expirationdate dispensation "
        "fill_quantity",
        "3.1",
    ),
    _spec(
        "prescriptions",
        "mimic-iv-3.1/hosp/prescriptions.csv.gz",
        "subject_id hadm_id pharmacy_id poe_id poe_seq order_provider_id starttime "
        "stoptime drug_type drug formulary_drug_cd gsn ndc prod_strength form_rx "
        "dose_val_rx dose_unit_rx form_val_disp form_unit_disp doses_per_24_hrs route",
        "3.1",
    ),
    _spec(
        "emar",
        "mimic-iv-3.1/hosp/emar.csv.gz",
        "subject_id hadm_id emar_id emar_seq poe_id pharmacy_id enter_provider_id "
        "charttime medication event_txt scheduletime storetime",
        "3.1",
    ),
    _spec(
        "emar_detail",
        "mimic-iv-3.1/hosp/emar_detail.csv.gz",
        "subject_id emar_id emar_seq parent_field_ordinal administration_type pharmacy_id "
        "barcode_type reason_for_no_barcode complete_dose_not_given dose_due dose_due_unit "
        "dose_given dose_given_unit will_remainder_of_dose_be_given product_amount_given "
        "product_unit product_code product_description product_description_other "
        "prior_infusion_rate infusion_rate infusion_rate_adjustment "
        "infusion_rate_adjustment_amount infusion_rate_unit route infusion_complete "
        "completion_interval new_iv_bag_hung continued_infusion_in_other_location "
        "restart_interval side site non_formulary_visual_verification",
        "3.1",
    ),
    _spec(
        "diagnoses_icd",
        "mimic-iv-3.1/hosp/diagnoses_icd.csv.gz",
        "subject_id hadm_id seq_num icd_code icd_version",
        "3.1",
    ),
    _spec(
        "d_icd_diagnoses",
        "mimic-iv-3.1/hosp/d_icd_diagnoses.csv.gz",
        "icd_code icd_version long_title",
        "3.1",
    ),
    _spec(
        "procedures_icd",
        "mimic-iv-3.1/hosp/procedures_icd.csv.gz",
        "subject_id hadm_id seq_num chartdate icd_code icd_version",
        "3.1",
    ),
    _spec(
        "d_icd_procedures",
        "mimic-iv-3.1/hosp/d_icd_procedures.csv.gz",
        "icd_code icd_version long_title",
        "3.1",
    ),
    _spec(
        "hcpcsevents",
        "mimic-iv-3.1/hosp/hcpcsevents.csv.gz",
        "subject_id hadm_id chartdate hcpcs_cd seq_num short_description",
        "3.1",
    ),
    _spec(
        "d_hcpcs",
        "mimic-iv-3.1/hosp/d_hcpcs.csv.gz",
        "code category long_description short_description",
        "3.1",
    ),
    _spec(
        "drgcodes",
        "mimic-iv-3.1/hosp/drgcodes.csv.gz",
        "subject_id hadm_id drg_type drg_code description drg_severity drg_mortality",
        "3.1",
    ),
    _spec("provider", "mimic-iv-3.1/hosp/provider.csv.gz", "provider_id", "3.1"),
    _spec(
        "icustays",
        "mimic-iv-3.1/icu/icustays.csv.gz",
        "subject_id hadm_id stay_id first_careunit last_careunit intime outtime los",
        "3.1",
    ),
    _spec(
        "chartevents",
        "mimic-iv-3.1/icu/chartevents.csv.gz",
        "subject_id hadm_id stay_id caregiver_id charttime storetime itemid value "
        "valuenum valueuom warning",
        "3.1",
    ),
    _spec(
        "datetimeevents",
        "mimic-iv-3.1/icu/datetimeevents.csv.gz",
        "subject_id hadm_id stay_id caregiver_id charttime storetime itemid value "
        "valueuom warning",
        "3.1",
    ),
    _spec(
        "ingredientevents",
        "mimic-iv-3.1/icu/ingredientevents.csv.gz",
        "subject_id hadm_id stay_id caregiver_id starttime endtime storetime itemid amount "
        "amountuom rate rateuom orderid linkorderid statusdescription originalamount "
        "originalrate",
        "3.1",
    ),
    _spec(
        "inputevents",
        "mimic-iv-3.1/icu/inputevents.csv.gz",
        "subject_id hadm_id stay_id caregiver_id starttime endtime storetime itemid amount "
        "amountuom rate rateuom orderid linkorderid ordercategoryname "
        "secondaryordercategoryname ordercomponenttypedescription ordercategorydescription "
        "patientweight totalamount totalamountuom isopenbag continueinnextdept "
        "statusdescription originalamount originalrate",
        "3.1",
    ),
    _spec(
        "outputevents",
        "mimic-iv-3.1/icu/outputevents.csv.gz",
        "subject_id hadm_id stay_id caregiver_id charttime storetime itemid value valueuom",
        "3.1",
    ),
    _spec(
        "procedureevents",
        "mimic-iv-3.1/icu/procedureevents.csv.gz",
        "subject_id hadm_id stay_id caregiver_id starttime endtime storetime itemid value "
        "valueuom location locationcategory orderid linkorderid ordercategoryname "
        "ordercategorydescription patientweight isopenbag continueinnextdept "
        "statusdescription originalamount originalrate",
        "3.1",
    ),
    _spec(
        "d_items",
        "mimic-iv-3.1/icu/d_items.csv.gz",
        "itemid label abbreviation linksto category unitname param_type lownormalvalue "
        "highnormalvalue",
        "3.1",
    ),
    _spec("caregiver", "mimic-iv-3.1/icu/caregiver.csv.gz", "caregiver_id", "3.1"),
    _spec(
        "edstays",
        "mimic-iv-ed/ed/edstays.csv.gz",
        "subject_id hadm_id stay_id intime outtime gender race arrival_transport disposition",
        "2.2",
    ),
    _spec(
        "triage",
        "mimic-iv-ed/ed/triage.csv.gz",
        "subject_id stay_id temperature heartrate resprate o2sat sbp dbp pain acuity "
        "chiefcomplaint",
        "2.2",
    ),
    _spec(
        "vitalsign",
        "mimic-iv-ed/ed/vitalsign.csv.gz",
        "subject_id stay_id charttime temperature heartrate resprate o2sat sbp dbp rhythm pain",
        "2.2",
    ),
    _spec(
        "ed_diagnosis",
        "mimic-iv-ed/ed/diagnosis.csv.gz",
        "subject_id stay_id seq_num icd_code icd_version icd_title",
        "2.2",
    ),
    _spec(
        "medrecon",
        "mimic-iv-ed/ed/medrecon.csv.gz",
        "subject_id stay_id charttime name gsn ndc etc_rn etccode etcdescription",
        "2.2",
    ),
    _spec(
        "pyxis",
        "mimic-iv-ed/ed/pyxis.csv.gz",
        "subject_id stay_id charttime med_rn name gsn_rn gsn",
        "2.2",
    ),
    _spec(
        "discharge",
        "mimic-iv-note-2.2/note/discharge.csv.gz",
        "note_id subject_id hadm_id note_type note_seq charttime storetime text",
        "2.2",
    ),
    _spec(
        "discharge_detail",
        "mimic-iv-note-2.2/note/discharge_detail.csv.gz",
        "note_id subject_id field_name field_value field_ordinal",
        "2.2",
    ),
    _spec(
        "radiology",
        "mimic-iv-note-2.2/note/radiology.csv.gz",
        "note_id subject_id hadm_id note_type note_seq charttime storetime text",
        "2.2",
    ),
    _spec(
        "radiology_detail",
        "mimic-iv-note-2.2/note/radiology_detail.csv.gz",
        "note_id subject_id field_name field_value field_ordinal",
        "2.2",
    ),
)

SOURCE_BY_KEY = {spec.key: spec for spec in SOURCE_SPECS}


@dataclass(frozen=True)
class EpisodeDatasetPaths:
    data_root: Path

    @classmethod
    def from_root(cls, data_root: Path) -> "EpisodeDatasetPaths":
        return cls(Path(data_root).resolve())

    def source_path(self, key: str) -> Path:
        try:
            spec = SOURCE_BY_KEY[key]
        except KeyError as error:
            raise KeyError(f"未知 MIMIC 来源：{key}") from error
        return self.data_root / Path(spec.relative_path)

    def required_files(self) -> tuple[Path, ...]:
        return tuple(self.source_path(spec.key) for spec in SOURCE_SPECS)

    def validate(self) -> None:
        missing = [path for path in self.required_files() if not path.is_file()]
        if missing:
            details = "\n".join(f"- {path}" for path in missing)
            raise FileNotFoundError(f"缺少 episode 聚合必需文件：\n{details}")

        errors: list[str] = []
        for spec in SOURCE_SPECS:
            path = self.source_path(spec.key)
            with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
                actual = tuple(next(csv.reader(handle), ()))
            if actual != spec.header:
                errors.append(
                    f"- {path}: 预期 {list(spec.header)}，实际 {list(actual)}"
                )
        if errors:
            raise ValueError("episode 聚合 CSV 表头不符合锁定 schema：\n" + "\n".join(errors))
