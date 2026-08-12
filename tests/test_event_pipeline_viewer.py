from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.event_pipeline.event_viewer.app import (
    CleaningViewerStore,
    _make_handler,
)


class CleaningViewerStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cleaning = self.root / "data" / "derived" / "sample" / "cleaning"
        self.validation = self.root / "data" / "validation"
        self.cleaning.mkdir(parents=True)
        self.validation.mkdir(parents=True)

        source_name = "sample.jsonl"
        source = self.validation / source_name
        source.write_text(
            json.dumps(
                {
                    "mimic_iv_ed": {
                        "triage": [
                            {"subject_id": 10, "chiefcomplaint": "Chest pain"}
                        ]
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        raw_ref = f"{source_name}#L1/mimic_iv_ed.triage[0]"
        self._write_parquet(
            "cleaned_events.parquet",
            [
                {
                    "event_id": "event-1",
                    "subject_id": "10",
                    "hadm_id": "100",
                    "event_kind": "symptom_reported",
                    "source_table": "ed.triage",
                    "source_label": "Chest pain",
                    "value_text": None,
                    "jsonl_line_number": 1,
                    "source_array_index": 0,
                    "raw_row_ref": raw_ref,
                },
                {
                    "event_id": "event-2",
                    "subject_id": "20",
                    "hadm_id": "200",
                    "event_kind": "laboratory_resulted",
                    "source_table": "hosp.labevents",
                    "source_label": "Hemoglobin",
                    "value_text": "14.2",
                    "jsonl_line_number": 2,
                    "source_array_index": 0,
                    "raw_row_ref": f"{source_name}#L2/mimic_iv_hosp.labevents[0]",
                },
            ],
        )
        self._write_parquet(
            "cleaning_rejected.parquet",
            [
                {
                    "subject_id": "10",
                    "hadm_id": "100",
                    "source_row_id": "row-1",
                    "source_table": "hosp.pharmacy",
                    "reason_code": "missing_required_field",
                    "message": "missing status",
                    "raw_row_ref": f"{source_name}#L1/mimic_iv_hosp.pharmacy[0]",
                }
            ],
        )
        self._write_parquet(
            "term_inventory.parquet",
            [
                {
                    "entity_type": "symptom",
                    "source_concept_id": None,
                    "normalized_source_label": "chest pain",
                    "source_label_example": "Chest pain",
                    "unit": None,
                    "event_count": 1,
                    "first_event_id": "event-1",
                }
            ],
        )
        self._write_parquet(
            "encounter_manifest.parquet",
            [
                {
                    "subject_id": "10",
                    "hadm_id": "100",
                    "jsonl_line_number": 1,
                    "source_row_count": 1,
                    "derived_row_count": 1,
                    "event_count": 1,
                    "rejected_count": 0,
                }
            ],
        )
        (self.cleaning / "run_manifest.json").write_text(
            json.dumps({"input": {"filename": source_name}, "counts": {"events": 2}}),
            encoding="utf-8",
        )
        (self.cleaning / "source_reconciliation.json").write_text(
            json.dumps({"source_rows": 2, "classified_source_rows": 2}),
            encoding="utf-8",
        )
        self.store = CleaningViewerStore(self.cleaning)

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def _write_parquet(self, filename: str, rows: list[dict[str, object]]) -> None:
        pq.write_table(pa.Table.from_pylist(rows), self.cleaning / filename)

    def test_catalog_reports_all_files_and_auto_resolves_source(self) -> None:
        catalog = self.store.catalog()
        self.assertTrue(catalog["read_only"])
        self.assertEqual(4, len(catalog["datasets"]))
        self.assertEqual(str((self.validation / "sample.jsonl").resolve()), catalog["source_jsonl"])
        self.assertEqual(2, catalog["datasets"][0]["count"])

    def test_catalog_includes_optional_review_package(self) -> None:
        review = self.cleaning / "review"
        review.mkdir()
        pq.write_table(
            pa.Table.from_pylist(
                [
                    {
                        "review_sample_id": "sample-1",
                        "event_id": "event-1",
                        "sample_reasons": ["TERM_UNRESOLVED"],
                        "raw_row_ref": "sample.jsonl#L1/mimic_iv_ed.triage[0]",
                    }
                ]
            ),
            review / "normalization_review_samples.parquet",
        )
        pq.write_table(
            pa.Table.from_pylist(
                [
                    {
                        "review_id": "mapping-1",
                        "priority_rank": 1,
                        "review_scope": "required",
                        "review_status": "pending",
                    }
                ]
            ),
            review / "normalization_review_decisions.parquet",
        )
        self.store.close()
        self.store = CleaningViewerStore(self.cleaning)
        catalog = self.store.catalog()
        self.assertEqual(6, len(catalog["datasets"]))
        self.assertEqual(
            {
                "normalization_review_samples",
                "normalization_review_decisions",
            },
            {item["name"] for item in catalog["datasets"]}
            - {
                "cleaned_events",
                "cleaning_rejected",
                "term_inventory",
                "encounter_manifest",
            },
        )

    def test_query_filters_searches_and_pages_without_loading_all_rows(self) -> None:
        filtered = self.store.query(
            "cleaned_events", filters={"subject_id": "10"}, page_size=20
        )
        self.assertEqual(1, filtered["total"])
        self.assertEqual("Chest pain", filtered["rows"][0]["source_label"])

        searched = self.store.query("cleaned_events", search="hemo", page_size=20)
        self.assertEqual(1, searched["total"])
        self.assertEqual("event-2", searched["rows"][0]["event_id"])

        empty_page = self.store.query("cleaned_events", page=2, page_size=20)
        self.assertEqual(2, empty_page["total"])
        self.assertEqual([], empty_page["rows"])

    def test_query_rejects_unknown_dataset_filter_and_page_size(self) -> None:
        with self.assertRaises(ValueError):
            self.store.query("read_csv_auto('/secret')")
        with self.assertRaises(ValueError):
            self.store.query(
                "cleaned_events", filters={"event_id OR 1=1": "x"}, page_size=20
            )
        with self.assertRaises(ValueError):
            self.store.query("cleaned_events", page_size=99999)

    def test_raw_reference_returns_exact_original_array_element(self) -> None:
        result = self.store.source_row(
            "sample.jsonl#L1/mimic_iv_ed.triage[0]"
        )
        self.assertEqual("Chest pain", result["source_row"]["chiefcomplaint"])
        self.assertEqual(0, result["source_array_index"])
        with self.assertRaises(ValueError):
            self.store.source_row("other.jsonl#L1/mimic_iv_ed.triage[0]")


class ViewerHttpTest(CleaningViewerStoreTest):
    def setUp(self) -> None:
        super().setUp()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        super().tearDown()

    def _get_json(self, path: str) -> dict[str, object]:
        with urlopen(self.base + path, timeout=3) as response:
            return json.loads(response.read())

    def test_http_catalog_rows_page_and_source(self) -> None:
        self.assertTrue(self._get_json("/api/catalog")["read_only"])
        rows = self._get_json(
            "/api/rows?dataset=cleaned_events&page_size=20&subject_id=10"
        )
        self.assertEqual(1, rows["total"])
        source = self._get_json(
            "/api/source?raw_row_ref="
            + quote("sample.jsonl#L1/mimic_iv_ed.triage[0]")
        )
        self.assertEqual("Chest pain", source["source_row"]["chiefcomplaint"])
        with urlopen(self.base + "/", timeout=3) as response:
            self.assertIn("MIMIC 事件流水线浏览器", response.read().decode("utf-8"))

    def test_http_rejects_write_requests(self) -> None:
        request = Request(self.base + "/api/rows", data=b"{}", method="POST")
        with self.assertRaises(HTTPError) as context:
            urlopen(request, timeout=3)
        self.assertEqual(405, context.exception.code)


if __name__ == "__main__":
    unittest.main()
