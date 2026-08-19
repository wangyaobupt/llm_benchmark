"""Deterministic catalog-lock for eligibility, panels, and time semantics."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "config" / "investigation-selection"
DEFAULT_LOCK_PATH = CONFIG / "catalog-lock.json"

LOCK_SOURCES = (
    "investigation-order-eligibility.yaml",
    "panel-definitions.yaml",
    "track-catalog.yaml",
    "time-semantics.yaml",
    "protocol.yaml",
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML object")
    return payload


def build_catalog_lock(config_dir: Path | None = None) -> dict[str, Any]:
    directory = Path(config_dir or CONFIG)
    hashes = {}
    for name in LOCK_SOURCES:
        path = directory / name
        if not path.is_file():
            raise FileNotFoundError(path)
        hashes[f"config/investigation-selection/{name}"] = _sha256_file(path)
    protocol = _load_yaml(directory / "protocol.yaml")
    eligibility = _load_yaml(directory / "investigation-order-eligibility.yaml")
    panels = _load_yaml(directory / "panel-definitions.yaml")
    contract = protocol["scientific_protocol"]["decision_contract"]
    body = {
        "schema_version": "investigation-selection-catalog-lock/1.0.0",
        "purpose": (
            "Hash lock for investigation catalog inputs (eligibility, panel counting, "
            "track catalog, time semantics, protocol). Rebuild if those files change. "
            "Not a patient-level data lock."
        ),
        "status": "scientific_frozen",
        "clinical_review": eligibility.get("clinical_review"),
        "decision_semantics": contract["decision_semantics"],
        "lab_result_proxy_target_time_field": contract["lab_result_proxy"]["target_time_field"],
        "lab_result_proxy_occurrence_time_field": contract["lab_result_proxy"]["occurrence_time_field"],
        "panel_main_analysis_count": contract["panel_policy"]["main_analysis_count"],
        "panel_complete_time": contract["panel_policy"]["panel_complete_time"],
        "eligibility_status": eligibility.get("status"),
        "panel_definition_status": panels.get("status"),
        "source_sha256": hashes,
    }
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {**body, "catalog_lock_sha256": hashlib.sha256(canonical).hexdigest()}


def write_catalog_lock(path: Path | None = None) -> Path:
    lock_path = Path(path or DEFAULT_LOCK_PATH)
    payload = build_catalog_lock(lock_path.parent)
    lock_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return lock_path
