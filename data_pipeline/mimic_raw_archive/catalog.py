"""Locked raw-source catalog and native linkage rules."""

from __future__ import annotations

from dataclasses import dataclass

from data_pipeline.mimic_source_catalog import SOURCE_BY_KEY, SourceSpec


@dataclass(frozen=True)
class ArchiveSource:
    key: str
    module: str
    output_key: str
    link: str
    parent_key: str | None = None
    match_fields: tuple[str, ...] = ()

    @property
    def source(self) -> SourceSpec:
        return SOURCE_BY_KEY[self.key]


def _source(
    key: str,
    module: str,
    *,
    output_key: str | None = None,
    link: str = "direct_hadm",
    parent_key: str | None = None,
    match_fields: tuple[str, ...] = (),
) -> ArchiveSource:
    return ArchiveSource(
        key=key,
        module=module,
        output_key=output_key or key,
        link=link,
        parent_key=parent_key,
        match_fields=match_fields,
    )


ARCHIVE_SOURCES: tuple[ArchiveSource, ...] = (
    _source("patients", "mimic_iv_hosp", link="subject"),
    _source("admissions", "mimic_iv_hosp"),
    _source("transfers", "mimic_iv_hosp"),
    _source("services", "mimic_iv_hosp"),
    _source("labevents", "mimic_iv_hosp"),
    _source("microbiologyevents", "mimic_iv_hosp"),
    _source("poe", "mimic_iv_hosp"),
    _source(
        "poe_detail", "mimic_iv_hosp", link="parent",
        parent_key="poe", match_fields=("poe_id", "poe_seq"),
    ),
    _source("pharmacy", "mimic_iv_hosp"),
    _source("prescriptions", "mimic_iv_hosp"),
    _source("emar", "mimic_iv_hosp"),
    _source(
        "emar_detail", "mimic_iv_hosp", link="parent",
        parent_key="emar", match_fields=("emar_id", "emar_seq"),
    ),
    _source("diagnoses_icd", "mimic_iv_hosp"),
    _source("procedures_icd", "mimic_iv_hosp"),
    _source("hcpcsevents", "mimic_iv_hosp"),
    _source("drgcodes", "mimic_iv_hosp"),
    _source("icustays", "mimic_iv_icu"),
    _source("datetimeevents", "mimic_iv_icu"),
    _source("ingredientevents", "mimic_iv_icu"),
    _source("inputevents", "mimic_iv_icu"),
    _source("outputevents", "mimic_iv_icu"),
    _source("procedureevents", "mimic_iv_icu"),
    _source("edstays", "mimic_iv_ed", link="ed_parent"),
    _source("triage", "mimic_iv_ed", link="ed_child", parent_key="edstays"),
    _source("vitalsign", "mimic_iv_ed", link="ed_child", parent_key="edstays"),
    _source(
        "ed_diagnosis", "mimic_iv_ed", output_key="diagnosis",
        link="ed_child", parent_key="edstays",
    ),
    _source("medrecon", "mimic_iv_ed", link="ed_child", parent_key="edstays"),
    _source("pyxis", "mimic_iv_ed", link="ed_child", parent_key="edstays"),
    _source("discharge", "mimic_iv_note"),
    _source(
        "discharge_detail", "mimic_iv_note", link="parent",
        parent_key="discharge", match_fields=("note_id",),
    ),
    _source("radiology", "mimic_iv_note"),
    _source(
        "radiology_detail", "mimic_iv_note", link="parent",
        parent_key="radiology", match_fields=("note_id",),
    ),
)

REFERENCE_SOURCE_KEYS: tuple[str, ...] = (
    "d_labitems",
    "d_icd_diagnoses",
    "d_icd_procedures",
    "d_hcpcs",
    "provider",
    "d_items",
    "caregiver",
)

EXCLUDED_SOURCE_REASONS: dict[str, str] = {
    "chartevents": "high-volume ICU bedside monitoring explicitly excluded",
    "omr": "no native hadm_id; temporal attribution is forbidden",
}

MODULE_TABLES: dict[str, tuple[ArchiveSource, ...]] = {
    module: tuple(source for source in ARCHIVE_SOURCES if source.module == module)
    for module in ("mimic_iv_hosp", "mimic_iv_icu", "mimic_iv_ed", "mimic_iv_note")
}

ARCHIVE_SOURCE_BY_KEY = {source.key: source for source in ARCHIVE_SOURCES}


def validate_catalog() -> None:
    keys = [source.key for source in ARCHIVE_SOURCES]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate raw archive source key")
    if "chartevents" in keys:
        raise ValueError("chartevents must never enter the raw admission archive")
    for source in ARCHIVE_SOURCES:
        if source.key not in SOURCE_BY_KEY:
            raise ValueError(f"unknown MIMIC source: {source.key}")
        if source.link == "parent" and not source.parent_key:
            raise ValueError(f"incomplete parent linkage rule: {source.key}")
        if source.link == "parent" and not source.match_fields:
            raise ValueError(f"missing parent match fields: {source.key}")
