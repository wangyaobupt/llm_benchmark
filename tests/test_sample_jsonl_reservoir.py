from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_pipeline.sample_jsonl_reservoir import (
    JsonlSamplingError,
    reservoir_sample_jsonl,
)


class ReservoirJsonlSamplingTest(unittest.TestCase):
    def test_is_reproducible_and_preserves_selected_source_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jsonl"
            source_lines = [
                json.dumps(
                    {"subject_id": str(index), "hadm_id": str(1000 + index)},
                    separators=(",", ":"),
                ).encode()
                + b"\n"
                for index in range(20)
            ]
            source.write_bytes(b"".join(source_lines))

            first = reservoir_sample_jsonl(
                source,
                root / "first.jsonl",
                root / "first-manifest.json",
                sample_size=5,
                seed=123,
            )
            second = reservoir_sample_jsonl(
                source,
                root / "second.jsonl",
                root / "second-manifest.json",
                sample_size=5,
                seed=123,
            )

            selected_lines = [
                item["source_line_number"] for item in first["selected_records"]
            ]
            self.assertEqual(selected_lines, sorted(selected_lines))
            self.assertEqual(len(selected_lines), len(set(selected_lines)))
            self.assertEqual(first["source"]["record_count"], 20)
            self.assertEqual(first["output"]["record_count"], 5)
            self.assertEqual(
                (root / "first.jsonl").read_bytes(),
                b"".join(source_lines[line_number - 1] for line_number in selected_lines),
            )
            self.assertEqual(
                (root / "first.jsonl").read_bytes(),
                (root / "second.jsonl").read_bytes(),
            )
            self.assertEqual(
                [item["source_line_number"] for item in second["selected_records"]],
                selected_lines,
            )

    def test_rejects_invalid_json_and_removes_partial_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jsonl"
            output = root / "sample.jsonl"
            manifest = root / "manifest.json"
            source.write_bytes(b'{"record":1}\nnot-json\n')

            with self.assertRaisesRegex(JsonlSamplingError, "line 2"):
                reservoir_sample_jsonl(
                    source, output, manifest, sample_size=1, seed=123
                )

            self.assertFalse(output.exists())
            self.assertFalse(manifest.exists())
            self.assertFalse(Path(str(output) + ".partial").exists())

    def test_rejects_source_smaller_than_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jsonl"
            output = root / "sample.jsonl"
            manifest = root / "manifest.json"
            source.write_text('{"record":1}\n', encoding="utf-8")

            with self.assertRaisesRegex(JsonlSamplingError, "fewer than requested"):
                reservoir_sample_jsonl(
                    source, output, manifest, sample_size=2, seed=123
                )

            self.assertFalse(output.exists())
            self.assertFalse(manifest.exists())


if __name__ == "__main__":
    unittest.main()
