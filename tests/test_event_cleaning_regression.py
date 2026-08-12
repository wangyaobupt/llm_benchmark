from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.event_pipeline.regression import (
    _fingerprint,
    _select_cases,
    _verify_cases,
)


class EventCleaningRegressionTest(unittest.TestCase):
    def _event(self, event_id: str, kind: str) -> dict[str, object]:
        return {
            "event_id": event_id,
            "source_row_id": "src:one",
            "subject_id": "patient-1",
            "hadm_id": "admission-1",
            "event_kind": kind,
            "event_time": "2150-01-01T08:00:00",
            "available_time": None,
            "recorded_time": None,
            "evidence_phase": "source_event",
            "quality_flags": ["AVAILABLE_TIME_UNKNOWN"],
            "raw_row_ref": "input.jsonl#L1/mimic_iv_ed.triage[0]",
            "source_table": "ed.triage",
        }

    def test_selection_preserves_event_kind_and_one_to_many_expectations(self) -> None:
        rows = [
            self._event("evt:one", "symptom_reported"),
            self._event("evt:two", "vital_measured"),
        ]
        cases = _select_cases([rows])
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["expected_event_count"], 2)
        self.assertEqual(
            {event["event_kind"] for event in cases[0]["events"]},
            {"symptom_reported", "vital_measured"},
        )
        self.assertEqual(
            cases[0]["identity_sha256"],
            _fingerprint(
                {"subject_id": "patient-1", "hadm_id": "admission-1"}
            ),
        )

    def test_case_verification_detects_time_and_identity_regressions(self) -> None:
        rows = [self._event("evt:one", "symptom_reported")]
        expected = _select_cases([rows])
        columns = tuple(rows[0])
        schema = pa.schema(
            [
                (name, pa.list_(pa.string()) if name == "quality_flags" else pa.string())
                for name in columns
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.mkdir(exist_ok=True)
            pq.write_table(pa.Table.from_pylist(rows, schema=schema), root / "cleaned_events.parquet")
            self.assertEqual(_verify_cases("batch", expected, root), [])

            changed = [dict(rows[0])]
            changed[0]["event_time"] = "2150-01-01T09:00:00"
            pq.write_table(
                pa.Table.from_pylist(changed, schema=schema),
                root / "cleaned_events.parquet",
            )
            errors = _verify_cases("batch", expected, root)
            self.assertTrue(any("event_time: value changed" in error for error in errors))

    def test_committed_fixture_contains_only_identity_and_time_fingerprints(self) -> None:
        fixture_path = (
            Path(__file__).parent / "fixtures" / "event-cleaning-regression.json"
        )
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [batch["batch_id"] for batch in fixture["batches"]],
            ["sample_100", "random_1000_a", "random_1000_b"],
        )

        def walk(value: object) -> None:
            if isinstance(value, dict):
                self.assertNotIn("subject_id", value)
                self.assertNotIn("hadm_id", value)
                for key in ("event_time", "available_time", "recorded_time"):
                    if key in value:
                        self.assertEqual(set(value[key]), {"present", "sha256"})
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(fixture)


if __name__ == "__main__":
    unittest.main()
