from __future__ import annotations

from copy import deepcopy
import importlib
import inspect
import json
from pathlib import Path
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.event_pipeline import (
    CLEANING_LOGIC_VERSION,
    EventWorkflowError,
    run_cleaning,
    run_normalization,
    run_workflow,
)
from data_pipeline.event_pipeline.event_contracts.schemas import (
    EVENT_ARROW_SCHEMA,
    EVENT_JSON_SCHEMA_PATH,
    QUALITY_FLAG_CODES,
)
from data_pipeline.event_pipeline.event_cleaning.source_catalog import (
    SOURCE_CATALOG,
    SOURCE_CATALOG_SHA256,
    SOURCE_CATALOG_VERSION,
)
from data_pipeline.event_pipeline.event_cleaning.validation import (
    EventPipelineError,
    EventValidator,
)
from data_pipeline.event_pipeline.event_quality.audit_cleaning import (
    audit as audit_cleaned,
)
from data_pipeline.event_pipeline.event_quality.audit_normalization import (
    audit as audit_normalized,
)
from data_pipeline.event_pipeline.event_viewer.app import CleaningViewerStore


class EventPipelineTest(unittest.TestCase):
    def test_acceptance_audits_stream_large_inputs(self) -> None:
        audit_cleaning_module = importlib.import_module(
            "data_pipeline.event_pipeline.event_quality.audit_cleaning"
        )
        audit_normalization_module = importlib.import_module(
            "data_pipeline.event_pipeline.event_quality.audit_normalization"
        )
        cleaning_source = inspect.getsource(audit_cleaning_module.audit)
        normalization_source = inspect.getsource(audit_normalization_module.audit)
        self.assertNotIn(".read()", cleaning_source)
        self.assertNotIn(".read()", normalization_source)
        self.assertIn("_iter_parquet_rows", cleaning_source)
        self.assertIn("_JsonlRecordStore", inspect.getsource(audit_cleaning_module))
        self.assertIn("_iter_parquet_rows", normalization_source)
        self.assertIn("sqlite3.connect", normalization_source)

    def _record(self) -> dict[str, object]:
        poe = [
            {
                "poe_id": "1-1",
                "poe_seq": "1",
                "subject_id": "1",
                "hadm_id": "10",
                "ordertime": "2150-01-01 09:00:00",
                "order_type": "Radiology",
                "order_subtype": "General Xray",
                "transaction_type": "New",
                "order_status": "Inactive",
            },
            {
                "poe_id": "1-2",
                "poe_seq": "2",
                "subject_id": "1",
                "hadm_id": "10",
                "ordertime": "2150-01-01 09:05:00",
                "order_type": "Lab",
                "order_subtype": None,
                "transaction_type": "New",
                "order_status": "Inactive",
            },
        ]
        timeline = [
            {
                "subject_id": "1",
                "hadm_id": "10",
                "poe_id": "1-1",
                "poe_seq": "1",
                "event_time": "2150-01-01 09:00:00",
                "action": "create",
                "order_status_raw": "Inactive",
                "clinical_category": {
                    "raw": "Radiology",
                    "subtype_raw": "General Xray",
                },
                "content_specificity": "subtype_only",
                "order_content": {"medications": []},
                "relations": {},
                "quality_flags": [],
            },
            {
                "subject_id": "1",
                "hadm_id": "10",
                "poe_id": "1-2",
                "poe_seq": "2",
                "event_time": "2150-01-01 09:05:00",
                "action": "create",
                "order_status_raw": "Inactive",
                "clinical_category": {"raw": "Lab", "subtype_raw": None},
                "content_specificity": "category_only",
                "order_content": {"medications": []},
                "relations": {},
                "quality_flags": ["category_only_no_specific_order_content"],
            },
        ]
        return {
            "schema": {"name": "mimic_admission_raw", "version": "1.0.0"},
            "subject_id": "1",
            "hadm_id": "10",
            "mimic_iv_hosp": {
                "patients": [],
                "admissions": [],
                "labevents": [
                    {
                        "labevent_id": "100",
                        "subject_id": "1",
                        "hadm_id": "10",
                        "itemid": "51222",
                        "itemid_decoded": {"label": "Hemoglobin"},
                        "charttime": "2150-01-01 08:30:00",
                        "storetime": "2150-01-01 08:45:00",
                        "value": "14.2",
                        "valuenum": "14.2",
                        "valueuom": "g/dL",
                        "ref_range_lower": "13.7",
                        "ref_range_upper": "17.5",
                        "flag": None,
                    }
                ],
                "microbiologyevents": [],
                "poe": poe,
                "poe_detail": [],
                "poe_timeline": timeline,
                "prescriptions": [
                    {
                        "subject_id": "1",
                        "hadm_id": "10",
                        "pharmacy_id": "p1",
                        "poe_id": "1-1",
                        "poe_seq": "1",
                        "drug": "Aspirin",
                        "ndc": "123",
                        "gsn": None,
                        "starttime": "2150-01-01 09:00:00",
                        "stoptime": "2150-01-02 09:00:00",
                        "dose_val_rx": "81",
                        "dose_unit_rx": "mg",
                        "route": "PO",
                    }
                ],
                "pharmacy": [
                    {
                        "subject_id": "1",
                        "hadm_id": "10",
                        "pharmacy_id": "p1",
                        "poe_id": "1-1",
                        "medication": "Aspirin",
                        "status": "Inactive",
                        "entertime": "2150-01-01 09:01:00",
                        "verifiedtime": "2150-01-01 09:02:00",
                    }
                ],
                "emar": [
                    {
                        "subject_id": "1",
                        "hadm_id": "10",
                        "emar_id": "e1",
                        "emar_seq": "1",
                        "poe_id": "1-1",
                        "pharmacy_id": "p1",
                        "medication": "Aspirin",
                        "event_txt": "Not Given",
                        "charttime": "2150-01-01 10:00:00",
                        "storetime": "2150-01-01 10:01:00",
                    }
                ],
                "emar_detail": [],
                "diagnoses_icd": [],
                "hcpcsevents": [],
                "drgcodes": [],
                "services": [
                    {
                        "subject_id": "1",
                        "hadm_id": "10",
                        "transfertime": "2150-01-01 08:00:00",
                        "prev_service": None,
                        "curr_service": "MED",
                    }
                ],
                "transfers": [
                    {
                        "subject_id": "1",
                        "hadm_id": "10",
                        "transfer_id": "t1",
                        "eventtype": "admit",
                        "careunit": "Medicine",
                        "intime": "2150-01-01 08:00:00",
                        "outtime": None,
                    }
                ],
                "procedures_icd": [
                    {
                        "subject_id": "1",
                        "hadm_id": "10",
                        "seq_num": "1",
                        "chartdate": "2150-01-02",
                        "icd_code": "0066",
                        "icd_version": "9",
                        "icd_decoded": {"long_title": "PCI"},
                    }
                ],
            },
            "mimic_iv_icu": {
                "icustays": [],
                "datetimeevents": [],
                "ingredientevents": [],
                "inputevents": [],
                "outputevents": [],
                "procedureevents": [
                    {
                        "subject_id": "1",
                        "hadm_id": "10",
                        "stay_id": "20",
                        "orderid": "o1",
                        "itemid": "225401",
                        "itemid_decoded": {"label": "Procedure"},
                        "starttime": "2150-01-01 11:00:00",
                        "endtime": "2150-01-01 11:30:00",
                        "storetime": "2150-01-01 11:31:00",
                        "value": "1",
                        "valueuom": None,
                    }
                ]
            },
            "mimic_iv_ed": {
                "edstays": [],
                "triage": [
                    {
                        "subject_id": "1",
                        "stay_id": "30",
                        "chiefcomplaint": "Chest pain",
                        "heartrate": "63",
                        "sbp": "127",
                        "dbp": "73",
                        "o2sat": "98",
                        "temperature": None,
                        "resprate": None,
                        "pain": None,
                        "acuity": "2",
                    }
                ],
                "vitalsign": [],
                "diagnosis": [],
                "medrecon": [],
                "pyxis": [],
            },
            "mimic_iv_note": {
                "radiology": [
                    {
                        "note_id": "r1",
                        "subject_id": "1",
                        "hadm_id": "10",
                        "note_type": "RR",
                        "note_seq": "1",
                        "charttime": "2150-01-01 12:00:00",
                        "storetime": "2150-01-01 12:05:00",
                        "text": "Not copied to derived event.",
                    }
                ],
                "radiology_detail": [],
                "discharge": [
                    {
                        "note_id": "d1",
                        "subject_id": "1",
                        "hadm_id": "10",
                        "note_type": "DS",
                        "note_seq": "1",
                        "charttime": "2150-01-03 12:00:00",
                        "storetime": "2150-01-03 12:05:00",
                        "text": "Not copied to derived event.",
                    }
                ],
                "discharge_detail": [],
            },
        }

    def _write_source(self, root: Path, record: dict[str, object]) -> Path:
        path = root / "source.jsonl"
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        return path

    def test_single_workflow_runs_all_gates_and_publishes_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            enriched = self._record()
            raw = deepcopy(enriched)

            def without_enrichment(value):
                if isinstance(value, dict):
                    return {
                        key: without_enrichment(item)
                        for key, item in value.items()
                        if not key.endswith("_decoded") and key != "poe_timeline"
                    }
                if isinstance(value, list):
                    return [without_enrichment(item) for item in value]
                return value

            raw = without_enrichment(raw)
            source_schema = deepcopy(enriched["schema"])
            enriched = {
                "schema": {
                    "name": "mimic_admission_clinical_readable",
                    "version": "1.0.0",
                },
                "source_schema": source_schema,
                **{key: value for key, value in enriched.items() if key != "schema"},
            }
            source = self._write_source(root, enriched)
            raw_path = root / "raw.jsonl"
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            output = root / "workflow-output"
            manifest = run_workflow(
                source,
                raw_path,
                output,
                batch_size=3,
                replay_batch_size=2,
            )
            self.assertEqual(
                manifest["acceptance"],
                {
                    "cleaning": True,
                    "normalization": True,
                    "reproducible": True,
                    "can_start_text_ner": True,
                },
            )
            self.assertTrue((output / "cleaning" / "cleaned_events.parquet").is_file())
            self.assertTrue(
                (output / "normalization" / "normalized_events.parquet").is_file()
            )
            self.assertTrue(
                (output / "quality" / "reproducibility-report.json").is_file()
            )
            saved = json.loads(
                (output / "workflow_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved, manifest)
            audit_result = json.loads(
                (output / "quality" / "normalized-events-acceptance-audit.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                audit_result["inputs"]["normalized_events"],
                "normalization/normalized_events.parquet",
            )
            store = CleaningViewerStore(output, source)
            try:
                self.assertEqual(len(store.catalog()["datasets"]), 7)
            finally:
                store.close()
            second_output = root / "workflow-output-second-location"
            second_manifest = run_workflow(
                source,
                raw_path,
                second_output,
                batch_size=3,
                replay_batch_size=2,
            )
            self.assertEqual(second_manifest, manifest)

    def test_single_workflow_does_not_publish_after_cleaning_audit_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            enriched = self._record()
            source = self._write_source(root, enriched)
            raw = deepcopy(enriched)
            raw["subject_id"] = "different-subject"
            raw["mimic_iv_hosp"].pop("poe_timeline")
            for module in (
                "mimic_iv_hosp",
                "mimic_iv_icu",
                "mimic_iv_ed",
                "mimic_iv_note",
            ):
                for rows in raw[module].values():
                    if not isinstance(rows, list):
                        continue
                    for row in rows:
                        if isinstance(row, dict):
                            for key in list(row):
                                if key.endswith("_decoded"):
                                    del row[key]
            raw_path = root / "bad-raw.jsonl"
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            output = root / "must-not-exist"
            with self.assertRaises(EventWorkflowError):
                run_workflow(
                    source,
                    raw_path,
                    output,
                    batch_size=3,
                    replay_batch_size=2,
                )
            self.assertFalse(output.exists())
            self.assertFalse(any(root.glob(".must-not-exist.tmp-*")))

    def test_two_stage_pipeline_is_traceable_and_category_order_stays_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = self._record()
            source = self._write_source(root, original)
            source_before = source.read_bytes()
            cleaning = run_cleaning(source, root / "cleaning", batch_size=3)
            normalization = run_normalization(
                root / "cleaning" / "cleaned_events.parquet",
                root / "cleaning" / "term_inventory.parquet",
                root / "normalization",
                batch_size=3,
            )

            self.assertEqual(source.read_bytes(), source_before)
            self.assertEqual(cleaning["counts"]["admissions"], 1)
            self.assertEqual(
                cleaning["cleaning_logic_version"], CLEANING_LOGIC_VERSION
            )
            self.assertEqual(cleaning["source_catalog"]["sources"], 33)
            self.assertEqual(cleaning["source_catalog"]["event_sources"], 21)
            self.assertEqual(
                cleaning["source_catalog"]["version"], SOURCE_CATALOG_VERSION
            )
            self.assertEqual(
                cleaning["source_catalog"]["sha256"], SOURCE_CATALOG_SHA256
            )
            self.assertEqual(normalization["counts"]["events"], cleaning["counts"]["events"])
            for filename in (
                "cleaned_events.parquet",
                "cleaning_rejected.parquet",
                "term_inventory.parquet",
            ):
                self.assertTrue((root / "cleaning" / filename).is_file())
            for filename in (
                "normalization_mappings.parquet",
                "normalized_events.parquet",
                "normalization_review_queue.parquet",
            ):
                self.assertTrue((root / "normalization" / filename).is_file())

            cleaned = pq.read_table(root / "cleaning" / "cleaned_events.parquet").to_pylist()
            normalized = pq.read_table(root / "normalization" / "normalized_events.parquet").to_pylist()
            self.assertTrue(all(row["raw_row_ref"].startswith("source.jsonl#L1/") for row in cleaned))
            self.assertTrue(all(row["cleaning_status"] == "accepted" for row in cleaned))
            self.assertTrue(all(row["schema_version"] == "1.2.0" for row in cleaned))
            self.assertTrue(all(row["normalization_status"] is None for row in cleaned))
            chest_pain = next(row for row in normalized if row["event_kind"] == "symptom_reported")
            self.assertEqual(chest_pain["concept_id"], "symptom:chest_pain")
            hemoglobin = next(row for row in normalized if row["event_kind"] == "laboratory_resulted")
            self.assertEqual(hemoglobin["concept_id"], "lab:51222")
            self.assertEqual(hemoglobin["value_numeric"], 14.2)
            self.assertEqual(hemoglobin["normalized_unit"], "g/dL")
            category_only = next(
                row
                for row in normalized
                if row["event_kind"] == "laboratory_ordered"
                and row["content_specificity"] == "category_only"
            )
            self.assertIsNone(category_only["concept_id"])
            self.assertEqual(category_only["normalization_status"], "unresolved")
            self.assertEqual(
                category_only["quality_flags"],
                ["CATEGORY_ONLY_NO_SPECIFIC_ORDER_CONTENT"],
            )
            prescription = next(
                row for row in cleaned if row["event_kind"] == "medication_ordered"
            )
            self.assertEqual(len(prescription["supporting_source_row_ids"]), 2)
            self.assertEqual(
                prescription["supporting_raw_row_refs"],
                [
                    "source.jsonl#L1/mimic_iv_hosp.poe_timeline[0]",
                    "source.jsonl#L1/mimic_iv_hosp.pharmacy[0]",
                ],
            )
            emar = next(row for row in cleaned if row["source_table"] == "hosp.emar")
            self.assertEqual(
                emar["supporting_raw_row_refs"],
                [
                    "source.jsonl#L1/mimic_iv_hosp.poe_timeline[0]",
                    "source.jsonl#L1/mimic_iv_hosp.pharmacy[0]",
                    "source.jsonl#L1/mimic_iv_hosp.prescriptions[0]",
                ],
            )
            self.assertEqual(emar["quality_flags"], [])
            discharge = next(
                row for row in cleaned if row["source_table"] == "note.discharge"
            )
            self.assertEqual(discharge["evidence_phase"], "post_hoc")
            normalized_prescription = next(
                row for row in normalized if row["event_id"] == prescription["event_id"]
            )
            self.assertEqual(normalized_prescription["cleaning_status"], "accepted")
            self.assertEqual(
                normalized_prescription["supporting_raw_row_refs"],
                prescription["supporting_raw_row_refs"],
            )

    def test_independent_acceptance_audit_passes_valid_output_and_blocks_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            enriched = self._record()
            source = self._write_source(root, enriched)
            raw = deepcopy(enriched)
            raw["mimic_iv_hosp"].pop("poe_timeline")
            for module in (
                "mimic_iv_hosp",
                "mimic_iv_icu",
                "mimic_iv_ed",
                "mimic_iv_note",
            ):
                for rows in raw[module].values():
                    if not isinstance(rows, list):
                        continue
                    for row in rows:
                        if isinstance(row, dict):
                            for key in list(row):
                                if key.endswith("_decoded"):
                                    del row[key]
            raw_path = root / "raw.jsonl"
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            cleaning = root / "cleaning"
            run_cleaning(source, cleaning, batch_size=3)

            valid = audit_cleaned(
                cleaning / "cleaned_events.parquet",
                cleaning / "cleaning_rejected.parquet",
                source,
                raw_path,
                cleaning / "source_reconciliation.json",
                cleaning / "run_manifest.json",
                samples_per_table=1,
            )
            self.assertTrue(valid["acceptance"]["can_start_normalization"])

            rows = pq.read_table(cleaning / "cleaned_events.parquet").to_pylist()
            laboratory = next(
                row for row in rows if row["event_kind"] == "laboratory_resulted"
            )
            laboratory["source_available_time"] = "2150-01-01T08:00:00"
            laboratory["available_time"] = "2150-01-01T08:00:00"
            laboratory["time_resolution_reasons"] = [
                "source_available_precedes_event_time"
            ]
            laboratory["quality_flags"] = ["AVAILABLE_BEFORE_EVENT_TIME"]
            corrupted_path = root / "corrupted_events.parquet"
            pq.write_table(
                pa.Table.from_pylist(rows, schema=EVENT_ARROW_SCHEMA),
                corrupted_path,
                compression="zstd",
            )

            corrupted = audit_cleaned(
                corrupted_path,
                cleaning / "cleaning_rejected.parquet",
                source,
                raw_path,
                cleaning / "source_reconciliation.json",
                cleaning / "run_manifest.json",
                samples_per_table=1,
            )
            self.assertFalse(corrupted["acceptance"]["can_start_normalization"])
            self.assertIn(
                "effective_time_inversion",
                corrupted["acceptance"]["blocking_issue_codes"],
            )
            self.assertIn(
                "manifest_hash_mismatch",
                corrupted["acceptance"]["blocking_issue_codes"],
            )

            missing_field_path = root / "missing_available_time.parquet"
            pq.write_table(
                pq.read_table(cleaning / "cleaned_events.parquet").drop(
                    ["available_time"]
                ),
                missing_field_path,
                compression="zstd",
            )
            missing_field = audit_cleaned(
                missing_field_path,
                cleaning / "cleaning_rejected.parquet",
                source,
                raw_path,
                cleaning / "source_reconciliation.json",
                cleaning / "run_manifest.json",
                samples_per_table=1,
            )
            self.assertFalse(
                missing_field["acceptance"]["can_start_normalization"]
            )
            self.assertIn(
                "required_event_field_missing",
                missing_field["acceptance"]["blocking_issue_codes"],
            )

    def test_normalization_acceptance_audit_preserves_facts_and_blocks_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_source(root, self._record())
            cleaning = root / "cleaning"
            normalization = root / "normalization"
            run_cleaning(source, cleaning, batch_size=3)
            run_normalization(
                cleaning / "cleaned_events.parquet",
                cleaning / "term_inventory.parquet",
                normalization,
                batch_size=3,
            )

            valid = audit_normalized(
                cleaning / "cleaned_events.parquet",
                cleaning / "term_inventory.parquet",
                normalization / "normalized_events.parquet",
                normalization / "normalization_mappings.parquet",
                normalization / "normalization_review_queue.parquet",
                normalization / "normalization_manifest.json",
            )
            self.assertTrue(valid["acceptance"]["can_publish_normalization"])

            rows = pq.read_table(
                normalization / "normalized_events.parquet"
            ).to_pylist()
            rows[0]["event_time"] = "2150-01-01T23:59:59"
            corrupted_path = root / "corrupted_normalized_events.parquet"
            pq.write_table(
                pa.Table.from_pylist(rows, schema=EVENT_ARROW_SCHEMA),
                corrupted_path,
                compression="zstd",
            )
            corrupted = audit_normalized(
                cleaning / "cleaned_events.parquet",
                cleaning / "term_inventory.parquet",
                corrupted_path,
                normalization / "normalization_mappings.parquet",
                normalization / "normalization_review_queue.parquet",
                normalization / "normalization_manifest.json",
            )
            self.assertFalse(
                corrupted["acceptance"]["can_publish_normalization"]
            )
            self.assertIn(
                "immutable_event_field_changed",
                corrupted["acceptance"]["blocking_issue_codes"],
            )
            self.assertIn(
                "manifest_contract_mismatch",
                corrupted["acceptance"]["blocking_issue_codes"],
            )

    def test_reconciliation_is_per_source_row_and_known_data_error_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = self._record()
            record["mimic_iv_hosp"]["labevents"][0].pop("itemid_decoded")  # type: ignore[index]
            source = self._write_source(root, record)
            manifest = run_cleaning(source, root / "cleaning")
            rejected = pq.read_table(root / "cleaning" / "cleaning_rejected.parquet").to_pylist()
            self.assertEqual(manifest["counts"]["rejected"], 1)
            self.assertEqual(rejected[0]["reason_code"], "LAB_CONCEPT_MISSING")
            self.assertEqual(rejected[0]["cleaning_status"], "rejected")
            reconciliation = json.loads(
                (root / "cleaning" / "source_reconciliation.json").read_text(encoding="utf-8")
            )
            for table in reconciliation["tables"]:
                self.assertEqual(table["input_rows"], table["classified_source_rows"])

    def test_all_catalog_roles_reconcile_with_complete_support_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = self._record()
            record["mimic_iv_hosp"]["patients"] = [  # type: ignore[index]
                {"subject_id": "1"}
            ]
            record["mimic_iv_hosp"]["admissions"] = [  # type: ignore[index]
                {"subject_id": "1", "hadm_id": "10"}
            ]
            record["mimic_iv_hosp"]["drgcodes"] = [  # type: ignore[index]
                {"subject_id": "1", "hadm_id": "10", "drg_code": "001"}
            ]
            record["mimic_iv_hosp"]["poe_detail"] = [  # type: ignore[index]
                {
                    "subject_id": "1",
                    "poe_id": "1-1",
                    "poe_seq": "1",
                    "field_name": "test",
                    "field_value": "Chest radiograph",
                }
            ]
            record["mimic_iv_hosp"]["emar_detail"] = [  # type: ignore[index]
                {
                    "subject_id": "1",
                    "emar_id": "e1",
                    "emar_seq": "1",
                    "parent_field_ordinal": "1.1",
                    "dose_given": "81",
                    "dose_given_unit": "mg",
                }
            ]
            record["mimic_iv_icu"]["icustays"] = [  # type: ignore[index]
                {"subject_id": "1", "hadm_id": "10", "stay_id": "20"}
            ]
            record["mimic_iv_icu"]["datetimeevents"] = [  # type: ignore[index]
                {
                    "subject_id": "1",
                    "hadm_id": "10",
                    "stay_id": "20",
                    "itemid": "225000",
                    "charttime": "2150-01-01 09:00:00",
                    "value": "2150-01-01 10:00:00",
                }
            ]
            record["mimic_iv_icu"]["inputevents"] = [  # type: ignore[index]
                {
                    "subject_id": "1",
                    "hadm_id": "10",
                    "stay_id": "20",
                    "orderid": "input-1",
                    "linkorderid": "linked-input-1",
                    "itemid": "225158",
                    "itemid_decoded": {"label": "NaCl 0.9%"},
                    "starttime": "2150-01-01 09:00:00",
                    "endtime": "2150-01-01 10:00:00",
                    "storetime": "2150-01-01 10:01:00",
                    "amount": "100",
                    "amountuom": "mL",
                }
            ]
            record["mimic_iv_icu"]["ingredientevents"] = [  # type: ignore[index]
                {
                    "subject_id": "1",
                    "hadm_id": "10",
                    "stay_id": "20",
                    "orderid": "ingredient-1",
                    "linkorderid": "linked-input-1",
                    "itemid": "220490",
                    "starttime": "2150-01-01 09:00:00",
                    "endtime": "2150-01-01 10:00:00",
                    "storetime": "2150-01-01 10:01:00",
                    "amount": "100",
                    "amountuom": "mL",
                }
            ]
            record["mimic_iv_ed"]["edstays"] = [  # type: ignore[index]
                {"subject_id": "1", "hadm_id": "10", "stay_id": "30"}
            ]
            record["mimic_iv_note"]["radiology_detail"] = [  # type: ignore[index]
                {
                    "subject_id": "1",
                    "note_id": "r1",
                    "field_name": "exam_code",
                    "field_value": "C11",
                    "field_ordinal": "1",
                }
            ]
            record["mimic_iv_note"]["discharge_detail"] = [  # type: ignore[index]
                {
                    "subject_id": "1",
                    "note_id": "d1",
                    "field_name": "author",
                    "field_value": "___",
                    "field_ordinal": "1",
                }
            ]
            source = self._write_source(root, record)

            manifest = run_cleaning(source, root / "cleaning")
            reconciliation = json.loads(
                (root / "cleaning" / "source_reconciliation.json").read_text(
                    encoding="utf-8"
                )
            )
            tables = {row["source_table"]: row for row in reconciliation["tables"]}
            self.assertEqual(len(tables), len(SOURCE_CATALOG))
            self.assertEqual(
                reconciliation["source_rows"],
                reconciliation["classified_source_rows"],
            )
            self.assertEqual(reconciliation["unlinked_support_source_rows"], 0)
            for spec in SOURCE_CATALOG:
                row = tables[spec.source_table]
                self.assertEqual(row["role"], spec.role)
                self.assertEqual(row["origin"], spec.origin)
                self.assertEqual(row["input_rows"], row["classified_source_rows"])
                if spec.role == "event":
                    self.assertEqual(
                        row["input_rows"],
                        row["accepted_source_rows"] + row["rejected_source_rows"],
                    )
                elif spec.role == "support":
                    self.assertEqual(row["input_rows"], row["linked_source_rows"])
                    self.assertEqual(row["unlinked_source_rows"], 0)

            expected_raw_rows = sum(
                len(record[spec.module][spec.table])  # type: ignore[index]
                for spec in SOURCE_CATALOG
                if spec.origin == "raw"
            )
            expected_derived_rows = sum(
                len(record[spec.module][spec.table])  # type: ignore[index]
                for spec in SOURCE_CATALOG
                if spec.origin == "derived"
            )
            self.assertEqual(reconciliation["raw_source_rows"], expected_raw_rows)
            self.assertEqual(
                reconciliation["derived_source_rows"], expected_derived_rows
            )
            self.assertEqual(manifest["counts"]["raw_source_rows"], expected_raw_rows)
            self.assertEqual(
                manifest["counts"]["derived_source_rows"], expected_derived_rows
            )
            encounter = pq.read_table(
                root / "cleaning" / "encounter_manifest.parquet"
            ).to_pylist()[0]
            self.assertEqual(encounter["source_row_count"], expected_raw_rows)
            self.assertEqual(encounter["derived_row_count"], expected_derived_rows)

    def test_unlinked_support_row_blocks_normalization_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            enriched = self._record()
            enriched["mimic_iv_hosp"]["poe_detail"] = [  # type: ignore[index]
                {
                    "subject_id": "1",
                    "poe_id": "missing-order",
                    "poe_seq": "999",
                    "field_name": "test",
                    "field_value": "orphan",
                }
            ]
            source = self._write_source(root, enriched)
            raw = deepcopy(enriched)
            raw["mimic_iv_hosp"].pop("poe_timeline")  # type: ignore[index]
            for module in (
                "mimic_iv_hosp",
                "mimic_iv_icu",
                "mimic_iv_ed",
                "mimic_iv_note",
            ):
                for rows in raw[module].values():  # type: ignore[index]
                    if not isinstance(rows, list):
                        continue
                    for row in rows:
                        if isinstance(row, dict):
                            for key in list(row):
                                if key.endswith("_decoded"):
                                    del row[key]
            raw_path = root / "raw.jsonl"
            raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            cleaning = root / "cleaning"
            run_cleaning(source, cleaning)

            result = audit_cleaned(
                cleaning / "cleaned_events.parquet",
                cleaning / "cleaning_rejected.parquet",
                source,
                raw_path,
                cleaning / "source_reconciliation.json",
                cleaning / "run_manifest.json",
            )

            self.assertFalse(result["acceptance"]["can_start_normalization"])
            self.assertIn(
                "supporting_source_row_unlinked",
                result["acceptance"]["blocking_issue_codes"],
            )

    def test_source_time_inversions_are_preserved_clamped_and_explained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = self._record()
            record["mimic_iv_hosp"]["labevents"][0]["storetime"] = (  # type: ignore[index]
                "2150-01-01 08:00:00"
            )
            record["mimic_iv_note"]["radiology"][0]["storetime"] = (  # type: ignore[index]
                "2150-01-01 11:55:00"
            )
            record["mimic_iv_hosp"]["emar"][0]["storetime"] = (  # type: ignore[index]
                "2150-01-01 09:55:00"
            )
            record["mimic_iv_note"]["discharge"][0]["storetime"] = (  # type: ignore[index]
                "2150-01-03 11:55:00"
            )
            record["mimic_iv_icu"]["outputevents"] = [  # type: ignore[index]
                {
                    "subject_id": "1",
                    "hadm_id": "10",
                    "stay_id": "20",
                    "itemid": "226559",
                    "itemid_decoded": {"label": "Urine Output"},
                    "charttime": "2150-01-01 10:00:00",
                    "storetime": "2150-01-01 09:50:00",
                    "value": "250",
                    "valueuom": "mL",
                }
            ]
            record["mimic_iv_icu"]["inputevents"] = [  # type: ignore[index]
                {
                    "subject_id": "1",
                    "hadm_id": "10",
                    "stay_id": "20",
                    "orderid": "input-1",
                    "itemid": "225158",
                    "itemid_decoded": {"label": "NaCl 0.9%"},
                    "starttime": "2150-01-01 09:00:00",
                    "endtime": "2150-01-01 10:00:00",
                    "storetime": "2150-01-01 09:30:00",
                    "amount": "100",
                    "amountuom": "mL",
                }
            ]
            source = self._write_source(root, record)

            manifest = run_cleaning(source, root / "cleaning")
            cleaned = pq.read_table(
                root / "cleaning" / "cleaned_events.parquet"
            ).to_pylist()
            rejected = pq.read_table(
                root / "cleaning" / "cleaning_rejected.parquet"
            ).to_pylist()

            self.assertEqual(manifest["counts"]["rejected"], 0)
            self.assertEqual(rejected, [])
            expected_source_available = {
                "hosp.labevents": "2150-01-01T08:00:00",
                "hosp.emar": "2150-01-01T09:55:00",
                "icu.outputevents": "2150-01-01T09:50:00",
                "note.radiology": "2150-01-01T11:55:00",
                "note.discharge": "2150-01-03T11:55:00",
            }
            for source_table, source_available in expected_source_available.items():
                event = next(
                    row for row in cleaned if row["source_table"] == source_table
                )
                self.assertEqual(event["source_available_time"], source_available)
                self.assertEqual(event["available_time"], event["event_time"])
                self.assertEqual(
                    event["time_resolution_reasons"],
                    [
                        "source_available_precedes_event_time",
                        "event_time_lower_bound",
                    ],
                )
                self.assertIn("AVAILABLE_BEFORE_EVENT_TIME", event["quality_flags"])
                self.assertIn(
                    "AVAILABLE_TIME_CLAMPED_TO_EVENT_TIME",
                    event["quality_flags"],
                )

            icu_input = next(
                row for row in cleaned if row["source_table"] == "icu.inputevents"
            )
            self.assertEqual(icu_input["source_available_time"], "2150-01-01T09:30:00")
            self.assertEqual(icu_input["available_time"], "2150-01-01T10:00:00")
            self.assertEqual(
                icu_input["time_resolution_reasons"],
                ["completion_time_lower_bound"],
            )
            self.assertIn(
                "AVAILABLE_TIME_DERIVED_FROM_COMPLETION",
                icu_input["quality_flags"],
            )
            reconciliation = json.loads(
                (root / "cleaning" / "source_reconciliation.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                reconciliation["source_rows"],
                reconciliation["classified_source_rows"],
            )
            for table in reconciliation["tables"]:
                self.assertEqual(table["input_rows"], table["classified_source_rows"])

    def test_pharmacy_missing_medication_is_resolved_by_native_pharmacy_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = self._record()
            record["mimic_iv_hosp"]["pharmacy"][0]["medication"] = None  # type: ignore[index]
            record["mimic_iv_hosp"]["emar"][0]["medication"] = None  # type: ignore[index]
            record["mimic_iv_hosp"]["emar_detail"] = [  # type: ignore[index]
                {
                    "subject_id": "1",
                    "emar_id": "e1",
                    "emar_seq": "1",
                    "parent_field_ordinal": "1.1",
                    "pharmacy_id": "p1",
                    "dose_given": "81",
                    "dose_given_unit": "mg",
                }
            ]
            source = self._write_source(root, record)

            manifest = run_cleaning(source, root / "cleaning")
            cleaned = pq.read_table(
                root / "cleaning" / "cleaned_events.parquet"
            ).to_pylist()
            rejected = pq.read_table(
                root / "cleaning" / "cleaning_rejected.parquet"
            ).to_pylist()

            self.assertEqual(manifest["counts"]["rejected"], 0)
            self.assertEqual(rejected, [])
            pharmacy = next(
                row for row in cleaned if row["source_table"] == "hosp.pharmacy"
            )
            self.assertEqual(pharmacy["source_label"], "Aspirin")
            self.assertEqual(
                pharmacy["quality_flags"],
                ["MEDICATION_LABEL_RESOLVED_FROM_LINKED_SOURCE"],
            )
            self.assertEqual(
                pharmacy["supporting_raw_row_refs"],
                [
                    "source.jsonl#L1/mimic_iv_hosp.poe_timeline[0]",
                    "source.jsonl#L1/mimic_iv_hosp.prescriptions[0]",
                ],
            )
            pharmacy_value = json.loads(pharmacy["value_structured_json"])
            self.assertIsNone(pharmacy_value["medication_raw"])
            self.assertEqual(
                pharmacy_value["medication_resolution"],
                "prescriptions.drug_by_pharmacy_id",
            )
            emar = next(row for row in cleaned if row["source_table"] == "hosp.emar")
            self.assertEqual(emar["source_label"], "Aspirin")
            self.assertEqual(
                emar["quality_flags"],
                ["MEDICATION_LABEL_RESOLVED_FROM_LINKED_SOURCE"],
            )
            self.assertEqual(
                emar["supporting_raw_row_refs"][-1],
                "source.jsonl#L1/mimic_iv_hosp.emar_detail[0]",
            )
            self.assertEqual(
                json.loads(emar["value_structured_json"])[
                    "linked_emar_detail_count"
                ],
                1,
            )
            self.assertEqual(
                json.loads(emar["value_structured_json"])[
                    "medication_resolution"
                ],
                "linked_source_by_pharmacy_id",
            )

    def test_pharmacy_rejects_only_after_native_link_is_ambiguous_or_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ambiguous = self._record()
            ambiguous["mimic_iv_hosp"]["pharmacy"][0]["medication"] = None  # type: ignore[index]
            second = deepcopy(ambiguous["mimic_iv_hosp"]["prescriptions"][0])  # type: ignore[index]
            second["drug"] = "Clopidogrel"
            second["ndc"] = "456"
            ambiguous["mimic_iv_hosp"]["prescriptions"].append(second)  # type: ignore[index]
            first_source = self._write_source(root, ambiguous)
            first_manifest = run_cleaning(first_source, root / "ambiguous")
            first_rejected = pq.read_table(
                root / "ambiguous" / "cleaning_rejected.parquet"
            ).to_pylist()
            self.assertEqual(first_manifest["counts"]["rejected"], 1)
            self.assertEqual(
                first_rejected[0]["reason_code"],
                "PHARMACY_MEDICATION_AMBIGUOUS",
            )

            unresolved = self._record()
            unresolved["mimic_iv_hosp"]["pharmacy"][0]["medication"] = None  # type: ignore[index]
            unresolved["mimic_iv_hosp"]["prescriptions"] = []  # type: ignore[index]
            second_source = root / "unresolved.jsonl"
            second_source.write_text(json.dumps(unresolved) + "\n", encoding="utf-8")
            second_manifest = run_cleaning(second_source, root / "unresolved")
            second_rejected = pq.read_table(
                root / "unresolved" / "cleaning_rejected.parquet"
            ).to_pylist()
            self.assertEqual(second_manifest["counts"]["rejected"], 1)
            self.assertEqual(
                second_rejected[0]["reason_code"],
                "PHARMACY_MEDICATION_UNRESOLVED",
            )

    def test_medication_links_preserve_poe_conflicts_and_require_exact_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = self._record()
            record["mimic_iv_hosp"]["prescriptions"][0]["poe_seq"] = "999"  # type: ignore[index]
            record["mimic_iv_hosp"]["emar"][0]["poe_id"] = "1-2"  # type: ignore[index]
            source = self._write_source(root, record)
            run_cleaning(source, root / "cleaning")
            cleaned = pq.read_table(
                root / "cleaning" / "cleaned_events.parquet"
            ).to_pylist()

            prescription = next(
                row
                for row in cleaned
                if row["source_table"] == "hosp.prescriptions"
            )
            self.assertIsNone(prescription["event_time"])
            self.assertIn("ORDER_TIME_UNRESOLVED", prescription["quality_flags"])
            self.assertNotIn(
                "source.jsonl#L1/mimic_iv_hosp.poe_timeline[0]",
                prescription["supporting_raw_row_refs"],
            )

            emar = next(row for row in cleaned if row["source_table"] == "hosp.emar")
            self.assertIn("PHARMACY_POE_ID_CONFLICT", emar["quality_flags"])
            self.assertEqual(
                json.loads(emar["value_structured_json"])["poe_id"], "1-2"
            )
            self.assertIn(
                "source.jsonl#L1/mimic_iv_hosp.poe_timeline[1]",
                emar["supporting_raw_row_refs"],
            )

    def test_stable_ids_do_not_depend_on_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_source(root, deepcopy(self._record()))
            run_cleaning(source, root / "first", batch_size=2)
            run_cleaning(source, root / "second", batch_size=7)
            first = pq.read_table(root / "first" / "cleaned_events.parquet").column("event_id").to_pylist()
            second = pq.read_table(root / "second" / "cleaned_events.parquet").column("event_id").to_pylist()
            self.assertEqual(first, second)
            self.assertEqual(len(first), len(set(first)))

    def test_validator_requires_explanation_and_rejects_effective_inversion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_source(root, self._record())
            run_cleaning(source, root / "cleaning")
            event = pq.read_table(
                root / "cleaning" / "cleaned_events.parquet"
            ).to_pylist()[0]
            known_source_ids = {
                event["source_row_id"],
                *event["supporting_source_row_ids"],
            }
            validator = EventValidator()

            missing_explanation = dict(event)
            missing_explanation["event_time"] = "2150-01-01T10:00:00"
            missing_explanation["source_available_time"] = "2149-01-01T00:00:00"
            missing_explanation["available_time"] = "2150-01-01T10:00:00"
            missing_explanation["quality_flags"] = []
            with self.assertRaises(EventPipelineError) as raised:
                validator.validate(missing_explanation, known_source_ids)
            self.assertEqual(
                raised.exception.reason_code,
                "TIME_INVERSION_EXPLANATION_MISSING",
            )

            effective_inversion = dict(event)
            effective_inversion["event_time"] = "2150-01-01T10:00:00"
            effective_inversion["source_available_time"] = "2150-01-01T09:00:00"
            effective_inversion["available_time"] = "2150-01-01T09:00:00"
            effective_inversion["time_resolution_reasons"] = [
                "source_available_precedes_event_time"
            ]
            effective_inversion["quality_flags"] = ["AVAILABLE_BEFORE_EVENT_TIME"]
            with self.assertRaises(EventPipelineError) as raised:
                validator.validate(effective_inversion, known_source_ids)
            self.assertEqual(
                raised.exception.reason_code,
                "EFFECTIVE_AVAILABLE_BEFORE_EVENT_TIME",
            )

    def test_unknown_quality_flag_stops_cleaning_without_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = self._record()
            record["mimic_iv_hosp"]["poe_timeline"][0]["quality_flags"] = [  # type: ignore[index]
                "new_unknown_flag"
            ]
            source = self._write_source(root, record)
            output = root / "cleaning"

            with self.assertRaisesRegex(ValueError, "unknown quality flag"):
                run_cleaning(source, output)

            self.assertFalse(output.exists())

    def test_quality_flag_enum_matches_json_schema(self) -> None:
        schema = json.loads(EVENT_JSON_SCHEMA_PATH.read_text(encoding="utf-8"))
        schema_codes = tuple(
            schema["properties"]["quality_flags"]["items"]["enum"]
        )
        self.assertEqual(schema_codes, QUALITY_FLAG_CODES)


if __name__ == "__main__":
    unittest.main()
