from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.text_ner.annotation_contracts import SECTION_ANNOTATION_SCHEMA_VERSION
from data_pipeline.text_ner.event_output_manifest import prepare_event_output_text_manifest
from data_pipeline.text_ner.model_interface import (
    MODEL_ADAPTER_PROTOCOL_VERSION,
    MODEL_REQUEST_SCHEMA_VERSION,
)
from data_pipeline.text_ner.openai_compatible_api import (
    GenericApiError,
    OpenAICompatibleSettings,
    run_api_batch,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CATALOG = REPOSITORY_ROOT / "config" / "text_ner" / "all-free-text-sources.json"
API_CONFIG = REPOSITORY_ROOT / "config" / "text_ner" / "openai-compatible-api.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _event_output(root: Path) -> Path:
    source = root / "readable.jsonl"
    admission = {
        "schema": {"name": "mimic_admission_clinical_readable", "version": "1.0.0"},
        "source_schema": {"name": "mimic_admission_raw", "version": "1.0.0"},
        "subject_id": "1",
        "hadm_id": "10",
        "mimic_iv_hosp": {
            "labevents": [
                {
                    "labevent_id": "100",
                    "subject_id": "1",
                    "hadm_id": "10",
                    "charttime": "2100-01-01 01:00:00",
                    "storetime": "2100-01-01 01:05:00",
                    "comments": "Specimen slightly hemolyzed.",
                }
            ],
            "microbiologyevents": [
                {
                    "microevent_id": "200",
                    "subject_id": "1",
                    "hadm_id": "10",
                    "charttime": "2100-01-01 02:00:00",
                    "storetime": "2100-01-01 02:05:00",
                    "comments": "Mixed flora present.",
                }
            ],
            "prescriptions": [{"drug": "structured medication name"}],
        },
        "mimic_iv_icu": {},
        "mimic_iv_ed": {
            "triage": [
                {
                    "subject_id": "1",
                    "stay_id": "20",
                    "chiefcomplaint": "Chest pain",
                }
            ]
        },
        "mimic_iv_note": {
            "radiology": [
                {
                    "note_id": "R1",
                    "subject_id": "1",
                    "hadm_id": "10",
                    "note_type": "RR",
                    "charttime": "2100-01-01 03:00:00",
                    "storetime": "2100-01-01 03:10:00",
                    "text": "FINDINGS: No edema.",
                }
            ],
            "discharge": [
                {
                    "note_id": "D1",
                    "subject_id": "1",
                    "hadm_id": "10",
                    "note_type": "DS",
                    "charttime": "2100-01-02 03:00:00",
                    "storetime": "2100-01-02 03:10:00",
                    "text": "Hospital course was uncomplicated.",
                }
            ],
        },
    }
    source.write_text(json.dumps(admission) + "\n", encoding="utf-8")
    output = root / "event_pipeline_output"
    (output / "normalization").mkdir(parents=True)
    normalized = output / "normalization" / "normalized_events.parquet"
    sources = [
        ("event:lab", "mimic_iv_hosp", "hosp.labevents", 0, "mapped"),
        ("event:micro", "mimic_iv_hosp", "hosp.microbiologyevents", 0, "mapped"),
        ("event:triage", "mimic_iv_ed", "ed.triage", 0, "unresolved"),
        ("event:rad", "mimic_iv_note", "note.radiology", 0, "unresolved"),
        ("event:discharge", "mimic_iv_note", "note.discharge", 0, "mapped"),
    ]
    rows = [
        {
            "event_id": event_id,
            "normalization_status": status,
            "concept_id": None,
            "preferred_name": None,
            "source_module": module,
            "source_table": table,
            "source_array_index": index,
            "jsonl_line_number": 1,
        }
        for event_id, module, table, index, status in sources
    ]
    pq.write_table(pa.Table.from_pylist(rows), normalized)
    workflow = {
        "run_id": "workflow:test",
        "acceptance": {"can_start_text_ner": True},
        "inputs": {
            "source_jsonl": source.name,
            "source_jsonl_sha256": _sha256_file(source),
        },
        "stages": {
            "cleaning": {"counts": {"admissions": 1}},
            "normalization": {"counts": {"events": 5}},
        },
    }
    (output / "workflow_manifest.json").write_text(
        json.dumps(workflow), encoding="utf-8"
    )
    return output


def _api_request(text: str, prompt: str) -> dict[str, object]:
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return {
        "schema_version": MODEL_REQUEST_SCHEMA_VERSION,
        "interface_protocol_version": MODEL_ADAPTER_PROTOCOL_VERSION,
        "request_id": "request:1",
        "stage_id": "mentions",
        "candidate_status": "pending_model_execution",
        "annotation_unit_id": "unit:1",
        "manifest_row_id": "manifest:1",
        "document_id": "document:1",
        "section_id": "section:1",
        "source_table": "ed.triage",
        "section_name": "chief_complaint",
        "section_text": text,
        "section_text_sha256": text_hash,
        "prompt_sha256": prompt_hash,
        "response_schema_version": SECTION_ANNOTATION_SCHEMA_VERSION,
    }


class EventOutputTextManifestTests(unittest.TestCase):
    def test_all_configured_free_text_includes_hosp_and_discharge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event_output = _event_output(root)
            result = prepare_event_output_text_manifest(
                event_output, SOURCE_CATALOG, event_output / "NER" / "input"
            )
            counts = result["counts"]
            self.assertEqual(counts["admissions"], 1)
            self.assertEqual(counts["documents"], 5)
            self.assertEqual(counts["text_units"], 5)
            self.assertIn("hosp.labevents", counts["source_document_counts"])
            self.assertIn("hosp.microbiologyevents", counts["source_document_counts"])
            self.assertIn("note.discharge", counts["source_document_counts"])
            self.assertNotIn("hosp.prescriptions", counts["source_document_counts"])
            manifest = pq.read_table(
                event_output / "NER" / "input" / "text_ner_input_manifest.parquet"
            ).to_pylist()
            discharge = next(row for row in manifest if row["source_table"] == "note.discharge")
            self.assertEqual(discharge["inclusion_status"], "included")
            self.assertEqual(discharge["evidence_phase"], "post_hoc")
            self.assertEqual(counts["text_units_without_direct_event_link"], 0)


class GenericApiBatchTests(unittest.TestCase):
    def test_gates_prevent_transport_before_explicit_authorization(self) -> None:
        calls: list[object] = []

        def transport(*args: object) -> dict[str, object]:
            calls.append(args)
            raise AssertionError("transport must not be called")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prompt = root / "prompt.md"
            prompt.write_text("Return JSON.", encoding="utf-8")
            request_path = root / "requests.jsonl"
            request_path.write_text(
                json.dumps(_api_request("Chest pain", "Return JSON.")) + "\n",
                encoding="utf-8",
            )
            common = (request_path, prompt, root / "responses.jsonl", root / "audit.jsonl", API_CONFIG)
            with self.assertRaisesRegex(GenericApiError, "MODEL_EXECUTION_NOT_AUTHORIZED"):
                run_api_batch(*common, transport=transport)
            with self.assertRaisesRegex(GenericApiError, "EXTERNAL_DATA_TRANSFER_NOT_AUTHORIZED"):
                run_api_batch(*common, execute=True, transport=transport)
            self.assertEqual(calls, [])

    def test_mock_transport_is_validated_persisted_and_resumable(self) -> None:
        calls: list[object] = []
        text = "Chest pain"
        prompt_text = "Return JSON."
        request = _api_request(text, prompt_text)
        annotation = {
            "schema_version": SECTION_ANNOTATION_SCHEMA_VERSION,
            "manifest_row_id": "manifest:1",
            "document_id": "document:1",
            "section_id": "section:1",
            "section_text_sha256": request["section_text_sha256"],
            "mentions": [],
            "relations": [],
        }

        def transport(
            settings: OpenAICompatibleSettings,
            endpoint: str,
            payload: dict[str, object],
            timeout: int,
        ) -> dict[str, object]:
            calls.append((settings, endpoint, payload, timeout))
            return {
                "id": "mock:1",
                "choices": [{"message": {"content": json.dumps(annotation)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
            }

        environment = {
            "TEXT_NER_API_KEY": "test-secret",
            "TEXT_NER_BASE_URL": "http://127.0.0.1:9999/v1",
            "TEXT_NER_MODEL": "test-model",
            "TEXT_NER_MODEL_VERSION": "test-revision",
            "TEXT_NER_PROVIDER": "test-provider",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prompt = root / "prompt.md"
            prompt.write_text(prompt_text, encoding="utf-8")
            requests = root / "requests.jsonl"
            requests.write_text(json.dumps(request) + "\n", encoding="utf-8")
            responses = root / "responses.jsonl"
            audit = root / "audit.jsonl"
            first = run_api_batch(
                requests,
                prompt,
                responses,
                audit,
                API_CONFIG,
                execute=True,
                endpoint_scope="local",
                environ=environment,
                transport=transport,
                sleep=lambda _: None,
            )
            second = run_api_batch(
                requests,
                prompt,
                responses,
                audit,
                API_CONFIG,
                execute=True,
                endpoint_scope="local",
                environ=environment,
                transport=transport,
                sleep=lambda _: None,
            )
            self.assertEqual(first["model_calls_this_run"], 1)
            self.assertEqual(second["model_calls_this_run"], 0)
            self.assertEqual(len(calls), 1)
            self.assertNotIn("test-secret", repr(calls[0][0]))
            self.assertNotIn("test-secret", audit.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
