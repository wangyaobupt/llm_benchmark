"""Source tables and join rules for the 10k visit extract."""

from __future__ import annotations

from dataclasses import dataclass

from data_pipeline.mimic_source_catalog import SOURCE_BY_KEY


@dataclass(frozen=True)
class ExtractSource:
    key: str
    link: str
    parent_key: str | None = None
    match_fields: tuple[str, ...] = ()


FACT_SOURCES: tuple[ExtractSource, ...] = (
    ExtractSource("admissions", "direct_hadm"),
    ExtractSource("patients", "subject"),
    ExtractSource("diagnoses_icd", "direct_hadm"),
    ExtractSource("procedures_icd", "direct_hadm"),
    ExtractSource("poe", "direct_hadm"),
    ExtractSource(
        "poe_detail",
        "parent",
        parent_key="poe",
        match_fields=("poe_id", "poe_seq"),
    ),
    ExtractSource("labevents", "direct_hadm"),
    ExtractSource("prescriptions", "direct_hadm"),
    ExtractSource("services", "direct_hadm"),
    ExtractSource("transfers", "direct_hadm"),
    ExtractSource("edstays", "ed_parent"),
    ExtractSource("triage", "ed_child"),
    ExtractSource("vitalsign", "ed_child"),
    ExtractSource("ed_diagnosis", "ed_child"),
    ExtractSource("medrecon", "ed_child"),
    ExtractSource("discharge", "direct_hadm"),
    ExtractSource("radiology", "direct_hadm"),
    ExtractSource(
        "radiology_detail",
        "parent",
        parent_key="radiology",
        match_fields=("note_id",),
    ),
)

DICTIONARY_KEYS: tuple[str, ...] = (
    "d_labitems",
    "d_icd_diagnoses",
    "d_icd_procedures",
)

FUNNEL_KEYS: tuple[str, ...] = (
    "patients",
    "admissions",
    "diagnoses_icd",
    "d_icd_diagnoses",
    "discharge",
)

REQUIRED_SOURCE_KEYS: tuple[str, ...] = tuple(
    dict.fromkeys(
        [source.key for source in FACT_SOURCES]
        + list(DICTIONARY_KEYS)
        + ["edstays"]
    )
)


def validate_catalog() -> None:
    for source in FACT_SOURCES:
        if source.key not in SOURCE_BY_KEY:
            raise ValueError(f"unknown extract source: {source.key}")
        if source.link == "parent":
            if not source.parent_key or source.parent_key not in SOURCE_BY_KEY:
                raise ValueError(f"parent source missing for {source.key}")
            if not source.match_fields:
                raise ValueError(f"match_fields required for {source.key}")
    for key in DICTIONARY_KEYS:
        if key not in SOURCE_BY_KEY:
            raise ValueError(f"unknown dictionary source: {key}")
