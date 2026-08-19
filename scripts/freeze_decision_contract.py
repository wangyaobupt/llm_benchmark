"""Refresh protocol audit hashes and write catalog-lock.json."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml

from data_pipeline.investigation_selection.catalog_lock import write_catalog_lock
from evaluation_pipeline.governance.protocol import load_protocol_bundle, validate_protocol_bundle

CONFIG = ROOT / "config/investigation-selection"
PROTOCOL = CONFIG / "protocol.yaml"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    protocol = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))
    protocol["audit_metadata"] = {
        "source_git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "dependency_lock_sha256": sha256(ROOT / "uv.lock"),
        "input_manifest_sha256": {
            str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path)
            for path in (
                ROOT / "docs/legacy-invalidation-manifest.json",
                ROOT / "versions/v1-template-stem/artifacts/investigation_selection/output/split/split_manifest.json",
                CONFIG / "track-catalog.yaml",
                CONFIG / "time-semantics.yaml",
                CONFIG / "feature-whitelist.yaml",
                CONFIG / "source-manifests.yaml",
                CONFIG / "investigation-order-eligibility.yaml",
                CONFIG / "panel-definitions.yaml",
                ROOT / "data/derived/investigation_timepoint/poe-subtype-audit-1000.json",
            )
        },
    }
    PROTOCOL.write_text(yaml.safe_dump(protocol, sort_keys=False), encoding="utf-8")
    lock_path = write_catalog_lock()
    bundle = load_protocol_bundle(
        PROTOCOL,
        ROOT / "schemas/investigation-selection-protocol.schema.json",
        CONFIG / "reason-code-registry.yaml",
    )
    report = validate_protocol_bundle(bundle)
    print(json.dumps({
        "protocol_valid": report["valid"],
        "freeze_ready": report["freeze_ready"],
        "freeze_blockers": report["freeze_blockers"],
        "catalog_lock": str(lock_path),
        "decision_semantics": protocol["scientific_protocol"]["decision_contract"]["decision_semantics"],
    }, ensure_ascii=False, indent=2))
    if not report["valid"]:
        print(json.dumps(report["errors"], ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
