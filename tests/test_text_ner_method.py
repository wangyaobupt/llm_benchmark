from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from data_pipeline.text_ner.annotation_contracts import (
    SECTION_ANNOTATION_SCHEMA_VERSION,
)
from data_pipeline.text_ner.method_contracts import MethodContractError
from data_pipeline.text_ner.method_evaluation import evaluate_section_annotations
from data_pipeline.text_ner.method_run import prepare_method_run
from data_pipeline.text_ner.method_run_audit import audit_method_run
from data_pipeline.text_ner.rule_baseline import rule_baseline_annotation


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
METHOD_CONFIG = REPOSITORY_ROOT / "config" / "text_ner" / "exploratory-two-stage.json"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _annotation(text: str, suffix: str) -> dict[str, object]:
    return {
        "schema_version": SECTION_ANNOTATION_SCHEMA_VERSION,
        "manifest_row_id": f"manifest:{suffix}",
        "document_id": f"document:{suffix}",
        "section_id": f"section:{suffix}",
        "section_text_sha256": _sha256(text),
        "mentions": [],
        "relations": [],
    }


def _task(text: str, suffix: str, slot: str) -> dict[str, object]:
    return {
        "task_id": f"task:{suffix}:{slot}",
        "annotation_unit_id": f"unit:{suffix}",
        "annotator_slot": slot,
        "partition": "calibration",
        "release_status": "released",
        "manifest_row_id": f"manifest:{suffix}",
        "document_id": f"document:{suffix}",
        "section_id": f"section:{suffix}",
        "source_table": "note.radiology",
        "section_name": "findings",
        "section_text": text,
        "section_text_sha256": _sha256(text),
        "annotation": _annotation(text, suffix),
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _package(root: Path) -> Path:
    package = root / "package"
    texts = ["Tube tip is 3 cm above carina today.", "No interval change."]
    a = [_task(text, str(index), "annotator_a") for index, text in enumerate(texts)]
    # Preserve matching unit IDs while changing only deterministic presentation order.
    b = [_task(texts[index], str(index), "annotator_b") for index in reversed(range(len(texts)))]
    _write_jsonl(package / "calibration" / "annotator_a" / "tasks.jsonl", a)
    _write_jsonl(package / "calibration" / "annotator_b" / "tasks.jsonl", b)
    (package / "run_manifest.json").write_text(
        json.dumps({"schema_version": "test-package/1.0.0"}) + "\n",
        encoding="utf-8",
    )
    # Invalid locked content proves method preparation never reads evaluation.
    evaluation = package / "evaluation" / "tasks.locked.jsonl"
    evaluation.parent.mkdir(parents=True)
    evaluation.write_text("not-json and must remain unread\n", encoding="utf-8")
    return package


def _mention(
    local_id: str,
    surface: str,
    start: int,
    entity_type: str,
    *,
    assertion: str = "present",
    temporality: str = "current",
    experiencer: str = "patient",
) -> dict[str, object]:
    return {
        "local_id": local_id,
        "surface_text": surface,
        "section_span_start": start,
        "section_span_end": start + len(surface),
        "entity_type": entity_type,
        "assertion": assertion,
        "temporality": temporality,
        "experiencer": experiencer,
        "laterality": "not_applicable",
        "severity": "not_applicable",
        "trend": "not_applicable",
        "normalization_status": "unattempted",
        "concept_id": None,
        "preferred_name": None,
        "terminology": None,
        "quality_flags": [],
    }


class TextNerMethodTests(unittest.TestCase):
    def test_prepare_is_calibration_only_deterministic_and_model_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = _package(root)
            first = prepare_method_run(package, METHOD_CONFIG, root / "run-one")
            second = prepare_method_run(package, METHOD_CONFIG, root / "run-two")
            self.assertEqual(first["run_id"], second["run_id"])
            self.assertEqual(first["outputs"], second["outputs"])
            self.assertEqual(first["execution"]["model_calls"], 0)
            self.assertEqual(first["input"]["evaluation_access_count"], 0)
            metrics = json.loads(
                (root / "run-one" / "evaluation" / "metrics.json").read_text()
            )
            self.assertEqual(metrics["status"], "not_evaluable")
            self.assertIsNone(metrics["metrics"])

    def test_explicit_execute_fails_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = _package(root)
            output = root / "execute"
            with self.assertRaisesRegex(MethodContractError, "MODEL_EXECUTION_NOT_AUTHORIZED"):
                prepare_method_run(package, METHOD_CONFIG, output, execute=True)
            self.assertFalse(output.exists())

    def test_non_calibration_task_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = _package(root)
            a_path = package / "calibration" / "annotator_a" / "tasks.jsonl"
            rows = [json.loads(line) for line in a_path.read_text().splitlines()]
            rows[0]["partition"] = "evaluation"
            _write_jsonl(a_path, rows)
            with self.assertRaisesRegex(MethodContractError, "METHOD_NON_CALIBRATION_INPUT"):
                prepare_method_run(package, METHOD_CONFIG, root / "run")

    def test_audit_replays_without_raw_text_in_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = _package(root)
            run = root / "run"
            prepare_method_run(package, METHOD_CONFIG, run)
            report_path = root / "report.md"
            result = audit_method_run(
                package,
                METHOD_CONFIG,
                run,
                replay_directory=root / "replay",
                output_markdown=report_path,
            )
            self.assertTrue(result["passed"])
            report = report_path.read_text(encoding="utf-8")
            self.assertNotIn("Tube tip", report)
            self.assertEqual(result["counts"]["model_calls"], 0)

    def test_rule_baseline_is_deliberately_limited(self) -> None:
        text = "Possible edema; tube is 3 cm above carina today."
        task = _task(text, "baseline", "annotator_a")
        annotation = rule_baseline_annotation(task)
        observed = {(m["surface_text"], m["entity_type"]) for m in annotation["mentions"]}
        self.assertEqual(
            observed,
            {("3 cm", "measurement"), ("today", "temporal_expression")},
        )
        self.assertFalse(annotation["relations"])

    def test_metrics_refuse_empty_gold_and_score_real_gold(self) -> None:
        text = "edema"
        base = _annotation(text, "metric")
        base["mentions"] = [_mention("m1", "edema", 0, "imaging_finding")]
        record = {"source_table": "note.radiology", "annotation": base}
        refused = evaluate_section_annotations([record], None)
        self.assertEqual(refused["status"], "not_evaluable")
        self.assertIsNone(refused["metrics"])
        scored = evaluate_section_annotations([record], [record])
        self.assertEqual(scored["status"], "evaluated")
        self.assertEqual(scored["metrics"]["overall"]["exact_span_type"]["f1"], 1.0)
        self.assertEqual(scored["metrics"]["overall"]["relations_exact"]["f1"], 0.0)

    def test_relaxed_matching_and_critical_error_remain_visible(self) -> None:
        text = "pulmonary edema"
        predicted_annotation = _annotation(text, "relaxed")
        predicted_annotation["mentions"] = [
            _mention("m1", text, 0, "imaging_finding", assertion="present")
        ]
        gold_annotation = _annotation(text, "relaxed")
        gold_annotation["mentions"] = [
            _mention("m1", "edema", 10, "imaging_finding", assertion="absent")
        ]
        predicted = {
            "source_table": "note.radiology",
            "annotation": predicted_annotation,
        }
        gold = {"source_table": "note.radiology", "annotation": gold_annotation}
        scored = evaluate_section_annotations([predicted], [gold])
        overall = scored["metrics"]["overall"]
        self.assertEqual(overall["exact_span_type"]["f1"], 0.0)
        self.assertEqual(overall["relaxed_span_type"]["f1"], 1.0)
        # Critical errors require identical entity identity; a boundary mismatch stays
        # visible in span metrics instead of being relabelled as a clinical error.
        self.assertEqual(overall["critical_errors"]["negated_as_present"], 0)

        gold_annotation["mentions"] = [
            _mention("m1", text, 0, "imaging_finding", assertion="absent")
        ]
        exact_scored = evaluate_section_annotations([predicted], [gold])
        self.assertEqual(
            exact_scored["metrics"]["overall"]["critical_errors"][
                "negated_as_present"
            ],
            1,
        )


if __name__ == "__main__":
    unittest.main()
