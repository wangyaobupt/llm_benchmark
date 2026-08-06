import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from rwd_pipeline.cleaning.pipeline import (
    CLEANED_FIELDS,
    OUTPUT_COLUMNS,
    CleaningError,
    DeepSeekClient,
    ResponseError,
    _normalize_entities,
    _prepare_llm_text,
    run_cleaning,
)
from rwd_pipeline.cleaning.prompts import PROMPTS


class FakeClient:
    def __init__(self, responses=None, error=None):
        self.responses = responses or {}
        self.error = error
        self.calls = []

    def extract(self, field, text):
        self.calls.append((field, text))
        if self.error is not None:
            raise self.error
        return list(self.responses.get((field, text), []))


class CleaningPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.input = root / "input.csv"
        self.output = root / "out" / "cleaned.csv"
        self.checkpoint = root / "out" / "checkpoint.jsonl"
        self.rows = [self._row("1", "10"), self._row("2", "20", empty=True)]
        self._write_input(self.rows)

    def tearDown(self):
        self.tempdir.cleanup()

    def _row(self, subject_id, hadm_id, empty=False):
        row = {column: f"{column}-{hadm_id}" for column in OUTPUT_COLUMNS}
        row["subject_id"] = subject_id
        row["hadm_id"] = hadm_id
        if empty:
            row["chief_complaint"] = "[**Name**] ---"
            row["history_of_present_illness"] = ""
            row["past_medical_history"] = "None"
            row["medications_on_admission"] = "No medications"
        else:
            row["chief_complaint"] = "Chest pain"
            row["history_of_present_illness"] = "Worsening pain and nausea"
            row["past_medical_history"] = "Hypertension"
            row["medications_on_admission"] = "Aspirin 81 mg daily"
        return row

    def _write_input(self, rows):
        with self.input.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def test_cleans_four_fields_and_copies_every_other_value(self):
        responses = {
            ("chief_complaint", "Chest pain"): ["Chest pain", " chest   PAIN "],
            ("history_of_present_illness", "Worsening pain and nausea"): [
                "Worsening pain",
                "nausea",
            ],
            ("past_medical_history", "Hypertension"): ["Hypertension"],
            ("medications_on_admission", "Aspirin 81 mg daily"): ["Aspirin"],
        }
        client = FakeClient(responses)
        summary = run_cleaning(self.input, self.output, self.checkpoint, 2, client)

        self.assertEqual(summary.row_count, 2)
        self.assertEqual(summary.api_requests, 4)
        self.assertEqual(summary.skipped_empty, 4)
        self.assertEqual({field for field, _ in client.calls}, set(CLEANED_FIELDS))
        with self.output.open(encoding="utf-8", newline="") as handle:
            cleaned = list(csv.DictReader(handle))
        for field in OUTPUT_COLUMNS:
            if field not in CLEANED_FIELDS:
                self.assertEqual(cleaned[0][field], self.rows[0][field])
                self.assertEqual(cleaned[1][field], self.rows[1][field])
        self.assertEqual(json.loads(cleaned[0]["chief_complaint"]), ["Chest pain"])
        for field in CLEANED_FIELDS:
            self.assertEqual(json.loads(cleaned[1][field]), [])

    def test_reuses_checkpoint_and_invalidates_changed_input(self):
        first_client = FakeClient(
            {(field, self.rows[0][field]): [field] for field in CLEANED_FIELDS}
        )
        run_cleaning(self.input, self.output, self.checkpoint, 1, first_client)

        self.rows[0]["chief_complaint"] = "New complaint"
        self._write_input(self.rows)
        second_client = FakeClient({("chief_complaint", "New complaint"): ["New complaint"]})
        summary = run_cleaning(self.input, self.output, self.checkpoint, 1, second_client)

        self.assertEqual(summary.checkpoint_reused, 3)
        self.assertEqual(summary.api_requests, 1)
        self.assertEqual(second_client.calls, [("chief_complaint", "New complaint")])

    def test_truncates_incomplete_final_checkpoint_record(self):
        self.checkpoint.parent.mkdir(parents=True)
        self.checkpoint.write_text('{"row_index":0', encoding="utf-8")
        client = FakeClient({(field, self.rows[0][field]): [] for field in CLEANED_FIELDS})
        run_cleaning(self.input, self.output, self.checkpoint, 1, client)
        records = [json.loads(line) for line in self.checkpoint.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(records), 4)

    def test_ignores_checkpoint_from_another_cleaning_configuration(self):
        self.checkpoint.parent.mkdir(parents=True)
        self.checkpoint.write_text(
            json.dumps(
                {
                    "row_index": 0,
                    "field": "chief_complaint",
                    "input_sha256": "0" * 64,
                    "entities": ["Old result"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        client = FakeClient({(field, self.rows[0][field]): [] for field in CLEANED_FIELDS})
        summary = run_cleaning(self.input, self.output, self.checkpoint, 1, client)
        self.assertEqual(summary.checkpoint_reused, 0)
        self.assertEqual(summary.api_requests, 4)

    def test_failure_does_not_replace_existing_output(self):
        self.output.parent.mkdir(parents=True)
        self.output.write_text("existing output", encoding="utf-8")
        client = FakeClient(error=CleaningError("API unavailable"))
        with self.assertRaises(CleaningError):
            run_cleaning(self.input, self.output, self.checkpoint, 1, client)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "existing output")


class DeepSeekClientTests(unittest.TestCase):
    def test_removes_placeholders_before_request(self):
        self.assertEqual(
            _prepare_llm_text("acute ___ chest pain on [**Date**]"),
            "acute chest pain on",
        )

    def test_rejects_placeholder_in_response(self):
        with self.assertRaises(ResponseError):
            _normalize_entities({"entities": ["cardiogenic ___"]})

    def test_disables_thinking_in_request_payload(self):
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = '{"entities":["Chest pain"]}'
        sdk = MagicMock()
        sdk.chat.completions.create.return_value = response
        with patch("rwd_pipeline.cleaning.pipeline.OpenAI", return_value=sdk) as openai_client:
            client = DeepSeekClient("test-key")
            entities = client.extract("chief_complaint", "Chest pain")

        openai_client.assert_called_once_with(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            timeout=180,
            max_retries=0,
        )
        request = sdk.chat.completions.create.call_args.kwargs
        self.assertEqual(request["extra_body"], {"thinking": {"type": "disabled"}})
        self.assertEqual(entities, ["Chest pain"])

    def test_retries_invalid_response(self):
        client = DeepSeekClient("test-key", max_attempts=2, sleep=lambda _: None)
        with patch.object(
            client,
            "_request_once",
            side_effect=[ResponseError("invalid"), ["Chest pain"]],
        ) as request:
            self.assertEqual(client.extract("chief_complaint", "Chest pain"), ["Chest pain"])
        self.assertEqual(request.call_count, 2)
        self.assertFalse(request.call_args_list[0].kwargs["corrective_retry"])
        self.assertTrue(request.call_args_list[1].kwargs["corrective_retry"])

    def test_reports_truncated_response_and_adds_retry_instruction(self):
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].finish_reason = "length"
        response.choices[0].message.content = '{"entities":["pain"'
        sdk = MagicMock()
        sdk.chat.completions.create.return_value = response
        with patch("rwd_pipeline.cleaning.pipeline.OpenAI", return_value=sdk):
            client = DeepSeekClient("test-key", max_attempts=1)
            with self.assertRaisesRegex(ResponseError, "truncated.*finish_reason=length"):
                client._request_once(
                    "history_of_present_illness", "Abdominal pain", corrective_retry=True
                )

        messages = sdk.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(len(messages), 3)
        self.assertIn("never repeat an entity", messages[-1]["content"])

    def test_prompts_are_field_specific(self):
        self.assertEqual(set(PROMPTS), set(CLEANED_FIELDS))
        self.assertEqual(len(set(PROMPTS.values())), 4)
        for field, prompt in PROMPTS.items():
            self.assertIn(field, prompt)
            self.assertIn("Return JSON only", prompt)


if __name__ == "__main__":
    unittest.main()
