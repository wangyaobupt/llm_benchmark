from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eda.analysis.build_raw_coronary_eda_html import build_report, safe_json, validate_metrics


class RawCoronaryEdaHtmlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics_path = Path("docs/reports/mimic-raw-coronary-eda-metrics.json")
        cls.metrics = json.loads(cls.metrics_path.read_text(encoding="utf-8"))

    def test_metrics_contract(self) -> None:
        validate_metrics(self.metrics)
        self.assertEqual(self.metrics["records"], 108_833)
        self.assertEqual(self.metrics["subjects"], 46_062)
        self.assertEqual(self.metrics["schema"]["invalid_records"], 0)
        self.assertEqual(self.metrics["schema"]["forbidden_chartevents"], 0)
        self.assertEqual(sum(self.metrics["orphan_child_rows"].values()), 0)

    def test_safe_json_neutralizes_script_close(self) -> None:
        self.assertNotIn("</script", safe_json({"x": "</script>"}).lower())

    def test_report_is_self_contained_and_interactive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.html"
            build_report(self.metrics_path, output)
            text = output.read_text(encoding="utf-8")
        self.assertIn("<!doctype html>", text.lower())
        self.assertIn("108833", text)
        self.assertIn('id="tableSearch"', text)
        self.assertIn('id="missingThreshold"', text)
        self.assertIn('id="dictionarySearch"', text)
        self.assertIn('id="fieldSearch"', text)
        self.assertIn("mimic_iv_hosp.emar_detail", text)
        self.assertIn("dose_given_unit", text)
        self.assertIn("administrative_end（住院结局）", text)
        self.assertIn("一行 JSON = 一次住院", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("http://", text)


if __name__ == "__main__":
    unittest.main()
