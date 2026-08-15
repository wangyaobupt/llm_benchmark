"""Model-neutral interfaces for two-stage entity and relation extraction.

This module deliberately contains no model client and performs no I/O.  A future
adapter can implement :class:`TextNerModelAdapter` without changing the request,
response, validation, or sidecar contracts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from jsonschema import Draft202012Validator


MODEL_REQUEST_SCHEMA_VERSION = "text-ner-model-request/1.0.0"
MODEL_RESPONSE_SCHEMA_VERSION = "text-ner-model-response/1.0.0"
MODEL_ADAPTER_PROTOCOL_VERSION = "text-ner-model-adapter/1.0.0"
MODEL_REQUEST_SCHEMA_PATH = (
    Path(__file__).resolve().parent / "schemas" / "model-request.schema.json"
)
_MODEL_REQUEST_SCHEMA = json.loads(
    MODEL_REQUEST_SCHEMA_PATH.read_text(encoding="utf-8")
)
Draft202012Validator.check_schema(_MODEL_REQUEST_SCHEMA)
_MODEL_REQUEST_VALIDATOR = Draft202012Validator(_MODEL_REQUEST_SCHEMA)


class ModelInterfaceError(ValueError):
    """A fail-closed model interface or response-envelope error."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


@runtime_checkable
class TextNerModelAdapter(Protocol):
    """The only contract a future local or remote model binding must implement."""

    @property
    def provider(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def model_version(self) -> str: ...

    def generate(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return one ``text-ner-model-response/1.0.0`` response envelope."""
        ...


def validate_model_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a pending or dependency-resolved request against the public schema."""

    errors = sorted(
        _MODEL_REQUEST_VALIDATOR.iter_errors(dict(request)),
        key=lambda error: list(error.path),
    )
    if errors:
        error = errors[0]
        path = ".".join(str(part) for part in error.path) or "<root>"
        raise ModelInterfaceError("MODEL_REQUEST_SCHEMA_INVALID", f"{path}: {error.message}")
    return dict(request)


def validate_response_envelope(
    response: Mapping[str, Any],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate transport-level lineage before clinical annotation validation."""

    required = {
        "schema_version",
        "request_id",
        "stage_id",
        "provider",
        "model_name",
        "model_version",
        "annotation",
    }
    missing = sorted(required - set(response))
    if missing:
        raise ModelInterfaceError("MODEL_RESPONSE_FIELD_MISSING", ",".join(missing))
    unknown = sorted(set(response) - required)
    if unknown:
        raise ModelInterfaceError("MODEL_RESPONSE_FIELD_UNKNOWN", ",".join(unknown))
    if response["schema_version"] != MODEL_RESPONSE_SCHEMA_VERSION:
        raise ModelInterfaceError(
            "MODEL_RESPONSE_SCHEMA_VERSION_MISMATCH",
            str(response["schema_version"]),
        )
    for field in ("request_id", "stage_id"):
        if response[field] != request[field]:
            raise ModelInterfaceError("MODEL_RESPONSE_LINEAGE_MISMATCH", field)
    for field in ("provider", "model_name", "model_version"):
        if not isinstance(response[field], str) or not response[field].strip():
            raise ModelInterfaceError("MODEL_RESPONSE_PROVENANCE_INVALID", field)
    if not isinstance(response["annotation"], dict):
        raise ModelInterfaceError("MODEL_RESPONSE_ANNOTATION_INVALID", "not an object")
    return dict(response)
