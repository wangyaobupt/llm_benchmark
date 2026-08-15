from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.text_ner.annotation_contracts import SECTION_ANNOTATION_SCHEMA_VERSION
from data_pipeline.text_ner.aggregation_manifest import (
    AggregationTextManifestError,
    prepare_aggregation_text_manifest,
)
from data_pipeline.text_ner.model_interface import (
    MODEL_ADAPTER_PROTOCOL_VERSION,
    MODEL_REQUEST_SCHEMA_VERSION,
)
from data_pipeline.text_ner.openai_compatible_api import (
    GenericApiError,
    OpenAICompatibleSettings,
    load_api_config,
    load_environment_file,
    resolve_environment,
    run_api_batch,
)
from data_pipeline.text_ner.span_grounding import ground_annotation_spans


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CATALOG = REPOSITORY_ROOT / "config" / "text_ner" / "all-free-text-sources.json"
API_CONFIG = REPOSITORY_ROOT / "config" / "text_ner" / "openai-compatible-api.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _aggregation(root: Path) -> Path:
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
                    "text": "FINDINGS: Tube tip is 3 cm above carina.",
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
    aggregation = root / "aggregation"
    aggregation.mkdir()
    source_specs = [
        ("srec:lab", "mimic_iv_hosp", "hosp.labevents", "labevents", 0, "comments", "laboratory_comment", admission["mimic_iv_hosp"]["labevents"][0]),
        ("srec:micro", "mimic_iv_hosp", "hosp.microbiologyevents", "microbiologyevents", 0, "comments", "microbiology_comment", admission["mimic_iv_hosp"]["microbiologyevents"][0]),
        ("srec:triage", "mimic_iv_ed", "ed.triage", "triage", 0, "chiefcomplaint", "chief_complaint", admission["mimic_iv_ed"]["triage"][0]),
        ("srec:rad", "mimic_iv_note", "note.radiology", "radiology", 0, "text", "radiology_report", admission["mimic_iv_note"]["radiology"][0]),
        ("srec:discharge", "mimic_iv_note", "note.discharge", "discharge", 0, "text", "discharge_summary", admission["mimic_iv_note"]["discharge"][0]),
    ]
    raw_rows = []
    for source_record_id, module, table, table_name, index, field, kind, record in source_specs:
        text = record[field]
        raw_rows.append(
            {
                "source_record_id": source_record_id,
                "subject_id": "1",
                "hadm_id": "10",
                "jsonl_line_number": 1,
                "source_module": module,
                "source_table": table,
                "source_table_name": table_name,
                "source_array_index": index,
                "raw_row_ref": f"readable.jsonl#L1/{module}.{table_name}[{index}]",
                "source_text_field": field,
                "source_text_kind": kind,
                "source_text": text,
                "source_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "clinical_readable_record_json": json.dumps(record, sort_keys=True),
            }
        )
    raw_table = pa.Table.from_pylist(raw_rows).replace_schema_metadata(
        {b"schema": b"event-source-record/1.0.0"}
    )
    raw_path = aggregation / "raw_source_records.parquet"
    pq.write_table(raw_table, raw_path)
    sources = [
        ("event:lab", "srec:lab", "hosp.labevents", "mapped"),
        ("event:micro", "srec:micro", "hosp.microbiologyevents", "mapped"),
        ("event:triage", "srec:triage", "ed.triage", "unresolved"),
        ("event:rad", "srec:rad", "note.radiology", "unresolved"),
        ("event:discharge", "srec:discharge", "note.discharge", "mapped"),
    ]
    rows = [
        {
            "event_id": event_id,
            "normalization_status": status,
            "concept_id": None,
            "preferred_name": None,
            "source_table": table,
            "source_record_id": source_record_id,
        }
        for event_id, source_record_id, table, status in sources
    ]
    event_table = pa.Table.from_pylist(rows).replace_schema_metadata(
        {b"schema": b"event-aggregation/1.0.0"}
    )
    processed = aggregation / "processed_events.parquet"
    traceable = aggregation / "traceable_events.parquet"
    pq.write_table(event_table, processed)
    pq.write_table(event_table, traceable)
    outputs = {}
    for path in (processed, raw_path, traceable):
        outputs[path.name] = {
            "sha256": _sha256_file(path),
            "bytes": path.stat().st_size,
            "rows": pq.ParquetFile(path).metadata.num_rows,
        }
    quality = {
        "schema_version": "event-aggregation-quality/1.0.0",
        "status": "passed",
        "checks": {"fixture_valid": True},
        "expected": {"admissions": 1, "events": 5, "all_source_records": 5},
        "observed": {
            "admissions": 1,
            "source_records": 5,
            "source_text_record_counts": {
                table: 1 for _, _, table, _, _, _, _, _ in source_specs
            },
            "source_text_character_counts": {
                table: len(record[field])
                for _, _, table, _, _, field, _, record in source_specs
            },
        },
    }
    (aggregation / "quality_report.json").write_text(
        json.dumps(quality), encoding="utf-8"
    )
    aggregation_manifest = {
        "schema_version": "event-aggregation-manifest/1.0.0",
        "aggregation_schema_version": "event-aggregation/1.0.0",
        "quality_status": "passed",
        "outputs": outputs,
        "text_fields": [
            {
                "source_module": module,
                "source_table": table,
                "source_text_field": field,
                "source_text_kind": kind,
            }
            for _, module, table, _, _, field, kind, _ in source_specs
        ],
    }
    (aggregation / "aggregation_manifest.json").write_text(
        json.dumps(aggregation_manifest), encoding="utf-8"
    )
    return aggregation


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


class AggregationTextManifestTests(unittest.TestCase):
    def test_all_configured_free_text_includes_hosp_and_discharge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            aggregation = _aggregation(root)
            result = prepare_aggregation_text_manifest(
                aggregation, SOURCE_CATALOG, root / "NER" / "input"
            )
            self.assertEqual(result["aggregation"]["schema_version"], "event-aggregation/1.0.0")
            self.assertFalse(list(root.rglob("*.jsonl")))
            counts = result["counts"]
            self.assertEqual(counts["admissions"], 1)
            self.assertEqual(counts["documents"], 5)
            self.assertEqual(counts["text_units"], 5)
            self.assertIn("hosp.labevents", counts["source_document_counts"])
            self.assertIn("hosp.microbiologyevents", counts["source_document_counts"])
            self.assertIn("note.discharge", counts["source_document_counts"])
            self.assertNotIn("hosp.prescriptions", counts["source_document_counts"])
            manifest = pq.read_table(
                root / "NER" / "input" / "text_ner_input_manifest.parquet"
            ).to_pylist()
            discharge = next(row for row in manifest if row["source_table"] == "note.discharge")
            self.assertEqual(discharge["inclusion_status"], "included")
            self.assertEqual(discharge["evidence_phase"], "post_hoc")
            self.assertEqual(counts["text_units_without_direct_event_link"], 0)

    def test_tampered_aggregation_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            aggregation = _aggregation(root)
            manifest_path = aggregation / "aggregation_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["outputs"]["raw_source_records.parquet"]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                AggregationTextManifestError, "AGGREGATION_OUTPUT_HASH_MISMATCH"
            ):
                prepare_aggregation_text_manifest(
                    aggregation, SOURCE_CATALOG, root / "NER" / "input"
                )


class GenericApiBatchTests(unittest.TestCase):
    def test_environment_file_is_strict_and_process_environment_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment_file = Path(temporary) / "api-settings.txt"
            environment_file.write_text(
                "\n".join(
                    [
                        "# Both .env and .txt extensions are accepted.",
                        "TEXT_NER_API_KEY='file-secret'",
                        "TEXT_NER_BASE_URL=http://127.0.0.1:9999/v1",
                        "TEXT_NER_MODEL=file-model",
                        'TEXT_NER_MODEL_VERSION="file-revision"',
                        "TEXT_NER_PROVIDER=file-provider",
                    ]
                ),
                encoding="utf-8",
            )
            loaded = load_environment_file(environment_file)
            resolved = resolve_environment(
                environment_file,
                {
                    "TEXT_NER_MODEL": "process-model",
                    "UNRELATED_SETTING": "ignored",
                },
            )
            settings = OpenAICompatibleSettings.from_environment(
                load_api_config(API_CONFIG), resolved
            )
            self.assertEqual(loaded["TEXT_NER_API_KEY"], "file-secret")
            self.assertEqual(settings.model, "process-model")
            self.assertEqual(settings.model_version, "file-revision")
            self.assertNotIn("UNRELATED_SETTING", resolved)
            self.assertNotIn("file-secret", repr(settings))

    def test_environment_file_rejects_invalid_content_without_secret_values(self) -> None:
        cases = {
            "unknown.env": "TEXT_NER_API_KEY=hidden-secret\nUNKNOWN_KEY=value\n",
            "duplicate.env": (
                "TEXT_NER_API_KEY=hidden-secret\nTEXT_NER_API_KEY=second-secret\n"
            ),
            "malformed.env": "TEXT_NER_API_KEY=hidden-secret\nnot-an-assignment\n",
            "quote.env": "TEXT_NER_API_KEY='hidden-secret\n",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, content in cases.items():
                with self.subTest(name=name):
                    path = root / name
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(GenericApiError) as raised:
                        load_environment_file(path)
                    self.assertNotIn("hidden-secret", str(raised.exception))
                    self.assertNotIn("second-secret", str(raised.exception))

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

    def test_empty_content_retries_then_accepts_complete_json_fence(self) -> None:
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
        transport_calls: list[dict[str, object]] = []

        def transport(
            settings: OpenAICompatibleSettings,
            endpoint: str,
            payload: dict[str, object],
            timeout: int,
        ) -> dict[str, object]:
            transport_calls.append(payload)
            if len(transport_calls) == 1:
                return {
                    "id": "empty:1",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": "   ",
                                "reasoning_content": "private reasoning",
                            },
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": 7,
                        "total_tokens": 12,
                        "completion_tokens_details": {"reasoning_tokens": 7},
                    },
                }
            return {
                "id": "valid:2",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "```json\n"
                            + json.dumps(annotation)
                            + "\n```"
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                },
            }

        environment = {
            "TEXT_NER_API_KEY": "test-secret",
            "TEXT_NER_BASE_URL": "http://127.0.0.1:9999/v1",
            "TEXT_NER_MODEL": "deepseek-v4-flash",
            "TEXT_NER_MODEL_VERSION": "DeepSeek-V4-Flash",
            "TEXT_NER_PROVIDER": "deepseek",
        }
        sleeps: list[float] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prompt = root / "prompt.md"
            prompt.write_text(prompt_text, encoding="utf-8")
            requests = root / "requests.jsonl"
            requests.write_text(json.dumps(request) + "\n", encoding="utf-8")
            responses = root / "responses.jsonl"
            audit = root / "audit.jsonl"
            summary = run_api_batch(
                requests,
                prompt,
                responses,
                audit,
                API_CONFIG,
                execute=True,
                endpoint_scope="local",
                maximum_requests=1,
                environ=environment,
                transport=transport,
                sleep=sleeps.append,
            )
            failures = root / "audit.failures.jsonl"
            failure_rows = [
                json.loads(line)
                for line in failures.read_text(encoding="utf-8").splitlines()
            ]
            success_audit = json.loads(audit.read_text(encoding="utf-8"))
            self.assertEqual(summary["model_calls_this_run"], 2)
            self.assertEqual(summary["successful_responses_this_run"], 1)
            self.assertEqual(summary["failed_attempts_this_run"], 1)
            self.assertEqual(summary["retries"], 1)
            self.assertEqual(summary["usage_this_run"]["total_tokens"], 26)
            self.assertEqual(
                summary["successful_usage_this_run"]["total_tokens"], 14
            )
            self.assertEqual(sleeps, [2.0])
            self.assertEqual(len(failure_rows), 1)
            self.assertEqual(
                failure_rows[0]["reason_code"],
                "GENERIC_API_ANNOTATION_CONTENT_EMPTY",
            )
            self.assertTrue(failure_rows[0]["will_retry"])
            self.assertEqual(failure_rows[0]["reasoning_content_length"], 17)
            self.assertFalse(failure_rows[0]["raw_model_content_persisted"])
            self.assertNotIn("private reasoning", failures.read_text(encoding="utf-8"))
            self.assertNotIn(text, failures.read_text(encoding="utf-8"))
            self.assertNotIn("test-secret", failures.read_text(encoding="utf-8"))
            self.assertEqual(
                success_audit["content_normalization"],
                "markdown_json_fence_removed",
            )
            self.assertEqual(success_audit["attempt_number"], 2)
            self.assertEqual(success_audit["thinking_mode"], "disabled")
            self.assertEqual(
                transport_calls[0]["thinking"], {"type": "disabled"}
            )

    def test_length_finish_reason_is_audited_without_useless_retry(self) -> None:
        prompt_text = "Return JSON."
        request = _api_request("Chest pain", prompt_text)
        calls = 0
        sleeps: list[float] = []

        def transport(*args: object) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {
                "id": "truncated:1",
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '{"schema_version":'},
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4096,
                    "total_tokens": 4106,
                },
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
            audit = root / "audit.jsonl"
            with self.assertRaisesRegex(
                GenericApiError, "GENERIC_API_OUTPUT_TRUNCATED"
            ):
                run_api_batch(
                    requests,
                    prompt,
                    root / "responses.jsonl",
                    audit,
                    API_CONFIG,
                    execute=True,
                    endpoint_scope="local",
                    environ=environment,
                    transport=transport,
                    sleep=sleeps.append,
                )
            failure = json.loads(
                (root / "audit.failures.jsonl").read_text(encoding="utf-8")
            )
            self.assertEqual(calls, 1)
            self.assertEqual(sleeps, [])
            self.assertEqual(failure["finish_reason"], "length")
            self.assertFalse(failure["retryable"])
            self.assertFalse(failure["will_retry"])
            self.assertEqual(failure["usage"]["total_tokens"], 4106)

    def test_persistent_identical_invalid_json_is_quarantined_early(self) -> None:
        prompt_text = "Return JSON."
        request = _api_request("Chest pain", prompt_text)
        calls = 0

        def transport(*args: object) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {
                "id": f"invalid:{calls}",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "not json"},
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
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
            audit = root / "audit.jsonl"
            summary = run_api_batch(
                requests,
                prompt,
                root / "responses.jsonl",
                audit,
                API_CONFIG,
                execute=True,
                endpoint_scope="local",
                environ=environment,
                transport=transport,
                sleep=lambda _: None,
            )
            failures = [
                json.loads(line)
                for line in (root / "audit.failures.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(calls, 2)
            self.assertEqual(len(failures), 2)
            self.assertEqual(
                [row["attempt_number"] for row in failures], [1, 2]
            )
            self.assertEqual(
                [row["will_retry"] for row in failures], [True, False]
            )
            self.assertEqual(
                failures[-1]["retry_stop_reason"], "identical_invalid_content"
            )
            self.assertEqual(summary["attempted_requests_this_run"], 1)
            self.assertEqual(summary["successful_responses_this_run"], 0)
            self.assertEqual(summary["failed_requests_this_run"], 1)
            self.assertTrue(
                all(row["content_sha256"] for row in failures)
            )
            self.assertNotIn(
                "not json",
                (root / "audit.failures.jsonl").read_text(encoding="utf-8"),
            )

    def test_unique_exact_surface_is_grounded_and_audited(self) -> None:
        text = "Chest pain"
        prompt_text = "Return JSON."
        request = _api_request(text, prompt_text)
        annotation = {
            "schema_version": SECTION_ANNOTATION_SCHEMA_VERSION,
            "manifest_row_id": request["manifest_row_id"],
            "document_id": request["document_id"],
            "section_id": request["section_id"],
            "section_text_sha256": request["section_text_sha256"],
            "mentions": [
                {
                    "local_id": "m1",
                    "surface_text": "Chest pain",
                    "section_span_start": 1,
                    "section_span_end": 11,
                    "entity_type": "symptom_or_sign",
                    "assertion": "present",
                    "temporality": "current",
                    "experiencer": "patient",
                    "laterality": "not_applicable",
                    "severity": "not_stated",
                    "trend": "not_stated",
                    "normalization_status": "unattempted",
                    "concept_id": None,
                    "preferred_name": None,
                    "terminology": None,
                    "quality_flags": [],
                }
            ],
            "relations": [],
        }

        def transport(*args: object) -> dict[str, object]:
            return {
                "id": "grounded:1",
                "choices": [{"message": {"content": json.dumps(annotation)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
            }

        environment = {
            "TEXT_NER_API_KEY": "test-secret",
            "TEXT_NER_BASE_URL": "http://127.0.0.1:9999/v1",
            "TEXT_NER_MODEL": "test-model",
            "TEXT_NER_MODEL_VERSION": "test-revision",
            "TEXT_NER_PROVIDER": "test-provider",
        }
        progress: list[str] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prompt = root / "prompt.md"
            prompt.write_text(prompt_text, encoding="utf-8")
            requests = root / "requests.jsonl"
            requests.write_text(json.dumps(request) + "\n", encoding="utf-8")
            responses = root / "responses.jsonl"
            audit = root / "audit.jsonl"
            summary = run_api_batch(
                requests,
                prompt,
                responses,
                audit,
                API_CONFIG,
                execute=True,
                endpoint_scope="local",
                maximum_requests=1,
                environ=environment,
                transport=transport,
                sleep=lambda _: None,
                progress_reporter=progress.append,
            )
            response = json.loads(responses.read_text(encoding="utf-8"))
            success_audit = json.loads(audit.read_text(encoding="utf-8"))
            mention = response["annotation"]["mentions"][0]
            self.assertEqual(
                (mention["section_span_start"], mention["section_span_end"]),
                (0, 10),
            )
            grounding = success_audit["span_grounding"]
            self.assertEqual(grounding["repair_count"], 1)
            self.assertEqual(
                grounding["repairs"][0]["rule"], "unique_exact_occurrence"
            )
            self.assertNotIn("Chest pain", json.dumps(grounding))
            self.assertEqual(summary["failed_requests_this_run"], 0)
            self.assertTrue(any("本次 tokens 18" in line for line in progress))

    def test_unrepairable_annotation_is_quarantined_and_batch_continues(self) -> None:
        prompt_text = "Return JSON."
        first = _api_request("Chest pain", prompt_text)
        second = _api_request("Fever", prompt_text)
        second.update(
            {
                "request_id": "request:2",
                "annotation_unit_id": "unit:2",
                "manifest_row_id": "manifest:2",
                "document_id": "document:2",
                "section_id": "section:2",
            }
        )

        invalid_annotation = {
            "schema_version": SECTION_ANNOTATION_SCHEMA_VERSION,
            "manifest_row_id": first["manifest_row_id"],
            "document_id": first["document_id"],
            "section_id": first["section_id"],
            "section_text_sha256": first["section_text_sha256"],
            "mentions": [
                {
                    "local_id": "m1",
                    "surface_text": "hallucinated",
                    "section_span_start": 0,
                    "section_span_end": 3,
                    "entity_type": "clinical_problem",
                    "assertion": "present",
                    "temporality": "current",
                    "experiencer": "patient",
                    "laterality": "not_applicable",
                    "severity": "not_stated",
                    "trend": "not_stated",
                    "normalization_status": "unattempted",
                    "concept_id": None,
                    "preferred_name": None,
                    "terminology": None,
                    "quality_flags": [],
                }
            ],
            "relations": [],
        }
        valid_annotation = {
            "schema_version": SECTION_ANNOTATION_SCHEMA_VERSION,
            "manifest_row_id": second["manifest_row_id"],
            "document_id": second["document_id"],
            "section_id": second["section_id"],
            "section_text_sha256": second["section_text_sha256"],
            "mentions": [],
            "relations": [],
        }
        calls = 0

        def transport(*args: object) -> dict[str, object]:
            nonlocal calls
            calls += 1
            annotation = invalid_annotation if calls <= 2 else valid_annotation
            return {
                "id": f"response:{calls}",
                "choices": [{"message": {"content": json.dumps(annotation)}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
            }

        environment = {
            "TEXT_NER_API_KEY": "test-secret",
            "TEXT_NER_BASE_URL": "http://127.0.0.1:9999/v1",
            "TEXT_NER_MODEL": "test-model",
            "TEXT_NER_MODEL_VERSION": "test-revision",
            "TEXT_NER_PROVIDER": "test-provider",
        }
        progress: list[str] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prompt = root / "prompt.md"
            prompt.write_text(prompt_text, encoding="utf-8")
            requests = root / "requests.jsonl"
            requests.write_text(
                "\n".join(json.dumps(item) for item in (first, second)) + "\n",
                encoding="utf-8",
            )
            responses = root / "responses.jsonl"
            summary = run_api_batch(
                requests,
                prompt,
                responses,
                root / "audit.jsonl",
                API_CONFIG,
                execute=True,
                endpoint_scope="local",
                maximum_requests=2,
                environ=environment,
                transport=transport,
                sleep=lambda _: None,
                progress_reporter=progress.append,
            )
            persisted = [
                json.loads(line)
                for line in responses.read_text(encoding="utf-8").splitlines()
            ]
            failures = [
                json.loads(line)
                for line in (root / "audit.failures.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(calls, 3)
            self.assertEqual(summary["attempted_requests_this_run"], 2)
            self.assertEqual(summary["successful_responses_this_run"], 1)
            self.assertEqual(summary["failed_requests_this_run"], 1)
            self.assertEqual(summary["completed_total"], 1)
            self.assertEqual(persisted[0]["request_id"], "request:2")
            self.assertEqual(
                failures[-1]["annotation_validation_reason_code"],
                "MENTION_SURFACE_MISMATCH",
            )
            self.assertEqual(
                failures[-1]["annotation_validation_local_id"], "m1"
            )
            self.assertTrue(any("文本单元失败并继续" in line for line in progress))
            self.assertTrue(any("成功 1 | 失败 1" in line for line in progress))

    def test_repeated_surface_requires_a_unique_nearest_occurrence(self) -> None:
        mention = {
            "local_id": "m1",
            "surface_text": "pain",
            "section_span_start": 7,
            "section_span_end": 11,
        }
        annotation = {"mentions": [mention], "relations": []}
        grounded, repairs = ground_annotation_spans(annotation, "pain xx pain")
        self.assertEqual(
            (
                grounded["mentions"][0]["section_span_start"],
                grounded["mentions"][0]["section_span_end"],
            ),
            (8, 12),
        )
        self.assertEqual(repairs[0]["candidate_count"], 2)
        self.assertEqual(
            repairs[0]["rule"], "unique_nearest_exact_occurrence"
        )

        tied = {
            "mentions": [
                {**mention, "section_span_start": 4, "section_span_end": 8}
            ],
            "relations": [],
        }
        unchanged, tied_repairs = ground_annotation_spans(tied, "pain xx pain")
        self.assertEqual(unchanged["mentions"][0]["section_span_start"], 4)
        self.assertEqual(tied_repairs, [])

    def test_relation_evidence_is_grounded_to_occurrence_covering_mentions(self) -> None:
        annotation = {
            "mentions": [
                {
                    "local_id": "m1",
                    "surface_text": "pain",
                    "section_span_start": 14,
                    "section_span_end": 18,
                },
                {
                    "local_id": "m2",
                    "surface_text": "fever",
                    "section_span_start": 19,
                    "section_span_end": 24,
                },
            ],
            "relations": [
                {
                    "local_id": "r1",
                    "source_mention_id": "m1",
                    "target_mention_id": "m2",
                    "evidence_text": "pain fever",
                    "section_evidence_start": 0,
                    "section_evidence_end": 10,
                }
            ],
        }
        grounded, repairs = ground_annotation_spans(
            annotation, "pain fever xx pain fever"
        )
        relation = grounded["relations"][0]
        self.assertEqual(
            (relation["section_evidence_start"], relation["section_evidence_end"]),
            (14, 24),
        )
        self.assertEqual(repairs[0]["item_kind"], "relation")
        self.assertEqual(repairs[0]["candidate_count"], 1)

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
            environment_file = root / ".env"
            environment_file.write_text(
                "\n".join(f"{key}={value}" for key, value in environment.items()),
                encoding="utf-8",
            )
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
                environment_file=environment_file,
                environ={},
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
            self.assertNotIn("thinking", calls[0][2])
            self.assertNotIn("test-secret", repr(calls[0][0]))
            self.assertNotIn("test-secret", audit.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
