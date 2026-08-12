"""Fail-closed validation for section-level annotation candidates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .annotation_contracts import SECTION_ANNOTATION_SCHEMA_VERSION


ANNOTATION_SCHEMA_PATH = (
    Path(__file__).resolve().parent / "schemas" / "section-annotation.schema.json"
)


class AnnotationValidationError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


class SectionAnnotationValidator:
    def __init__(self, schema_path: Path = ANNOTATION_SCHEMA_PATH):
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self._validator = Draft202012Validator(schema)

    def validate(
        self,
        annotation: dict[str, Any],
        manifest_row: dict[str, Any],
        section_text: str,
    ) -> None:
        errors = sorted(
            self._validator.iter_errors(annotation), key=lambda error: list(error.path)
        )
        if errors:
            error = errors[0]
            path = ".".join(str(part) for part in error.path) or "<root>"
            raise AnnotationValidationError(
                "ANNOTATION_SCHEMA_INVALID", f"{path}: {error.message}"
            )
        if annotation["schema_version"] != SECTION_ANNOTATION_SCHEMA_VERSION:
            raise AnnotationValidationError(
                "ANNOTATION_SCHEMA_VERSION_MISMATCH", annotation["schema_version"]
            )
        for field in ("manifest_row_id", "document_id", "section_id"):
            if annotation[field] != manifest_row[field]:
                raise AnnotationValidationError(
                    "ANNOTATION_LINEAGE_MISMATCH", field
                )
        if annotation["section_text_sha256"] != manifest_row["span_sha256"]:
            raise AnnotationValidationError(
                "ANNOTATION_INPUT_HASH_MISMATCH", annotation["manifest_row_id"]
            )
        observed_text_sha256 = hashlib.sha256(section_text.encode("utf-8")).hexdigest()
        if observed_text_sha256 != annotation["section_text_sha256"]:
            raise AnnotationValidationError(
                "ANNOTATION_SECTION_TEXT_MISMATCH", annotation["manifest_row_id"]
            )

        mention_by_id: dict[str, dict[str, Any]] = {}
        exact_mentions: set[tuple[int, int, str]] = set()
        for mention in annotation["mentions"]:
            local_id = mention["local_id"]
            if local_id in mention_by_id:
                raise AnnotationValidationError("DUPLICATE_MENTION_ID", local_id)
            start = mention["section_span_start"]
            end = mention["section_span_end"]
            if end <= start or end > len(section_text):
                raise AnnotationValidationError("MENTION_SPAN_INVALID", local_id)
            if section_text[start:end] != mention["surface_text"]:
                raise AnnotationValidationError("MENTION_SURFACE_MISMATCH", local_id)
            exact_key = (start, end, mention["entity_type"])
            if exact_key in exact_mentions:
                raise AnnotationValidationError("DUPLICATE_MENTION", local_id)
            exact_mentions.add(exact_key)
            mention_by_id[local_id] = mention

        relation_ids: set[str] = set()
        relation_keys: set[tuple[str, str, str]] = set()
        for relation in annotation["relations"]:
            relation_id = relation["local_id"]
            if relation_id in relation_ids:
                raise AnnotationValidationError("DUPLICATE_RELATION_ID", relation_id)
            relation_ids.add(relation_id)
            source = mention_by_id.get(relation["source_mention_id"])
            target = mention_by_id.get(relation["target_mention_id"])
            if source is None or target is None:
                raise AnnotationValidationError(
                    "RELATION_MENTION_NOT_FOUND", relation_id
                )
            if relation["source_mention_id"] == relation["target_mention_id"]:
                raise AnnotationValidationError("RELATION_SELF_REFERENCE", relation_id)
            relation_key = (
                relation["source_mention_id"],
                relation["relation_type"],
                relation["target_mention_id"],
            )
            if relation_key in relation_keys:
                raise AnnotationValidationError("DUPLICATE_RELATION", relation_id)
            relation_keys.add(relation_key)
            start = relation["section_evidence_start"]
            end = relation["section_evidence_end"]
            if end <= start or end > len(section_text):
                raise AnnotationValidationError("RELATION_EVIDENCE_INVALID", relation_id)
            if section_text[start:end] != relation["evidence_text"]:
                raise AnnotationValidationError(
                    "RELATION_EVIDENCE_MISMATCH", relation_id
                )
            mention_start = min(
                source["section_span_start"], target["section_span_start"]
            )
            mention_end = max(source["section_span_end"], target["section_span_end"])
            if start > mention_start or end < mention_end:
                raise AnnotationValidationError(
                    "RELATION_EVIDENCE_DOES_NOT_COVER_MENTIONS", relation_id
                )
