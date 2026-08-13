"""Frozen contracts for exploratory text NER method runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


METHOD_CONFIG_SCHEMA_VERSION = "text-ner-method-config/1.0.0"
METHOD_RUN_SCHEMA_VERSION = "text-ner-method-run/1.0.0"
METHOD_REQUEST_SCHEMA_VERSION = "text-ner-method-request/1.0.0"
METHOD_CONFIG_SCHEMA_PATH = (
    Path(__file__).resolve().parent / "schemas" / "ner-method-config.schema.json"
)
METHOD_RUN_SCHEMA_PATH = (
    Path(__file__).resolve().parent / "schemas" / "ner-method-run.schema.json"
)


class MethodContractError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


def _validator(schema_path: Path) -> Draft202012Validator:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_method_config(value: dict[str, Any]) -> None:
    _validate(value, _validator(METHOD_CONFIG_SCHEMA_PATH), "METHOD_CONFIG_INVALID")


def validate_method_run(value: dict[str, Any]) -> None:
    _validate(value, _validator(METHOD_RUN_SCHEMA_PATH), "METHOD_RUN_INVALID")


def _validate(
    value: dict[str, Any], validator: Draft202012Validator, reason_code: str
) -> None:
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
    if not errors:
        return
    error = errors[0]
    path = ".".join(str(part) for part in error.path) or "<root>"
    raise MethodContractError(reason_code, f"{path}: {error.message}")
