"""Load mining YAML. Investigation catalog is draft_unreviewed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from data_pipeline.mcq_visit_extract.atomic import file_sha256


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected mapping in {path}")
    return payload


def load_config(config_dir: Path) -> dict[str, Any]:
    config_dir = config_dir.resolve()
    windows = load_yaml(config_dir / "windows.yaml")
    thresholds = load_yaml(config_dir / "thresholds.yaml")
    vitals = load_yaml(config_dir / "vital-flags.yaml")
    catalog = load_yaml(config_dir / "investigation-catalog.yaml")
    lab_ids = {str(row["itemid"]).strip() for row in catalog.get("high_signal_labs") or []}
    return {
        "dir": str(config_dir),
        "windows": windows,
        "thresholds": thresholds,
        "vitals": vitals,
        "catalog": catalog,
        "high_signal_itemids": lab_ids,
        "sha256": {
            "windows": file_sha256(config_dir / "windows.yaml"),
            "thresholds": file_sha256(config_dir / "thresholds.yaml"),
            "vitals": file_sha256(config_dir / "vital-flags.yaml"),
            "catalog": file_sha256(config_dir / "investigation-catalog.yaml"),
        },
    }
