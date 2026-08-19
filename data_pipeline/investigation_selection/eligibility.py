"""Classify POE rows into investigation eligibility without guessing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ELIGIBILITY_PATH = (
    REPO_ROOT / "config" / "investigation-selection" / "investigation-order-eligibility.yaml"
)

ELIGIBLE = "eligible_investigation"
MONITORING_ONLY = "monitoring_only"
EXCLUDED = "excluded_non_investigation"
REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True)
class EligibilityPolicy:
    default_eligibility: str
    types: dict[str, dict[str, str]]
    status: str
    path: Path

    def classify(self, order_type: str | None, order_subtype: str | None) -> str:
        if not order_type:
            return self.default_eligibility
        subtypes = self.types.get(order_type)
        if subtypes is None:
            return self.default_eligibility
        if order_subtype and order_subtype in subtypes:
            return subtypes[order_subtype]
        if "*" in subtypes:
            return subtypes["*"]
        return self.default_eligibility


def load_eligibility_policy(path: Path | None = None) -> EligibilityPolicy:
    policy_path = Path(path or DEFAULT_ELIGIBILITY_PATH)
    if not policy_path.is_file():
        raise FileNotFoundError(f"investigation eligibility catalog missing: {policy_path}")
    payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"{policy_path} must contain a YAML object")
    types = payload.get("types")
    if not isinstance(types, Mapping):
        raise ValueError("eligibility catalog requires types")
    normalized: dict[str, dict[str, str]] = {}
    for order_type, subtypes in types.items():
        if not isinstance(subtypes, Mapping):
            raise ValueError(f"eligibility types[{order_type!r}] must be a mapping")
        normalized[str(order_type)] = {str(key): str(value) for key, value in subtypes.items()}
    default = str(payload.get("default_eligibility") or REVIEW_REQUIRED)
    return EligibilityPolicy(
        default_eligibility=default,
        types=normalized,
        status=str(payload.get("status") or "draft_unreviewed"),
        path=policy_path,
    )


def track_for(
    *,
    event_kind: str | None,
    order_type: str | None,
    eligibility: str,
    source_table: str | None = None,
) -> str | None:
    kind = str(event_kind or "")
    table = str(source_table or "")
    if "labevents" in table or kind in {"laboratory_resulted", "microbiology_resulted"}:
        return "lab_result_proxy"
    if kind == "imaging_reported" or (table.endswith("radiology") and kind != "imaging_ordered"):
        return "imaging_result_proxy"
    if kind == "laboratory_ordered" or order_type == "Lab":
        return "generic_lab_order"
    if kind == "imaging_ordered" or order_type == "Radiology":
        return "imaging_order"
    if eligibility == ELIGIBLE and kind.endswith("_ordered"):
        return "clinical_order"
    return None
