"""Hashing and fail-closed input verification shared across tasks."""
import hashlib
import json
from pathlib import Path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_normalized_events(events_path: Path) -> str:
    """Verify normalized_events.parquet against its workflow_manifest (fail-closed)."""
    workflow_path = events_path.parent.parent / "workflow_manifest.json"
    if not workflow_path.exists():
        raise FileNotFoundError(f"workflow manifest not found: {workflow_path}")
    manifest = json.loads(workflow_path.read_text(encoding="utf-8"))
    expected = manifest["stages"]["normalization"]["output_sha256"][
        "normalized_events.parquet"
    ]
    actual = _sha256_file(events_path)
    if actual != expected:
        raise ValueError("normalized_events SHA-256 drift vs workflow manifest")
    return actual
