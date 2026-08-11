"""Frozen visit archive schema and observable validation interface."""

from __future__ import annotations

from typing import Any


SCHEMA_NAME = "mimic_visit_archive"
SCHEMA_VERSION = "1.0.0"

TOP_LEVEL_FIELDS = (
    "metadata",
    "identifiers",
    "episode",
    "demographics",
    "presentation",
    "vitals",
    "orders",
    "investigations",
    "diagnoses",
    "treatments",
    "care_path",
    "discharge",
    "longitudinal_refs",
    "partition",
    "decision_snapshots",
)

TIME_FIELDS = ("event_time", "available_time", "recorded_time")
POST_HOC_KINDS = frozenset({"coded_diagnosis", "drg", "discharge_summary"})


class SchemaValidationError(ValueError):
    """Raised when a record violates the frozen archive contract."""


def validate_visit_archive(record: dict[str, Any]) -> None:
    """Validate the stable public Interface of a visit archive record."""
    if tuple(record) != TOP_LEVEL_FIELDS:
        raise SchemaValidationError(
            f"top-level schema drift: expected {TOP_LEVEL_FIELDS}, got {tuple(record)}"
        )
    metadata = record["metadata"]
    if metadata.get("schema_name") != SCHEMA_NAME:
        raise SchemaValidationError("unexpected schema_name")
    if metadata.get("schema_version") != SCHEMA_VERSION:
        raise SchemaValidationError("unexpected schema_version")

    episode = record["episode"]
    for field in (
        "episode_start_time",
        "ed_start_time",
        "ed_end_time",
        "clinical_end_time",
        "administrative_end_time",
    ):
        if field not in episode:
            raise SchemaValidationError(f"episode.{field} is absent")

    initial = record["vitals"].get("initial")
    if not isinstance(initial, dict) or "pain" not in initial:
        raise SchemaValidationError("vitals.initial.pain is absent")

    if "triage_chief_complaint" not in record["presentation"]:
        raise SchemaValidationError("triage chief complaint is absent")
    retrospective = record["presentation"].get("discharge_summary_retrospective")
    if not isinstance(retrospective, dict):
        raise SchemaValidationError("retrospective discharge summary is absent")
    if retrospective.get("evidence_phase") != "post_hoc":
        raise SchemaValidationError("discharge summary must be marked post_hoc")

    _validate_timed_collections(record)
    _validate_post_hoc_markers(record)


def _validate_timed_collections(record: dict[str, Any]) -> None:
    paths = (
        ("orders", "provider_orders"),
        ("investigations", "microbiology"),
        ("investigations", "radiology"),
        ("treatments", "medications"),
        ("treatments", "pharmacy_orders"),
        ("treatments", "medication_administrations"),
        ("care_path", "transfers"),
        ("care_path", "services"),
    )
    for parent, child in paths:
        values = record[parent].get(child)
        if not isinstance(values, list):
            raise SchemaValidationError(f"{parent}.{child} must be a list")
        for index, item in enumerate(values):
            if not isinstance(item, dict):
                raise SchemaValidationError(f"{parent}.{child}[{index}] must be an object")
            missing = [field for field in TIME_FIELDS if field not in item]
            if missing:
                raise SchemaValidationError(
                    f"{parent}.{child}[{index}] missing time fields: {missing}"
                )
    for panel_index, panel in enumerate(record["investigations"].get("laboratory", [])):
        for result_index, item in enumerate(panel.get("results", [])):
            missing = [field for field in TIME_FIELDS if field not in item]
            if missing:
                raise SchemaValidationError(
                    "investigations.laboratory"
                    f"[{panel_index}].results[{result_index}] missing time fields: {missing}"
                )


def _validate_post_hoc_markers(record: dict[str, Any]) -> None:
    for item in record["diagnoses"].get("coded_diagnoses", []):
        if item.get("evidence_phase") != "post_hoc":
            raise SchemaValidationError("coded diagnosis is not marked post_hoc")
    drg = record["discharge"].get("drg")
    if drg is not None and drg.get("evidence_phase") != "post_hoc":
        raise SchemaValidationError("DRG is not marked post_hoc")
