"""Phase 2: Batch aggregation of event data from parquet.

All aggregators rely on a pre-populated DuckDB temp table 'batch_eps'
containing a single column 'episode_id VARCHAR'. The adapter creates
and populates this table before calling any aggregator.
"""

from __future__ import annotations
import json
import logging
from typing import Any
from collections import defaultdict

import duckdb

logger = logging.getLogger(__name__)


def _read_parquet(base: str, name: str) -> str:
    """Return read_parquet() SQL string for the given file."""
    return f"read_parquet('{base}{name}.parquet')"


def _parse_payload(raw: Any) -> dict:
    """Parse raw_payload (JSON string or dict) to dict."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return {}


def aggregate_laboratory(con: duckdb.DuckDBPyConnection, base: str) -> dict[str, list[dict]]:
    """Aggregate lab events grouped by episode + label (concept_name).

    Preserves full time-series for each lab item.
    Returns {episode_id: [{itemid, label, fluid, category, results: [...]}]}.
    """
    rows = con.execute(f"""
        SELECT te.episode_id,
               ei.concept_name,
               ei.raw_payload,
               te.event_time
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN {_read_parquet(base, 'event_items')} ei ON te.event_id = ei.event_id
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        WHERE te.event_type = 'laboratory_panel'
        ORDER BY te.episode_id, ei.concept_name, te.event_time
    """).fetchall()

    grouped: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {
        "itemid": None, "results": []
    }))
    for ep_id, label, raw_payload, event_time in rows:
        payload = _parse_payload(raw_payload)
        entry = grouped[str(ep_id)][label]
        if entry["itemid"] is None:
            entry["itemid"] = payload.get("itemid")
        entry["results"].append({
            "charttime": payload.get("charttime") or (str(event_time) if event_time else None),
            "value": payload.get("value"),
            "valuenum": _safe_float(payload.get("valuenum")),
            "valueuom": payload.get("valueuom"),
            "ref_range_lower": _safe_float(payload.get("ref_range_lower")),
            "ref_range_upper": _safe_float(payload.get("ref_range_upper")),
            "flag": payload.get("flag"),
        })

    result: dict[str, list[dict]] = {}
    for ep_id, labels in grouped.items():
        result[ep_id] = [
            {
                "itemid": data["itemid"],
                "label": label,
                "fluid": None,
                "category": None,
                "results": data["results"],
            }
            for label, data in labels.items()
        ]
    return result


def aggregate_diagnoses(con: duckdb.DuckDBPyConnection, base: str) -> dict[str, dict[str, Any]]:
    """Separate primary (seq_num=1) and other diagnoses.

    Returns {episode_id: {"primary": {...}|None, "other": [str]}}.
    """
    rows = con.execute(f"""
        SELECT te.episode_id,
               ei.concept_name,
               ei.raw_payload
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN {_read_parquet(base, 'event_items')} ei ON te.event_id = ei.event_id
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        WHERE te.event_type = 'diagnosis_code'
        ORDER BY te.episode_id
    """).fetchall()

    all_dx: dict[str, list[tuple[int, str, str, int]]] = defaultdict(list)
    for ep_id, dx_name, raw_payload in rows:
        payload = _parse_payload(raw_payload)
        seq = _safe_int(payload.get("seq_num"), 999)
        icd_code = payload.get("icd_code") or ""
        icd_version = _safe_int(payload.get("icd_version"), 0)
        all_dx[str(ep_id)].append((seq, icd_code, dx_name or "", icd_version))

    result: dict[str, dict[str, Any]] = {}
    for ep_id, dx_list in all_dx.items():
        dx_list.sort(key=lambda x: x[0])
        primary = None
        other: list[str] = []
        for seq, code, name, ver in dx_list:
            ver_str = f"ICD-{ver}-CM" if ver in (9, 10) else str(ver)
            entry = {"icd_code": code, "diagnosis_name": name, "icd_version": ver_str}
            if seq == 1 and primary is None:
                primary = entry
            else:
                other.append(name)
        result[ep_id] = {"primary": primary, "other": other}
    return result


def aggregate_microbiology(con: duckdb.DuckDBPyConnection, base: str) -> dict[str, list[dict]]:
    """Aggregate microbiology specimens."""
    rows = con.execute(f"""
        SELECT te.episode_id,
               ei.concept_name,
               ei.raw_payload,
               te.event_time
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN {_read_parquet(base, 'event_items')} ei ON te.event_id = ei.event_id
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        WHERE te.event_type = 'microbiology_specimen'
        ORDER BY te.episode_id, te.event_time
    """).fetchall()

    result: dict[str, list[dict]] = defaultdict(list)
    for ep_id, concept, raw_payload, event_time in rows:
        payload = _parse_payload(raw_payload)
        result[str(ep_id)].append({
            "spec_type_desc": payload.get("spec_type_desc"),
            "test_name": payload.get("test_name"),
            "charttime": str(event_time) if event_time else None,
            "org_name": payload.get("org_name"),
            "isolate_num": _safe_int(payload.get("isolate_num"), 0),
            "ab_name": payload.get("ab_name"),
            "interpretation": payload.get("interpretation"),
            "dilution_text": payload.get("dilution_text"),
            "dilution_value": _safe_float(payload.get("dilution_value")),
        })
    return dict(result)


def aggregate_radiology(con: duckdb.DuckDBPyConnection, base: str) -> dict[str, list[dict]]:
    """Aggregate radiology reports (note_type='RR').

    Deduplicates by exam_name per episode (keep first occurrence).
    """
    rows = con.execute(f"""
        SELECT d.episode_id, d.event_time, d.text
        FROM {_read_parquet(base, 'documents')} d
        JOIN batch_eps ON d.episode_id = batch_eps.episode_id
        WHERE d.note_type = 'RR' AND length(d.text) > 0
        ORDER BY d.episode_id, d.event_time
    """).fetchall()

    result: dict[str, list[dict]] = defaultdict(list)
    seen: dict[str, set[str]] = defaultdict(set)
    for ep_id, event_time, text in rows:
        ep_key = str(ep_id)
        exam_name = _guess_exam_name(text)
        if exam_name in seen[ep_key]:
            continue
        seen[ep_key].add(exam_name)
        result[ep_key].append({
            "exam_name": exam_name,
            "charttime": str(event_time) if event_time else None,
            "text": text,
            "details": [],
        })
    return dict(result)


def aggregate_ed_triage(con: duckdb.DuckDBPyConnection, base: str) -> dict[str, dict[str, Any]]:
    """Aggregate ED triage vitals. All fields are directly in raw_payload."""
    rows = con.execute(f"""
        SELECT te.episode_id, ei.raw_payload
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN {_read_parquet(base, 'event_items')} ei ON te.event_id = ei.event_id
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        WHERE te.event_type = 'ed_triage'
    """).fetchall()

    result: dict[str, dict[str, Any]] = {}
    for ep_id, raw_payload in rows:
        ep_key = str(ep_id)
        if ep_key in result:
            continue
        payload = _parse_payload(raw_payload)
        result[ep_key] = {
            "temperature": _safe_float(payload.get("temperature")),
            "heartrate": _safe_float(payload.get("heartrate")),
            "resprate": _safe_float(payload.get("resprate")),
            "o2sat": _safe_float(payload.get("o2sat")),
            "sbp": _safe_float(payload.get("sbp")),
            "dbp": _safe_float(payload.get("dbp")),
            "acuity": _safe_int(payload.get("acuity")),
            "pain": payload.get("pain"),
            "rhythm": None,
            "source": "triage",
        }
    return result


def aggregate_ed_vital_signs(con: duckdb.DuckDBPyConnection, base: str) -> dict[str, list[dict]]:
    """Aggregate ED vital signs series (has rhythm field).

    Used to supplement triage vitals with rhythm information.
    """
    rows = con.execute(f"""
        SELECT te.episode_id, ei.raw_payload, te.event_time
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN {_read_parquet(base, 'event_items')} ei ON te.event_id = ei.event_id
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        WHERE te.event_type = 'ed_vital_signs'
        ORDER BY te.episode_id, te.event_time
    """).fetchall()

    result: dict[str, list[dict]] = defaultdict(list)
    for ep_id, raw_payload, event_time in rows:
        payload = _parse_payload(raw_payload)
        result[str(ep_id)].append({
            "charttime": payload.get("charttime") or (str(event_time) if event_time else None),
            "temperature": _safe_float(payload.get("temperature")),
            "heartrate": _safe_float(payload.get("heartrate")),
            "resprate": _safe_float(payload.get("resprate")),
            "o2sat": _safe_float(payload.get("o2sat")),
            "sbp": _safe_float(payload.get("sbp")),
            "dbp": _safe_float(payload.get("dbp")),
            "rhythm": payload.get("rhythm"),
            "pain": payload.get("pain"),
        })
    return dict(result)


def aggregate_generic_events(
    con: duckdb.DuckDBPyConnection,
    base: str,
    event_type: str,
    payload_fields: list[str],
    source_filter: str | None = None,
) -> dict[str, list[dict]]:
    """Generic aggregation for event_types mapping to simple arrays.

    Relies on batch_eps temp table for episode filtering.
    """
    clauses = [f"te.event_type = '{event_type}'"]
    if source_filter:
        clauses.append(f"ei.source_table LIKE '{source_filter}'")
    where = " AND ".join(clauses)

    rows = con.execute(f"""
        SELECT te.episode_id,
               ei.concept_name,
               ei.raw_payload,
               te.event_time,
               te.event_subtype
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN {_read_parquet(base, 'event_items')} ei ON te.event_id = ei.event_id
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        WHERE {where}
        ORDER BY te.episode_id, te.event_time
    """).fetchall()

    result: dict[str, list[dict]] = defaultdict(list)
    for ep_id, concept, raw_payload, event_time, subtype in rows:
        payload = _parse_payload(raw_payload)
        item = {}
        for f in payload_fields:
            item[f] = payload.get(f)
        item["_event_time"] = str(event_time) if event_time else None
        item["_concept_name"] = concept
        item["_event_subtype"] = subtype
        result[str(ep_id)].append(item)
    return dict(result)


def aggregate_transfers(con: duckdb.DuckDBPyConnection, base: str) -> dict[str, list[dict]]:
    """Aggregate transfer events into ordered care-unit path."""
    rows = con.execute(f"""
        SELECT te.episode_id, ei.raw_payload, te.event_time
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN {_read_parquet(base, 'event_items')} ei ON te.event_id = ei.event_id
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        WHERE te.event_type = 'transfer'
        ORDER BY te.episode_id, te.event_time
    """).fetchall()

    result: dict[str, list[dict]] = defaultdict(list)
    for ep_id, raw_payload, event_time in rows:
        payload = _parse_payload(raw_payload)
        result[str(ep_id)].append({
            "eventtype": payload.get("eventtype"),
            "careunit": payload.get("careunit"),
            "intime": str(event_time) if event_time else None,
            "outtime": payload.get("outtime"),
        })
    return dict(result)


def aggregate_icu_stays(con: duckdb.DuckDBPyConnection, base: str) -> dict[str, list[dict]]:
    """Aggregate ICU stay metadata from care_contacts (contact_type='icu')."""
    rows = con.execute(f"""
        SELECT cc.episode_id, cc.start_time, cc.end_time
        FROM {_read_parquet(base, 'care_contacts')} cc
        JOIN batch_eps ON cc.episode_id = batch_eps.episode_id
        WHERE cc.contact_type = 'icu'
        ORDER BY cc.episode_id, cc.start_time
    """).fetchall()

    result: dict[str, list[dict]] = defaultdict(list)
    for ep_id, start, end in rows:
        result[str(ep_id)].append({
            "first_careunit": None,
            "last_careunit": None,
            "intime": str(start) if start else None,
            "outtime": str(end) if end else None,
            "los": None,
        })
    return dict(result)


def _safe_float(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (ValueError, TypeError):
        return None


def _safe_int(v: Any, default: int | None = None) -> int | None:
    try:
        if v is None or v == "":
            return default
        return int(float(v))
    except (ValueError, TypeError):
        return default


def _guess_exam_name(text: str) -> str:
    """Extract exam name from radiology report text."""
    if not text:
        return "UNKNOWN"
    for line in text[:500].split("\n"):
        ll = line.strip().lower()
        if ll.startswith("examination:") or ll.startswith("exam:"):
            return line.split(":", 1)[1].strip()[:100]
    for line in text[:200].split("\n"):
        s = line.strip()
        if s:
            return s[:100]
    return "UNKNOWN"
