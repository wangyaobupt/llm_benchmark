from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest

from data_pipeline.event_pipeline.ids import SourceIdentityError, build_source_row_id
from data_pipeline.event_pipeline.pipeline import run_cleaning
from data_pipeline.event_pipeline.source_registry import (
    EVENT_SOURCE_REGISTRY,
    REGISTERED_SOURCE_PATHS,
    SOURCE_BY_PATH,
    SOURCE_CATALOG,
    SOURCE_CATALOG_SHA256,
    SOURCE_CATALOG_VERSION,
    TIME_POLICIES,
    UPSTREAM_EXCLUDED_SOURCES,
    validate_source_catalog,
)
from data_pipeline.event_pipeline.transformers import TRANSFORMERS
from data_pipeline.event_pipeline.validation import (
    EventPipelineError,
    validate_admission_shell,
)


class EventSourceCatalogTest(unittest.TestCase):
    def _empty_admission(self) -> dict[str, object]:
        modules: dict[str, dict[str, list[object]]] = {
            "mimic_iv_hosp": {},
            "mimic_iv_icu": {},
            "mimic_iv_ed": {},
            "mimic_iv_note": {},
        }
        for spec in SOURCE_CATALOG:
            modules[spec.module][spec.table] = []
        return {
            "schema": {"name": "mimic_admission_raw", "version": "1.0.0"},
            "subject_id": "1",
            "hadm_id": "10",
            **modules,
        }

    def test_catalog_is_complete_and_fact_ownership_is_closed(self) -> None:
        validate_source_catalog()
        self.assertEqual(len(SOURCE_CATALOG), 33)
        self.assertEqual(
            Counter(spec.role for spec in SOURCE_CATALOG),
            {"event": 21, "support": 6, "context": 6},
        )
        self.assertEqual(
            EVENT_SOURCE_REGISTRY,
            tuple(spec for spec in SOURCE_CATALOG if spec.role == "event"),
        )
        self.assertEqual(len(REGISTERED_SOURCE_PATHS), 33)
        self.assertEqual(len(SOURCE_CATALOG_SHA256), 64)
        self.assertEqual(SOURCE_CATALOG_VERSION, "1.1.0")
        self.assertEqual(
            {
                spec.source_table
                for spec in SOURCE_CATALOG
                if spec.identity_strategy == "canonical_row_hash_with_occurrence"
            },
            {
                "hosp.prescriptions",
                "hosp.emar_detail",
                "hosp.drgcodes",
                "icu.datetimeevents",
                "icu.outputevents",
                "ed.medrecon",
                "note.radiology_detail",
            },
        )

        event_paths = {spec.source_table for spec in EVENT_SOURCE_REGISTRY}
        for spec in SOURCE_CATALOG:
            self.assertIn(spec.time_policy, TIME_POLICIES)
            self.assertTrue(spec.inclusion_reason)
            if spec.role == "event":
                self.assertEqual(spec.fact_owner, spec.source_table)
                self.assertIn(spec.transformer_name, TRANSFORMERS)
            else:
                self.assertIsNone(spec.transformer_name)
            if spec.role == "support":
                self.assertIn(spec.fact_owner, event_paths)

        self.assertEqual(SOURCE_BY_PATH[("mimic_iv_hosp", "poe")].role, "support")
        self.assertEqual(
            SOURCE_BY_PATH[("mimic_iv_hosp", "poe_timeline")].role,
            "event",
        )
        self.assertEqual(
            SOURCE_BY_PATH[("mimic_iv_icu", "ingredientevents")].fact_owner,
            "icu.inputevents",
        )
        self.assertEqual(
            SOURCE_BY_PATH[("mimic_iv_icu", "datetimeevents")].role,
            "context",
        )
        self.assertEqual(
            set(UPSTREAM_EXCLUDED_SOURCES),
            {"icu.chartevents", "hosp.omr"},
        )

    def test_unknown_missing_and_non_array_tables_fail_before_routing(self) -> None:
        unknown = self._empty_admission()
        unknown["mimic_iv_hosp"]["new_table"] = []  # type: ignore[index]
        with self.assertRaises(EventPipelineError) as raised:
            validate_admission_shell(unknown, 1)
        self.assertEqual(raised.exception.reason_code, "UNREGISTERED_SOURCE_TABLE")

        missing = self._empty_admission()
        del missing["mimic_iv_hosp"]["labevents"]  # type: ignore[index]
        with self.assertRaises(EventPipelineError) as raised:
            validate_admission_shell(missing, 1)
        self.assertEqual(raised.exception.reason_code, "REQUIRED_SOURCE_TABLE_MISSING")

        non_array = self._empty_admission()
        non_array["mimic_iv_ed"]["triage"] = {}  # type: ignore[index]
        with self.assertRaises(EventPipelineError) as raised:
            validate_admission_shell(non_array, 1)
        self.assertEqual(raised.exception.reason_code, "SOURCE_TABLE_NOT_ARRAY")

    def test_pipeline_rejects_unknown_table_without_publishing_output(self) -> None:
        admission = self._empty_admission()
        admission["mimic_iv_hosp"]["future_table"] = []  # type: ignore[index]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.jsonl"
            source.write_text(json.dumps(admission) + "\n", encoding="utf-8")
            output = root / "cleaning"
            with self.assertRaises(EventPipelineError) as raised:
                run_cleaning(source, output)
            self.assertEqual(raised.exception.reason_code, "UNREGISTERED_SOURCE_TABLE")
            self.assertFalse(output.exists())

    def test_identity_strategy_never_silently_falls_back(self) -> None:
        lab = SOURCE_BY_PATH[("mimic_iv_hosp", "labevents")]
        with self.assertRaises(SourceIdentityError) as raised:
            build_source_row_id(lab, {"labevent_id": None})
        self.assertEqual(raised.exception.reason_code, "SOURCE_IDENTITY_KEY_MISSING")

        medication_history = SOURCE_BY_PATH[("mimic_iv_ed", "medrecon")]
        row = {"subject_id": "1", "stay_id": "2", "name": "Aspirin"}
        first = build_source_row_id(
            medication_history,
            row,
            duplicate_occurrence_ordinal=0,
        )
        second = build_source_row_id(
            medication_history,
            row,
            duplicate_occurrence_ordinal=1,
        )
        self.assertNotEqual(first, second)

    def test_local_sample_100_contains_exact_catalog_when_available(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "validation"
            / "mimic-admission-raw-coronary-sample-100-poe-timeline-decoded.jsonl"
        )
        if not source.is_file():
            self.skipTest("licensed local sample is unavailable")
        lines = 0
        observed: set[tuple[str, str]] = set()
        with source.open("r", encoding="utf-8") as handle:
            for lines, raw_line in enumerate(handle, 1):
                admission = json.loads(raw_line)
                validate_admission_shell(admission, lines)
                for module in (
                    "mimic_iv_hosp",
                    "mimic_iv_icu",
                    "mimic_iv_ed",
                    "mimic_iv_note",
                ):
                    observed.update((module, table) for table in admission[module])
        self.assertEqual(lines, 100)
        self.assertEqual(observed, REGISTERED_SOURCE_PATHS)


if __name__ == "__main__":
    unittest.main()
