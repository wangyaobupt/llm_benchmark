from __future__ import annotations

import unittest
from pathlib import Path

from data_pipeline.mcq_visit_mining.catalog import load_config
from data_pipeline.mcq_visit_mining.families import IsolationError, contract_for
from data_pipeline.mcq_visit_mining.mine import mine_family
from data_pipeline.mcq_visit_mining.stats import fisher_greater, pair_stats, wilson_lower
from data_pipeline.mcq_visit_mining.transactions import build_transaction, type1_outcomes
from data_pipeline.mcq_visit_timeline.events import merge_visit
from tests.test_mcq_visit_timeline import _named, _timed


REPO_CONFIG = Path("config/mcq_visit_mining")


def _events() -> tuple[dict, list]:
    _, events, facts = merge_visit(_timed(), _named())
    return facts, events


class IsolationTests(unittest.TestCase):
    def test_type1_excludes_diagnosis_results_and_poe_lab(self) -> None:
        config = load_config(REPO_CONFIG)
        facts, events = _events()
        contract = contract_for("type1_investigation")
        row = build_transaction(
            facts,
            events,
            contract=contract,
            window=config["windows"]["families"]["type1_investigation"],
            vital_spec=config["vitals"],
            high_signal_itemids=config["high_signal_itemids"],
            skip_poe_category_only=True,
        )
        types = {item["feature_type"] for item in row["features"]}
        self.assertNotIn("diagnosis", types)
        self.assertNotIn("investigation_result_flag", types)
        self.assertTrue(any(item["feature_type"] == "symptom" for item in row["features"]))
        ids = {item["outcome_id"] for item in row["outcomes"]}
        self.assertTrue(any(oid.startswith("lab:51003") for oid in ids))
        self.assertFalse(any("50912" in oid for oid in ids))
        self.assertFalse(any(item.get("category_only") for item in row["outcomes"]))
        self.assertTrue(any(item["outcome_id"].startswith("order:") for item in row["outcomes"]))
        self.assertTrue(any(item["outcome_id"].startswith("imaging:") for item in row["outcomes"]))

    def test_type1_drops_labs_outside_four_hours(self) -> None:
        config = load_config(REPO_CONFIG)
        timed = _timed()
        timed["investigations"]["laboratory"][0]["results"][0]["charttime"] = "2188-04-24 15:00:00"
        _, events, facts = merge_visit(timed, _named())
        outcomes = type1_outcomes(
            events,
            origin=facts["presentation_origin"],
            hours=4,
            high_signal_itemids=config["high_signal_itemids"],
            skip_poe_category_only=True,
        )
        self.assertFalse(any("51003" in item["outcome_id"] for item in outcomes))

    def test_type2_can_use_result_flags_not_diagnosis_as_x(self) -> None:
        config = load_config(REPO_CONFIG)
        facts, events = _events()
        row = build_transaction(
            facts,
            events,
            contract=contract_for("type2_diagnosis"),
            window=config["windows"]["families"]["type2_diagnosis"],
            vital_spec=config["vitals"],
            high_signal_itemids=config["high_signal_itemids"],
            skip_poe_category_only=True,
        )
        types = {item["feature_type"] for item in row["features"]}
        self.assertIn("investigation_result_flag", types)
        self.assertNotIn("diagnosis", types)
        self.assertEqual(row["outcomes"][0]["grain"], "discharge_icd")
        self.assertIn("discharge_icd_posthoc", row["posthoc_flags"])

    def test_type3_default_excludes_diagnosis(self) -> None:
        config = load_config(REPO_CONFIG)
        facts, events = _events()
        row = build_transaction(
            facts,
            events,
            contract=contract_for("type3_medication"),
            window=config["windows"]["families"]["type3_medication"],
            vital_spec=config["vitals"],
            high_signal_itemids=set(),
            skip_poe_category_only=True,
        )
        types = {item["feature_type"] for item in row["features"]}
        self.assertNotIn("diagnosis", types)
        self.assertTrue(any(item["outcome_id"].startswith("drug:") for item in row["outcomes"]))

    def test_leaked_diagnosis_raises(self) -> None:
        contract = contract_for("type1_investigation")
        with self.assertRaises(IsolationError):
            from data_pipeline.mcq_visit_mining.families import assert_isolated

            assert_isolated(
                [{"feature_id": "diagnosis:x", "feature_type": "diagnosis", "display_name": "x"}],
                contract,
                outcomes=[],
            )


class StatsAndMineTests(unittest.TestCase):
    def test_wilson_and_fisher_known_table(self) -> None:
        stats = pair_stats(n_x=100, n_y=40, n_xy=30, n_total=200)
        self.assertGreater(stats["lift"], 1.0)
        self.assertGreater(stats["wilson_lower"], 0.2)
        self.assertLess(stats["fisher_p"], 0.05)
        self.assertGreater(wilson_lower(30, 100), 0.2)
        self.assertLess(fisher_greater(30, 70, 10, 90), 0.05)

    def test_mine_accepts_separated_rule(self) -> None:
        transactions = []
        for index in range(20):
            chest = index < 12
            features = [
                {"feature_id": "symptom:chest pain", "feature_type": "symptom", "display_name": "Chest pain"},
                {"feature_id": "sex:F", "feature_type": "sex", "display_name": "F"},
            ]
            if not chest:
                features = [
                    {"feature_id": "symptom:abdominal pain", "feature_type": "symptom", "display_name": "Abdominal pain"},
                    {"feature_id": "sex:F", "feature_type": "sex", "display_name": "F"},
                ]
            outcomes = []
            if chest:
                outcomes.append(
                    {
                        "outcome_id": "order:ecg",
                        "outcome_name": "ECG",
                        "grain": "order",
                        "source_event_kind": "cardiology_ordered",
                        "category_only": False,
                    }
                )
            else:
                outcomes.append(
                    {
                        "outcome_id": "imaging:ct abdomen",
                        "outcome_name": "CT abdomen",
                        "grain": "exam",
                        "source_event_kind": "radiology_reported",
                        "category_only": False,
                    }
                )
            if index % 5 == 0 and chest:
                outcomes.append(
                    {
                        "outcome_id": "imaging:chest radiography",
                        "outcome_name": "Chest radiography",
                        "grain": "exam",
                        "source_event_kind": "radiology_reported",
                        "category_only": False,
                    }
                )
            if not chest:
                outcomes.append(
                    {
                        "outcome_id": "order:ecg",
                        "outcome_name": "ECG",
                        "grain": "order",
                        "source_event_kind": "cardiology_ordered",
                        "category_only": False,
                    }
                )
            transactions.append(
                {
                    "visit_key": f"v{index}",
                    "hadm_id": str(index),
                    "family": "type1_investigation",
                    "features": features,
                    "outcomes": outcomes,
                }
            )
        accepted, rejected, summary = mine_family(
            transactions,
            family="type1_investigation",
            window_id="first_wave_4h",
            profile="strict",
            thresholds={
                "min_conditions": 2,
                "max_conditions": 2,
                "min_x_support": 5,
                "min_xy_support": 4,
                "min_smoothed_probability": 0.60,
                "min_lift": 1.20,
                "min_wilson_lower": 0.35,
                "max_fdr_q": 0.05,
                "min_bootstrap_stability": 0.50,
                "min_probability_gap": 0.10,
                "min_score_ratio": 1.05,
                "bootstrap_iterations": 50,
                "random_seed": 20260820,
                "score_ratio_cap": 1e6,
            },
            catalog_sha256="x",
            posthoc_flags=[],
        )
        self.assertGreaterEqual(summary["tested_pairs"], 1)
        self.assertTrue(isinstance(accepted, list))
        self.assertTrue(isinstance(rejected, list))


class ConfigLoadTests(unittest.TestCase):
    def test_config_loads(self) -> None:
        config = load_config(REPO_CONFIG)
        self.assertIn("51003", config["high_signal_itemids"])
        self.assertEqual(config["windows"]["families"]["type1_investigation"]["hours"], 4)


class PipelineIsolationTests(unittest.TestCase):
    def test_run_family_writes_only_that_family(self) -> None:
        import tempfile

        from data_pipeline.mcq_visit_mining.pipeline import run_family
        from data_pipeline.mcq_visit_standardize.io import write_json_array
        from data_pipeline.mcq_visit_timeline.pipeline import run as run_timeline

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            times_dir = root / "times"
            std_dir = root / "std"
            times_dir.mkdir()
            std_dir.mkdir()
            write_json_array(times_dir / "visits.json", [_timed()])
            write_json_array(std_dir / "visits_standardized.json", [_named()])
            timeline_dir = root / "timeline"
            run_timeline(
                times_path=times_dir / "visits.json",
                standardized_path=std_dir / "visits_standardized.json",
                output_dir=timeline_dir,
                expected_count=1,
                skip_fingerprint=True,
            )
            out = root / "mine_type1"
            manifest = run_family(
                timeline_dir=timeline_dir,
                output_dir=out,
                config_dir=REPO_CONFIG,
                family="type1_investigation",
                profile="strict",
                expected_count=1,
            )
            self.assertEqual(manifest["identity"]["family"], "type1_investigation")
            text = (out / "visit_transactions.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("diagnosis:", text)
            self.assertNotIn("Non-ST elevation", text)


if __name__ == "__main__":
    unittest.main()
