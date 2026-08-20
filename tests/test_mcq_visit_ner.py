from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any

from data_pipeline.mcq_visit_extract.columns import RESULT_COLUMNS
from data_pipeline.mcq_visit_ner.client import (
    APPROVAL_VALUE,
    ApiSettings,
    NerError,
    enforce_execution_gates,
    load_env_file,
    parse_json_object,
)
from data_pipeline.mcq_visit_ner.ground import ground_surface
from data_pipeline.mcq_visit_ner.pipeline import (
    compile_mentions,
    main,
    prepare,
    run_mentions,
    status,
)


def _visit(**overrides: object) -> dict[str, Any]:
    visit = {key: None for key in RESULT_COLUMNS}
    visit.update(
        {
            "subject_id": "1",
            "hadm_id": "10",
            "age_at_encounter": 60,
            "sex": "F",
            "admission_type": "EW EMER.",
            "chief_complaint": "Chest pain",
            "primary_icd_code": "I214",
            "primary_diagnosis_name": "NSTEMI",
            "primary_icd_version": "ICD-10-CM",
            "discharge_note_full": (
                "Chief Complaint:\nChest pain\n\n"
                "History of Present Illness:\nThe patient denies dyspnea.\n"
                "Aspirin 81 mg daily.\n"
            ),
        }
    )
    visit.update(overrides)
    return visit


def _write_visits(path: Path, visits: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("[\n")
        for index, visit in enumerate(visits):
            if index:
                handle.write(",\n")
            handle.write(json.dumps(visit, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n]\n")


def _env() -> dict[str, str]:
    return {
        "MCQ_VISIT_NER_API_KEY": "test-key-not-real",
        "MCQ_VISIT_NER_BASE_URL": "https://www.dmxapi.cn/v1",
        "MCQ_VISIT_NER_MODEL": "deepseek-v4-flash",
        "MCQ_VISIT_NER_MODEL_VERSION": "DeepSeek-V4-Flash",
        "MCQ_VISIT_NER_PROVIDER": "openai-compatible",
        "MCQ_VISIT_NER_EXTERNAL_API_APPROVED": APPROVAL_VALUE,
    }


class GroundingTests(unittest.TestCase):
    def test_unique_exact(self) -> None:
        located = ground_surface("denies dyspnea today", "dyspnea")
        self.assertEqual(located, (7, 14, False))

    def test_casefold_rewrites_to_source(self) -> None:
        text = "Chest Pain started today"
        located = ground_surface(text, "chest pain")
        self.assertIsNotNone(located)
        start, end, rewritten = located  # type: ignore[misc]
        self.assertTrue(rewritten)
        self.assertEqual(text[start:end], "Chest Pain")

    def test_ambiguous_returns_none(self) -> None:
        self.assertIsNone(ground_surface("pain then pain", "pain"))


class EnvAndGateTests(unittest.TestCase):
    def test_env_file_ignores_text_ner_keys(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / ".env"
            path.write_text(
                "TEXT_NER_API_KEY=other\n"
                "MCQ_VISIT_NER_API_KEY=visit-key\n"
                "MCQ_VISIT_NER_BASE_URL=https://www.dmxapi.cn/v1\n",
                encoding="utf-8",
            )
            values = load_env_file(path)
            self.assertEqual(values["MCQ_VISIT_NER_API_KEY"], "visit-key")
            self.assertNotIn("TEXT_NER_API_KEY", values)

    def test_settings_repr_redacts_key(self) -> None:
        settings = ApiSettings.resolve(None, environ=_env())
        text = repr(settings)
        self.assertIn("<redacted>", text)
        self.assertNotIn("test-key-not-real", text)
        self.assertEqual(settings.model, "deepseek-v4-flash")
        self.assertEqual(settings.base_url, "https://www.dmxapi.cn/v1")
        self.assertFalse(settings.is_loopback())

    def test_external_gates(self) -> None:
        settings = ApiSettings.resolve(None, environ=_env())
        with self.assertRaisesRegex(NerError, "MODEL_EXECUTION_NOT_AUTHORIZED"):
            enforce_execution_gates(
                execute=False,
                data_transfer_authorized=True,
                settings=settings,
                environ=_env(),
            )
        with self.assertRaisesRegex(NerError, "EXTERNAL_DATA_TRANSFER_NOT_AUTHORIZED"):
            enforce_execution_gates(
                execute=True,
                data_transfer_authorized=False,
                settings=settings,
                environ=_env(),
            )
        denied = dict(_env())
        denied["MCQ_VISIT_NER_EXTERNAL_API_APPROVED"] = ""
        with self.assertRaisesRegex(NerError, "EXTERNAL_API_NOT_APPROVED"):
            enforce_execution_gates(
                execute=True,
                data_transfer_authorized=True,
                settings=settings,
                environ=denied,
            )
        enforce_execution_gates(
            execute=True,
            data_transfer_authorized=True,
            settings=settings,
            environ=_env(),
        )

    def test_loopback_skips_external_approval(self) -> None:
        settings = ApiSettings(
            api_key="local",
            base_url="http://127.0.0.1:8000/v1",
            model="local-model",
            model_version="local",
            provider="local",
        )
        enforce_execution_gates(
            execute=True,
            data_transfer_authorized=False,
            settings=settings,
            environ={},
        )

    def test_json_fence_strip(self) -> None:
        parsed = parse_json_object('```json\n{"mentions": []}\n```')
        self.assertEqual(parsed, {"mentions": []})


class PipelineTests(unittest.TestCase):
    def test_prepare_chunks_and_refuses_extract_dir(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            extract_dir = root / "extract"
            visits_path = extract_dir / "visits.json"
            _write_visits(visits_path, [_visit(), _visit(subject_id="2", hadm_id="20")])
            with self.assertRaisesRegex(NerError, "REFUSING_EXTRACT_DIR"):
                prepare(input_path=visits_path, output_dir=extract_dir, max_visits=1)
            output_dir = root / "ner"
            result = prepare(
                input_path=visits_path,
                output_dir=output_dir,
                max_visits=1,
            )
            self.assertEqual(result["visits_selected"], 1)
            self.assertEqual(result["chunks"], 1)
            self.assertFalse(result["resumed"])
            documents = (output_dir / "documents.jsonl").read_text(encoding="utf-8")
            self.assertIn("Chest pain", documents)
            resumed = prepare(
                input_path=visits_path,
                output_dir=output_dir,
                max_visits=1,
            )
            self.assertTrue(resumed["resumed"])

    def test_prepare_accepts_discharge_medication_field(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            visits_path = root / "extract" / "visits.json"
            _write_visits(
                visits_path,
                [
                    _visit(
                        discharge_note_full=None,
                        discharge_medications="1. Calcium Oral\n",
                    )
                ],
            )
            result = prepare(
                input_path=visits_path,
                output_dir=root / "ner",
                fields=("discharge_medications",),
                max_visits=1,
            )
            self.assertEqual(result["field_chunk_counts"]["discharge_medications"], 1)

    def test_prepare_falls_back_when_ds_empty(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            visits_path = root / "extract" / "visits.json"
            _write_visits(
                visits_path,
                [_visit(discharge_note_full=None, history_of_present_illness="Pain started today.")],
            )
            result = prepare(
                input_path=visits_path,
                output_dir=root / "ner",
                max_visits=1,
            )
            self.assertEqual(result["field_chunk_counts"]["history_of_present_illness"], 1)

    def test_identity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            visits_path = root / "extract" / "visits.json"
            _write_visits(visits_path, [_visit()])
            output_dir = root / "ner"
            prepare(input_path=visits_path, output_dir=output_dir, max_visits=1)
            with self.assertRaisesRegex(NerError, "MANIFEST_IDENTITY_MISMATCH"):
                prepare(input_path=visits_path, output_dir=output_dir, max_visits=2)

    def test_run_without_execute_does_not_call_transport(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            visits_path = root / "extract" / "visits.json"
            _write_visits(visits_path, [_visit()])
            output_dir = root / "ner"
            prepare(input_path=visits_path, output_dir=output_dir, max_visits=1)
            called = {"n": 0}

            def transport(url, payload, headers, timeout):  # type: ignore[no-untyped-def]
                called["n"] += 1
                raise AssertionError("transport must not be called")

            with self.assertRaisesRegex(NerError, "MODEL_EXECUTION_NOT_AUTHORIZED"):
                run_mentions(
                    output_dir,
                    execute=False,
                    data_transfer_authorized=True,
                    environ=_env(),
                    transport=transport,
                    sleep=lambda _seconds: None,
                )
            self.assertEqual(called["n"], 0)

    def test_run_grounds_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            visits_path = root / "extract" / "visits.json"
            _write_visits(visits_path, [_visit()])
            output_dir = root / "ner"
            prepare(input_path=visits_path, output_dir=output_dir, max_visits=1)
            calls = {"n": 0}

            def transport(url, payload, headers, timeout):  # type: ignore[no-untyped-def]
                calls["n"] += 1
                self.assertEqual(url, "https://www.dmxapi.cn/v1/chat/completions")
                self.assertIn("Bearer test-key-not-real", headers["Authorization"])
                user = json.loads(payload["messages"][1]["content"])
                self.assertIn("Chest pain", user["section_text"])
                return {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": json.dumps(
                                    {
                                        "mentions": [
                                            {
                                                "surface_text": "Chest pain",
                                                "entity_type": "symptom_or_sign",
                                            },
                                            {
                                                "surface_text": "dyspnea",
                                                "entity_type": "symptom_or_sign",
                                                "assertion": "absent",
                                            },
                                            {
                                                "surface_text": "Aspirin",
                                                "entity_type": "medication_or_substance",
                                            },
                                            {
                                                "surface_text": "not-in-text",
                                                "entity_type": "clinical_problem",
                                            },
                                            {
                                                "surface_text": "mild",
                                                "entity_type": "symptom_or_sign",
                                            },
                                        ]
                                    }
                                )
                            },
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }

            first = run_mentions(
                output_dir,
                execute=True,
                data_transfer_authorized=True,
                environ=_env(),
                transport=transport,
                sleep=lambda _seconds: None,
            )
            self.assertEqual(first["successful"], 1)
            self.assertEqual(calls["n"], 1)
            second = run_mentions(
                output_dir,
                execute=True,
                data_transfer_authorized=True,
                environ=_env(),
                transport=transport,
                sleep=lambda _seconds: None,
            )
            self.assertEqual(second["pending"], 0)
            self.assertEqual(calls["n"], 1)
            compiled = compile_mentions(output_dir)
            self.assertEqual(compiled["visits"], 1)
            self.assertEqual(compiled["mentions"], 3)
            self.assertEqual(compiled["incomplete_docs"], 0)
            mentions = json.loads(
                (output_dir / "visit_mentions.jsonl").read_text(encoding="utf-8")
            )
            surfaces = [item["surface_text"] for item in mentions["mentions"]]
            self.assertEqual(surfaces, ["Chest pain", "dyspnea", "Aspirin"])
            dyspnea = mentions["mentions"][1]
            self.assertEqual(dyspnea["assertion"], "absent")
            self.assertEqual(
                _visit()["discharge_note_full"][
                    dyspnea["field_span_start"] : dyspnea["field_span_end"]
                ],
                "dyspnea",
            )
            report = status(output_dir)
            self.assertEqual(report["mention_docs_done"], 1)
            self.assertTrue(report["does_not_overwrite_extract"])
            original = json.loads(
                Path(visits_path).read_text(encoding="utf-8").splitlines()[1].rstrip(",")
            )
            self.assertEqual(original["discharge_note_full"], _visit()["discharge_note_full"])

    def test_prepare_all_requires_all_visits_flag(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            visits_path = root / "extract" / "visits.json"
            _write_visits(visits_path, [_visit()])
            output_dir = root / "ner"
            prepare(input_path=visits_path, output_dir=output_dir)
            with self.assertRaisesRegex(NerError, "VISIT_LIMIT_REQUIRED"):
                run_mentions(
                    output_dir,
                    execute=True,
                    data_transfer_authorized=True,
                    environ=_env(),
                    transport=lambda *args, **kwargs: {},
                    sleep=lambda _seconds: None,
                )

    def test_workers_complete_all_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            visits_path = root / "extract" / "visits.json"
            visits = [
                _visit(
                    subject_id=str(index),
                    hadm_id=str(10 + index),
                    discharge_note_full="Chief Complaint:\nChest pain\n",
                )
                for index in range(3)
            ]
            _write_visits(visits_path, visits)
            output_dir = root / "ner"
            prepare(input_path=visits_path, output_dir=output_dir, max_visits=3)
            inflight = {"n": 0, "max": 0}
            lock = threading.Lock()

            def transport(url, payload, headers, timeout):  # type: ignore[no-untyped-def]
                with lock:
                    inflight["n"] += 1
                    inflight["max"] = max(inflight["max"], inflight["n"])
                time.sleep(0.05)
                with lock:
                    inflight["n"] -= 1
                return {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": json.dumps(
                                    {
                                        "mentions": [
                                            {
                                                "surface_text": "Chest pain",
                                                "entity_type": "symptom_or_sign",
                                            }
                                        ]
                                    }
                                )
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }

            result = run_mentions(
                output_dir,
                execute=True,
                data_transfer_authorized=True,
                environ=_env(),
                transport=transport,
                workers=3,
                requests_per_minute=1000,
                sleep=lambda _seconds: None,
            )
            self.assertEqual(result["successful"], 3)
            self.assertEqual(result["failed"], 0)
            self.assertEqual(result["workers"], 3)
            self.assertGreaterEqual(inflight["max"], 2)

    def test_cli_prepare_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            visits_path = root / "extract" / "visits.json"
            output_dir = root / "ner"
            _write_visits(visits_path, [_visit()])
            code = main(
                [
                    "prepare",
                    "--input",
                    str(visits_path),
                    "--output-dir",
                    str(output_dir),
                    "--max-visits",
                    "1",
                ]
            )
            self.assertEqual(code, 0)
            self.assertTrue((output_dir / "documents.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
