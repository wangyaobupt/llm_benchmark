"""First-wave methodology policy: result-table identity and clocks, not POE orders."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

import pyarrow.parquet as pq
import yaml

from .fields import _clean, structured_payload


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = REPO_ROOT / "config" / "investigation-selection" / "first-wave.yaml"


def load_first_wave_policy(path: Path | None = None) -> dict[str, Any]:
    policy_path = Path(path or DEFAULT_PATH)
    payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"{policy_path} must contain a YAML object")
    return dict(payload)


def first_wave_tracks(policy: Mapping[str, Any] | None = None) -> tuple[str, ...]:
    loaded = policy or load_first_wave_policy()
    tracks = loaded.get("index", {}).get("tracks") or ["lab_result_proxy", "imaging_result_proxy"]
    return tuple(str(item) for item in tracks)


def first_wave_fact_types(policy: Mapping[str, Any] | None = None) -> tuple[str, ...]:
    loaded = policy or load_first_wave_policy()
    types = loaded.get("index", {}).get("fact_types") or ["resulted", "reported"]
    return tuple(str(item) for item in types)


def first_wave_domains(policy: Mapping[str, Any] | None = None) -> tuple[str, ...]:
    loaded = policy or load_first_wave_policy()
    domains = loaded.get("index", {}).get("domains") or ["lab", "imaging"]
    return tuple(str(item) for item in domains)


def is_first_wave_row(row: Mapping[str, Any], policy: Mapping[str, Any] | None = None) -> bool:
    """True for result-layer lab/imaging facts.  POE orders never qualify."""
    if row.get("fact_type") == "order":
        return False
    fact_types = first_wave_fact_types(policy)
    if row.get("fact_type") and str(row["fact_type"]) not in fact_types:
        return False
    tracks = first_wave_tracks(policy)
    track = row.get("track_id")
    if track:
        return str(track) in tracks
    domains = first_wave_domains(policy)
    return str(row.get("domain") or "") in domains


def first_wave_burst_minutes(policy: Mapping[str, Any] | None = None) -> int:
    loaded = policy or load_first_wave_policy()
    return int(loaded.get("index", {}).get("burst_minutes") or 15)


def evidence_exclude_event_kinds(policy: Mapping[str, Any] | None = None) -> set[str]:
    loaded = policy or load_first_wave_policy()
    kinds = loaded.get("evidence_exclude_event_kinds") or []
    return {str(kind) for kind in kinds}


def skip_exam_names(policy: Mapping[str, Any] | None = None) -> set[str]:
    loaded = policy or load_first_wave_policy()
    names = loaded.get("imaging_result_proxy", {}).get("skip_exam_names") or []
    return {str(name).casefold() for name in names}


def radiology_exam_names(event: Mapping[str, Any]) -> list[str]:
    payload = structured_payload(event)
    details = payload.get("details")
    if not isinstance(details, list):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for detail in details:
        if not isinstance(detail, Mapping):
            continue
        if str(detail.get("field_name") or "").casefold() != "exam_name":
            continue
        name = _clean(detail.get("field_value"))
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def load_radiology_exam_sidecar(path: Path | None) -> dict[str, list[dict[str, Any]]]:
    """Index radiology_detail exam_name rows by note_id.

    processed_events drops supporting detail rows; exam_name lives on
    raw_source_records for note.radiology_detail.
    """
    if path is None or not path.is_file():
        return {}
    table = pq.read_table(
        path,
        columns=["source_table", "clinical_readable_record_json", "raw_record_json"],
        filters=[("source_table", "==", "note.radiology_detail")],
    )
    by_note: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in table.to_pylist():
        raw = row.get("clinical_readable_record_json") or row.get("raw_record_json")
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        if str(parsed.get("field_name") or "").casefold() != "exam_name":
            continue
        note_id = _clean(parsed.get("note_id"))
        if note_id:
            by_note[note_id].append(parsed)
    return dict(by_note)


def attach_radiology_exam_details(
    events: list[dict[str, Any]],
    sidecar: Mapping[str, list[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    if not sidecar:
        return events
    attached: list[dict[str, Any]] = []
    for event in events:
        kind = str(event.get("event_kind") or "")
        if kind != "imaging_reported":
            attached.append(event)
            continue
        payload = structured_payload(event)
        details = payload.get("details")
        if isinstance(details, list) and details:
            attached.append(event)
            continue
        note_id = _clean(payload.get("note_id"))
        extra = sidecar.get(note_id or "")
        if not extra:
            attached.append(event)
            continue
        row = dict(event)
        payload = dict(payload)
        payload["details"] = list(extra)
        row["value_structured_json"] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        attached.append(row)
    return attached


def expand_imaging_report_events(
    events: list[dict[str, Any]],
    *,
    policy: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Split one radiology note into one row per exam_name.

    The event preferred_name is the note type (RR).  Body-site identity lives in
    radiology_detail.exam_name.
    """
    skipped = skip_exam_names(policy)
    expanded: list[dict[str, Any]] = []
    for event in events:
        kind = str(event.get("event_kind") or "")
        table = str(event.get("source_table") or "")
        if kind != "imaging_reported" and not table.endswith("radiology"):
            expanded.append(event)
            continue
        if kind.endswith("_ordered"):
            expanded.append(event)
            continue
        names = [name for name in radiology_exam_names(event) if name.casefold() not in skipped]
        if not names:
            continue
        payload = structured_payload(event)
        note_id = _clean(payload.get("note_id") or event.get("source_row_id") or event.get("event_id"))
        for name in names:
            row = dict(event)
            row["preferred_name"] = name
            row["source_label"] = name
            row["exam_name"] = name
            row["note_id"] = note_id
            row["content_specificity"] = "entity_specific"
            row["lifecycle_action"] = event.get("lifecycle_action") or "create"
            expanded.append(row)
    return expanded
