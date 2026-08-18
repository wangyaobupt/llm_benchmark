from pathlib import Path

from scripts.run_exploratory_gold_workflow import build_stage_specs


def test_exploratory_workflow_has_ordered_e1_to_e4_specs(tmp_path: Path):
    specs = build_stage_specs(Path("source"), tmp_path)
    assert [spec["stage"] for spec in specs] == ["E1", "E2", "E3", "E4"]
    assert specs[0]["script"].endswith("exploratory_source_audit.py")
    assert "--e2" in specs[3]["args"]
    assert "--e3" in specs[3]["args"]
