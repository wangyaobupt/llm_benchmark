"""Bind W1 protocol audit hashes and emit the deterministic protocol lock."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation_pipeline.governance import (
    build_protocol_lock,
    load_protocol_bundle,
    validate_protocol_bundle,
)
from evaluation_pipeline.governance.protocol import write_json


CONFIG = ROOT / "config/investigation-selection"
PROTOCOL = CONFIG / "protocol.yaml"
LOCK = CONFIG / "protocol-lock.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    import yaml

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
                ROOT / "tasks/investigation_selection/output/split/split_manifest.json",
                CONFIG / "track-catalog.yaml",
                CONFIG / "time-semantics.yaml",
                CONFIG / "feature-whitelist.yaml",
                CONFIG / "source-manifests.yaml",
            )
        },
    }
    PROTOCOL.write_text(yaml.safe_dump(protocol, sort_keys=False), encoding="utf-8")
    bundle = load_protocol_bundle(
        PROTOCOL,
        ROOT / "schemas/investigation-selection-protocol.schema.json",
        CONFIG / "reason-code-registry.yaml",
    )
    report = validate_protocol_bundle(bundle)
    if not report["freeze_ready"]:
        raise SystemExit(json.dumps(report, ensure_ascii=False, indent=2))
    write_json(LOCK, build_protocol_lock(bundle))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(LOCK)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
