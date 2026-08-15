from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.text_ner.annotation_contracts import SECTION_ANNOTATION_SCHEMA_VERSION
from data_pipeline.text_ner.contracts import MANIFEST_ARROW_SCHEMA, MANIFEST_SCHEMA_VERSION
from data_pipeline.text_ner.full_extraction import (
    compile_model_responses,
    prepare_full_extraction_package,
)
from data_pipeline.text_ner.model_interface import (
    MODEL_RESPONSE_SCHEMA_VERSION,
    ModelInterfaceError,
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _manifest_row(
    suffix: str,
    *,
    source_module: str,
    source_table: str,
    source_array_index: int,
    text: str,
    included: bool,
) -> dict[str, object]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_row_id": f"manifest:{suffix}",
        "document_id": f"document:{suffix}",
        "section_id": f"section:{suffix}",
        "subject_id": f"subject:{suffix}",
        "hadm_id": f"hadm:{suffix}",
        "split_group_id": f"subject:{suffix}",
        "source_module": source_module,
        "source_table": source_table,
        "source_row_id": f"row:{suffix}",
        "source_array_index": source_array_index,
        "jsonl_line_number": 1,
        "raw_row_ref": f"line:1:{source_table}:{source_array_index}",
        "text_field": "chiefcomplaint" if source_table == "ed.triage" else "text",
        "note_id": f"note:{suffix}",
        "note_type": source_table.split(".")[1],
        "parent_note_id": "",
        "addendum_note_ids": [],
        "event_time": "2100-01-01 00:00:00",
        "source_available_time": "2100-01-01 00:00:00",
        "available_time": "2100-01-01 00:00:00",
        "recorded_time": "",
        "time_resolution_status": "resolved",
        "time_policy_id": "test",
        "time_resolution_reasons": [],
        "evidence_phase": "presentation",
        "quality_flags": [],
        "section_name": "chief_complaint" if source_table == "ed.triage" else "findings",
        "section_ordinal": 0,
        "span_start": 0,
        "span_end": len(text),
        "source_text_character_count": len(text),
        "span_character_count": len(text),
        "source_text_sha256": _sha256(text),
        "span_sha256": _sha256(text),
        "inclusion_status": "included" if included else "excluded",
        "reason_code": "TEST_INCLUDED" if included else "POST_HOC_DISCHARGE",
        "pilot_document_selected": False,
        "pilot_selection_rank": 0,
        "pilot_stratum": "test",
    }


def _fixture(root: Path) -> tuple[Path, Path, Path, Path]:
    ed_text = "Chest pain"
    radiology_text = "FINDINGS: Tube tip is 3 cm above carina."
    raw = {
        "mimic_iv_ed": {"triage": [{"chiefcomplaint": ed_text}]},
        "mimic_iv_note": {
            "radiology": [{"text": radiology_text}],
            "discharge": [{"text": "Post-hoc diagnosis"}],
        },
    }
    raw_path = root / "raw.jsonl"
    raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
    rows = [
        _manifest_row(
            "ed",
            source_module="mimic_iv_ed",
            source_table="ed.triage",
            source_array_index=0,
            text=ed_text,
            included=True,
        ),
        _manifest_row(
            "rad",
            source_module="mimic_iv_note",
            source_table="note.radiology",
            source_array_index=0,
            text=radiology_text,
            included=True,
        ),
        _manifest_row(
            "discharge",
            source_module="mimic_iv_note",
            source_table="note.discharge",
            source_array_index=0,
            text="Post-hoc diagnosis",
            included=False,
        ),
    ]
    manifest_path = root / "manifest.parquet"
    pq.write_table(pa.Table.from_pylist(rows, schema=MANIFEST_ARROW_SCHEMA), manifest_path)
    mention_prompt = root / "mentions.md"
    relation_prompt = root / "relations.md"
    mention_prompt.write_text("Return entity mentions as JSON.", encoding="utf-8")
    relation_prompt.write_text("Return explicit relations as JSON.", encoding="utf-8")
    return raw_path, manifest_path, mention_prompt, relation_prompt


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _mention(local_id: str, surface: str, start: int, entity_type: str) -> dict[str, object]:
    return {
        "local_id": local_id,
        "surface_text": surface,
        "section_span_start": start,
        "section_span_end": start + len(surface),
        "entity_type": entity_type,
        "assertion": "present",
        "temporality": "current",
        "experiencer": "patient",
        "laterality": "not_applicable",
        "severity": "not_applicable",
        "trend": "not_applicable",
        "normalization_status": "unattempted",
        "concept_id": None,
        "preferred_name": None,
        "terminology": None,
        "quality_flags": [],
    }


def _response(request: dict[str, object], mentions: list[dict[str, object]], relations: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": MODEL_RESPONSE_SCHEMA_VERSION,
        "request_id": request["request_id"],
        "stage_id": request["stage_id"],
        "provider": "synthetic-test",
        "model_name": "contract-fixture",
        "model_version": "1",
        "annotation": {
            "schema_version": SECTION_ANNOTATION_SCHEMA_VERSION,
            "manifest_row_id": request["manifest_row_id"],
            "document_id": request["document_id"],
            "section_id": request["section_id"],
            "section_text_sha256": request["section_text_sha256"],
            "mentions": mentions,
            "relations": relations,
        },
    }


class FullExtractionInterfaceTests(unittest.TestCase):
    def test_prepare_full_scope_is_deterministic_and_model_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw, manifest, mention_prompt, relation_prompt = _fixture(root)
            first = prepare_full_extraction_package(
                raw,
                manifest,
                root / "first",
                mention_prompt_path=mention_prompt,
                relation_prompt_path=relation_prompt,
            )
            second = prepare_full_extraction_package(
                raw,
                manifest,
                root / "second",
                mention_prompt_path=mention_prompt,
                relation_prompt_path=relation_prompt,
            )
            self.assertEqual(first["run_id"], second["run_id"])
            self.assertEqual(first["outputs"], second["outputs"])
            self.assertEqual(first["execution"], {"mode": "request_only", "model_calls": 0})
            self.assertEqual(first["input"]["text_units"], 2)
            self.assertEqual(
                first["input"]["source_counts"], {"ed.triage": 1, "note.radiology": 1}
            )
            requests = _read_jsonl(root / "first" / "requests" / "mention_requests.jsonl")
            self.assertEqual(len(requests), 2)
            self.assertNotIn("note.discharge", {request["source_table"] for request in requests})

    def test_empty_responses_compile_typed_pending_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw, manifest, mention_prompt, relation_prompt = _fixture(root)
            package = root / "package"
            prepare_full_extraction_package(
                raw,
                manifest,
                package,
                mention_prompt_path=mention_prompt,
                relation_prompt_path=relation_prompt,
            )
            empty_mentions = root / "mention-responses.jsonl"
            empty_relations = root / "relation-responses.jsonl"
            empty_mentions.write_text("", encoding="utf-8")
            empty_relations.write_text("", encoding="utf-8")
            result = compile_model_responses(
                package, manifest, empty_mentions, empty_relations, root / "compiled"
            )
            self.assertEqual(result["compile_status"], "pending_model_execution")
            self.assertEqual(result["model_calls_performed_by_compiler"], 0)
            entities = pq.read_table(root / "compiled" / "sidecars" / "entity_mentions.parquet")
            relations = pq.read_table(root / "compiled" / "sidecars" / "text_relations.parquet")
            self.assertEqual(entities.num_rows, 0)
            self.assertEqual(relations.num_rows, 0)
            self.assertEqual(entities.schema.metadata, ENTITY_METADATA)
            self.assertEqual(relations.schema.metadata, RELATION_METADATA)

    def test_valid_two_stage_responses_compile_entities_and_relation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw, manifest, mention_prompt, relation_prompt = _fixture(root)
            package = root / "package"
            prepare_full_extraction_package(
                raw,
                manifest,
                package,
                mention_prompt_path=mention_prompt,
                relation_prompt_path=relation_prompt,
            )
            mention_requests = _read_jsonl(package / "requests" / "mention_requests.jsonl")
            mention_request = next(row for row in mention_requests if row["source_table"] == "note.radiology")
            text = str(mention_request["section_text"])
            mentions = [
                _mention("m1", "Tube tip", text.index("Tube tip"), "device"),
                _mention("m2", "carina", text.index("carina"), "anatomical_site"),
            ]
            mention_response = _response(mention_request, mentions, [])
            mention_responses = root / "mention-responses.jsonl"
            mention_responses.write_text(json.dumps(mention_response) + "\n", encoding="utf-8")
            pending = _read_jsonl(package / "requests" / "relation_requests.pending.jsonl")
            relation_request = next(row for row in pending if row["manifest_row_id"] == "manifest:rad")
            relation_request["section_text"] = text
            relation_request["validated_mentions"] = mentions
            evidence = "Tube tip is 3 cm above carina"
            relation_response = _response(
                relation_request,
                mentions,
                [
                    {
                        "local_id": "r1",
                        "source_mention_id": "m1",
                        "target_mention_id": "m2",
                        "relation_type": "device_positioned_at",
                        "evidence_text": evidence,
                        "section_evidence_start": text.index(evidence),
                        "section_evidence_end": text.index(evidence) + len(evidence),
                        "relation_basis": "text_explicit",
                        "quality_flags": [],
                    }
                ],
            )
            relation_responses = root / "relation-responses.jsonl"
            relation_responses.write_text(json.dumps(relation_response) + "\n", encoding="utf-8")
            result = compile_model_responses(
                package, manifest, mention_responses, relation_responses, root / "compiled"
            )
            self.assertEqual(result["mention_responses_validated"], 1)
            self.assertEqual(result["relation_responses_validated"], 1)
            self.assertEqual(result["entity_mentions"], 2)
            self.assertEqual(result["text_relations"], 1)

    def test_relation_response_without_validated_mentions_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw, manifest, mention_prompt, relation_prompt = _fixture(root)
            package = root / "package"
            prepare_full_extraction_package(
                raw,
                manifest,
                package,
                mention_prompt_path=mention_prompt,
                relation_prompt_path=relation_prompt,
            )
            empty_mentions = root / "mention-responses.jsonl"
            empty_mentions.write_text("", encoding="utf-8")
            pending = _read_jsonl(package / "requests" / "relation_requests.pending.jsonl")[0]
            pending["section_text"] = "Chest pain"
            response = _response(pending, [], [])
            relation_responses = root / "relation-responses.jsonl"
            relation_responses.write_text(json.dumps(response) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ModelInterfaceError, "RELATION_RESPONSE_BEFORE_VALIDATED_MENTIONS"):
                compile_model_responses(
                    package, manifest, empty_mentions, relation_responses, root / "compiled"
                )


ENTITY_METADATA = {b"schema": b"entity-mention/1.0.0"}
RELATION_METADATA = {b"schema": b"text-relation/1.0.0"}


if __name__ == "__main__":
    unittest.main()
