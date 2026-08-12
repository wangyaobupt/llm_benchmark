"""Structural, semantic, provenance, and POE cross-check gates."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .schemas import EVENT_JSON_SCHEMA_PATH
from .source_registry import REGISTERED_SOURCE_PATHS, REQUIRED_SOURCE_PATHS


ACCEPTED_INPUT_SCHEMAS = {
    ("mimic_admission_raw", "1.0.0"),
    ("mimic_admission_clinical_readable", "1.0.0"),
}


class EventPipelineError(ValueError):
    """Raised when a run cannot satisfy the frozen pipeline contract."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


class EventValidator:
    def __init__(self, schema_path: Path = EVENT_JSON_SCHEMA_PATH):
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self._validator = Draft202012Validator(schema)

    def validate(self, event: dict[str, Any], known_source_row_ids: set[str]) -> None:
        errors = sorted(self._validator.iter_errors(event), key=lambda error: list(error.path))
        if errors:
            error = errors[0]
            path = ".".join(str(part) for part in error.path) or "<root>"
            raise EventPipelineError(
                "EVENT_SCHEMA_INVALID", f"{path}: {error.message}"
            )
        if event["source_row_id"] not in known_source_row_ids:
            raise EventPipelineError(
                "SOURCE_ROW_NOT_FOUND", event["source_row_id"]
            )
        missing_support = set(event["supporting_source_row_ids"]) - known_source_row_ids
        if missing_support:
            raise EventPipelineError(
                "SUPPORTING_SOURCE_ROW_NOT_FOUND", sorted(missing_support)[0]
            )
        if len(event["supporting_source_row_ids"]) != len(
            event["supporting_raw_row_refs"]
        ):
            raise EventPipelineError(
                "SUPPORTING_LINEAGE_LENGTH_MISMATCH", event["event_id"]
            )
        if event["normalization_status"] == "mapped" and not event["concept_id"]:
            raise EventPipelineError(
                "MAPPED_CONCEPT_ID_MISSING", event["event_id"]
            )
        if (
            event["event_kind"] == "laboratory_resulted"
            and not event["source_concept_id"]
            and not event["concept_id"]
        ):
            raise EventPipelineError(
                "LABORATORY_CONCEPT_MISSING", event["event_id"]
            )
        event_time = _parsed_time(event["event_time"])
        available_time = _parsed_time(event["available_time"])
        result_kinds = {
            "laboratory_resulted",
            "microbiology_resulted",
            "imaging_reported",
            "output_measured",
            "procedure_performed",
        }
        if (
            event["event_kind"] in result_kinds
            and event_time
            and available_time
            and available_time < event_time
        ):
            raise EventPipelineError(
                "AVAILABLE_BEFORE_EVENT_TIME", event["event_id"]
            )


def _parsed_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def validate_admission_shell(admission: Any, line_number: int) -> None:
    if not isinstance(admission, dict):
        raise EventPipelineError("ADMISSION_NOT_OBJECT", f"line {line_number}")
    schema = admission.get("schema")
    identity = (
        schema.get("name") if isinstance(schema, dict) else None,
        schema.get("version") if isinstance(schema, dict) else None,
    )
    if identity not in ACCEPTED_INPUT_SCHEMAS:
        raise EventPipelineError(
            "INPUT_SCHEMA_UNSUPPORTED", f"line {line_number}: {schema!r}"
        )
    for field in ("subject_id", "hadm_id"):
        if admission.get(field) in (None, ""):
            raise EventPipelineError(
                "ADMISSION_ID_MISSING", f"line {line_number}: {field}"
            )
    modules = ("mimic_iv_hosp", "mimic_iv_icu", "mimic_iv_ed", "mimic_iv_note")
    for module in modules:
        if not isinstance(admission.get(module), dict):
            raise EventPipelineError(
                "SOURCE_MODULE_INVALID", f"line {line_number}: {module}"
            )
    observed_paths = {
        (module, table)
        for module in modules
        for table in admission[module]
    }
    unexpected = sorted(observed_paths - REGISTERED_SOURCE_PATHS)
    if unexpected:
        module, table = unexpected[0]
        raise EventPipelineError(
            "UNREGISTERED_SOURCE_TABLE",
            f"line {line_number}: {module}.{table}",
        )
    missing = sorted(REQUIRED_SOURCE_PATHS - observed_paths)
    if missing:
        module, table = missing[0]
        raise EventPipelineError(
            "REQUIRED_SOURCE_TABLE_MISSING",
            f"line {line_number}: {module}.{table}",
        )
    for module, table in sorted(observed_paths):
        if not isinstance(admission[module][table], list):
            raise EventPipelineError(
                "SOURCE_TABLE_NOT_ARRAY",
                f"line {line_number}: {module}.{table}",
            )


def crosscheck_poe_timeline(admission: dict[str, Any], line_number: int) -> int:
    hosp = admission["mimic_iv_hosp"]
    orders = hosp.get("poe", [])
    timeline = hosp.get("poe_timeline", [])
    if not timeline:
        if orders:
            raise EventPipelineError(
                "POE_TIMELINE_COUNT_MISMATCH",
                f"line {line_number}: poe={len(orders)}, poe_timeline=0",
            )
        return 0
    if len(orders) != len(timeline):
        raise EventPipelineError(
            "POE_TIMELINE_COUNT_MISMATCH",
            f"line {line_number}: poe={len(orders)}, poe_timeline={len(timeline)}",
        )
    by_id = {str(item.get("poe_id")): item for item in timeline}
    action_map = {"New": "create", "Change": "change", "D/C": "discontinue"}
    for order in orders:
        poe_id = str(order.get("poe_id"))
        derived = by_id.get(poe_id)
        if derived is None:
            raise EventPipelineError(
                "POE_TIMELINE_ID_MISSING", f"line {line_number}: {poe_id}"
            )
        expected_action = action_map.get(order.get("transaction_type"), "uninterpreted")
        if derived.get("action") != expected_action:
            raise EventPipelineError(
                "POE_TIMELINE_ACTION_MISMATCH", f"line {line_number}: {poe_id}"
            )
        raw_time = order.get("ordertime")
        derived_time = derived.get("event_time")
        if raw_time != derived_time:
            raise EventPipelineError(
                "POE_TIMELINE_TIME_MISMATCH", f"line {line_number}: {poe_id}"
            )
    return len(timeline)
