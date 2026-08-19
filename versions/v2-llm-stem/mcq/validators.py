"""Load and expose the strict versioned JSON-schema validators (no extra fields)."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


def _load(name: str) -> Draft202012Validator:
    path = _SCHEMA_DIR / name
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


RULE_VALIDATOR = _load("investigation-rule.schema.json")
QUESTION_VALIDATOR = _load("investigation-question.schema.json")
STEM_RESPONSE_VALIDATOR = _load("stem-response.schema.json")
REVIEW_RESPONSE_VALIDATOR = _load("review-response.schema.json")
HUMAN_DECISION_VALIDATOR = _load("human-review-decision.schema.json")
MANIFEST_VALIDATOR = _load("run-manifest.schema.json")


class SchemaValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def validate_strict(validator: Draft202012Validator, obj: dict) -> dict:
    """Validate an object against a strict schema; raise SchemaValidationError."""
    errors = sorted(
        validator.iter_errors(obj),
        key=lambda e: list(e.path),
    )
    if errors:
        messages = []
        for e in errors[:10]:
            path = ".".join(str(p) for p in e.path) or "<root>"
            messages.append(f"{path}: {e.message}")
        raise SchemaValidationError(messages)
    return dict(obj)
