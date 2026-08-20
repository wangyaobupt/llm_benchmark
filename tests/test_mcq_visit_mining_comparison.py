from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_pipeline.mcq_visit_mining.comparison import (
    ComparisonError,
    build_comparison,
    canonical_rule_key,
    discover_complete_runs,
    render_html,
    write_outputs,
)
from data_pipeline.mcq_visit_mining.families import FAMILY_IDS


def _rule(family: str, profile: str, suffix: str) -> dict:
    return {
        "family": family,
        "profile": profile,
        "condition_feature_ids": ["sex:F", f"symptom:{suffix}"],
        "condition_display_names": ["F", suffix],
        "target_outcome_id": f"outcome:{suffix}",
        "target_outcome_name": suffix,
        "n_x": 10,
        "n_xy": 8,
        "conditional_probability": 0.8,
        "smoothed_probability": 0.75,
        "lift": 2.0,
        "psr": 1.5,
        "tfidf": 1.2,
        "idf": 1.6,
        "wilson_lower": 0.5,
        "fdr_q": 0.01,
        "bootstrap_stability": 0.9,
        "score": 2.5,
    }


def _write_run(root: Path, directory: str, profile: str, *, missing_family: str | None = None) -> None:
    for family in FAMILY_IDS:
        if family == missing_family:
            continue
        family_dir = root / directory / family
        family_dir.mkdir(parents=True)
        summary = {
            "family": family,
            "profile": profile,
            "rank_key": "smoothed_probability",
            "transactions": 10,
            "tested_pairs": 12,
            "accepted": 1,
            "rejected": 2,
            "transactions_sha256": "same-transactions",
        }
        (family_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        (family_dir / "mining_manifest.json").write_text(
            json.dumps({"status": "complete", "identity": {"profile": profile}}), encoding="utf-8"
        )
        (family_dir / "conditional_rules.jsonl").write_text(
            json.dumps(_rule(family, profile, family)) + "\n", encoding="utf-8"
        )


class ComparisonTests(unittest.TestCase):
    def test_rule_key_ignores_profile_and_feature_order(self) -> None:
        left = _rule("type1_investigation", "strict", "x")
        right = dict(left, profile="compare_psr", condition_feature_ids=list(reversed(left["condition_feature_ids"])))
        self.assertEqual(canonical_rule_key(left), canonical_rule_key(right))

    def test_discovery_excludes_incomplete_run(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_run(root, "strict_run", "strict")
            _write_run(root, "psr_run", "compare_psr")
            _write_run(root, "old_run", "compare_idf", missing_family="type2_diagnosis")
            runs, excluded = discover_complete_runs(root)
            self.assertEqual([run.profile for run in runs], ["strict", "compare_psr"])
            self.assertEqual(excluded[0]["directory"], "old_run")

    def test_comparison_and_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_run(root, "strict_run", "strict")
            _write_run(root, "psr_run", "compare_psr")
            runs, excluded = discover_complete_runs(root)
            payload = build_comparison(runs, excluded, top_n=1)
            self.assertEqual(len(payload["methods"]), 2)
            self.assertEqual(payload["methods"][0]["accepted"], len(FAMILY_IDS))
            all_pair = next(row for row in payload["pairwise"] if row["family"] == "all")
            self.assertEqual(all_pair["jaccard"], 1.0)
            html = render_html(payload)
            self.assertIn("MCQ Visit 挖掘规则比较", html)
            self.assertIn("const DATA=", html)
            output = root / "comparison"
            write_outputs(payload, input_root=root, output_dir=output)
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "comparison_summary.json").is_file())
            self.assertTrue((output / "说明文档.md").is_file())

    def test_duplicate_complete_profile_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _write_run(root, "strict_a", "strict")
            _write_run(root, "strict_b", "strict")
            with self.assertRaises(ComparisonError):
                discover_complete_runs(root)


if __name__ == "__main__":
    unittest.main()
