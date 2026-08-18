"""Run the W10 final-test process rehearsal on synthetic fixture subjects only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_pipeline.investigation_selection.release_preflight import audit_release_inputs, record_final_test_run


def main() -> int:
    protocol = {"status": "draft"}
    split = {"roles": {"development": ["fixture:dev-1", "fixture:dev-2"], "validation": ["fixture:val-1"], "final_test": ["fixture:test-1"]}, "previous_exposure_none": 1}
    artifacts = {"protocol": "fixture-protocol", "catalog": "fixture-catalog", "panel": "fixture-panel", "diagnosis": "fixture-diagnosis", "feature_whitelist": "fixture-whitelist"}
    preflight = audit_release_inputs(protocol=protocol, split=split, artifacts=artifacts, final_test_subjects=["fixture:test-1"], mode="rehearsal")
    if not preflight.ready:
        print(json.dumps({"ready": False, "blockers": preflight.blockers, "manifest": preflight.manifest}, ensure_ascii=False, indent=2))
        return 2
    run = record_final_test_run(result=preflight, metrics={"recall_at_10": 0.0, "mrr": 0.0, "ndcg": 0.0})
    print(json.dumps(run, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
