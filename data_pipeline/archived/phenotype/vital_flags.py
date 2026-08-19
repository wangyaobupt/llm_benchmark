"""P2 — physiologic flags (physiologic_flag) from structured vital signs.

Reads ``vital_measured`` events, resolves each vital's numeric value (heart
rate / temperature / respiratory rate / oxygen saturation from ``value_numeric``;
blood pressure systolic from ``value_structured_json``), and emits the adopted
qualitative flags (tachycardia, fever, hypoxia, hypotension, ...).

For a flag with ``>``/``>=`` the most abnormal value is the maximum; for ``<`` it
is the minimum. Temporal gating (only values available before the index time) is
applied by the phenotype assembler (P0/P6), not here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import pandas as pd
import yaml

# source_label -> canonical source key used by the flag rules.
_SOURCE_KEY = {
    "Heart rate": "heart_rate",
    "Temperature": "temperature",
    "Respiratory rate": "respiratory_rate",
    "Oxygen saturation": "oxygen_saturation",
    "Blood pressure": "systolic_bp",
}

_FAHRENHEIT = ("°F", "degF", "f")


def load_flag_rules(path: Path | None = None) -> dict:
    path = path or Path(__file__).resolve().parent / "config" / "vital_flag_rules.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _temperature_c(value: float, unit: str | None) -> float:
    unit = (unit or "").strip()
    if unit in _FAHRENHEIT or unit.lower() in {"f", "°f", "degf"}:
        return (value - 32.0) * 5.0 / 9.0
    return value


def _resolve_value(row: Mapping) -> float | None:
    source = _SOURCE_KEY.get(row.get("source_label"))
    if source == "systolic_bp":
        raw = row.get("value_structured_json")
        if isinstance(raw, str) and raw.strip():
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                return None
        elif isinstance(raw, dict):
            obj = raw
        else:
            return None
        v = obj.get("systolic")
        return float(v) if v is not None else None
    v = row.get("value_numeric")
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    value = float(v)
    if source == "temperature":
        return _temperature_c(value, row.get("unit"))
    return value


def _extreme(values: list[float], operator: str) -> float:
    return max(values) if operator in (">", ">=") else min(values)


def flags_for_visit(vital_rows: pd.DataFrame, rules: Mapping) -> set[str]:
    """Return the set of physiologic flags for one visit's vital rows."""
    flags: set[str] = set()
    by_source: dict[str, list[float]] = {}
    for row in vital_rows.to_dict("records"):
        source = _SOURCE_KEY.get(row.get("source_label"))
        if source is None:
            continue
        value = _resolve_value(row)
        if value is not None:
            by_source.setdefault(source, []).append(value)
    for flag_name, rule in rules["flags"].items():
        values = by_source.get(rule["source"])
        if not values:
            continue
        extreme = _extreme(values, rule["operator"])
        op = rule["operator"]
        thr = float(rule["threshold"])
        hit = extreme > thr if op == ">" else (extreme >= thr if op == ">=" else extreme < thr)
        if hit:
            flags.add(flag_name)
    return flags


def extract_vital_flags(events: pd.DataFrame,
                        rules: Mapping | None = None) -> pd.DataFrame:
    """Return hadm_id -> physiologic flags (one row per admission with vitals)."""
    rules = rules or load_flag_rules()
    vitals = events[events["event_kind"] == "vital_measured"]
    needed = ["hadm_id", "source_label", "value_numeric",
              "value_structured_json", "unit"]
    vitals = vitals[needed].copy()
    rows: list[dict] = []
    for hadm_id, grp in vitals.groupby("hadm_id", sort=True):
        flags = flags_for_visit(grp, rules)
        if flags:
            rows.append({"hadm_id": hadm_id, "physiologic_flags": sorted(flags)})
    return pd.DataFrame(rows, columns=["hadm_id", "physiologic_flags"])
