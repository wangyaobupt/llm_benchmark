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

from .config import Config

logger = logging.getLogger(__name__)


def create_raw_context_views(con: duckdb.DuckDBPyConnection, config: Config) -> None:
    """Create local source adapters for fields omitted by the episode Parquets."""
    paths = {
        "raw_context_omr": config.omr_path,
        "raw_context_edstays": config.edstays_path,
        "raw_context_icustays": config.icustays_path,
        "raw_context_radiology_detail": config.radiology_detail_path,
    }
    for view_name, path in paths.items():
        if not path.exists():
            raise FileNotFoundError(f"required source for P0 archive is missing: {path}")
        escaped = path.as_posix().replace("'", "''")
        con.execute(
            f"CREATE OR REPLACE TEMP VIEW {view_name} AS "
            f"SELECT * FROM read_csv_auto('{escaped}', header=true, all_varchar=true)"
        )


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
               te.event_id, te.event_time, te.available_time, te.recorded_time
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN {_read_parquet(base, 'event_items')} ei ON te.event_id = ei.event_id
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        WHERE te.event_type = 'laboratory_panel'
        ORDER BY te.episode_id, ei.concept_name, te.event_time
    """).fetchall()

    grouped: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {
        "itemid": None, "results": []
    }))
    for ep_id, label, raw_payload, event_id, event_time, available_time, recorded_time in rows:
        payload = _parse_payload(raw_payload)
        entry = grouped[str(ep_id)][label]
        if entry["itemid"] is None:
            entry["itemid"] = payload.get("itemid")
        entry["results"].append({
            "event_id": event_id,
            "charttime": payload.get("charttime") or (str(event_time) if event_time else None),
            **_time_meta(event_time, available_time, recorded_time),
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
        SELECT te.episode_id, te.event_id, te.event_time,
               te.available_time, te.recorded_time,
               ei.concept_name,
               ei.raw_payload
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN {_read_parquet(base, 'event_items')} ei ON te.event_id = ei.event_id
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        WHERE te.event_type = 'diagnosis_code'
        ORDER BY te.episode_id
    """).fetchall()

    all_dx: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ep_id, event_id, event_time, available_time, recorded_time, dx_name, raw_payload in rows:
        payload = _parse_payload(raw_payload)
        seq = _safe_int(payload.get("seq_num"), 999)
        icd_code = payload.get("icd_code") or ""
        icd_version = _safe_int(payload.get("icd_version"), 0)
        all_dx[str(ep_id)].append({
            "event_id": event_id,
            "sequence": seq,
            "icd_code": icd_code,
            "diagnosis_name": dx_name or "",
            "icd_version": f"ICD-{icd_version}-CM" if icd_version in (9, 10) else str(icd_version),
            **_time_meta(event_time, available_time, recorded_time),
            "evidence_phase": "post_hoc",
        })

    result: dict[str, dict[str, Any]] = {}
    for ep_id, dx_list in all_dx.items():
        dx_list.sort(key=lambda x: x["sequence"])
        primary = None
        for entry in dx_list:
            if entry["sequence"] == 1 and primary is None:
                primary = entry
        result[ep_id] = {"primary": primary, "coded_diagnoses": dx_list}
    return result


def aggregate_microbiology(con: duckdb.DuckDBPyConnection, base: str) -> dict[str, list[dict]]:
    """Aggregate microbiology specimens."""
    rows = con.execute(f"""
        SELECT te.episode_id,
               ei.concept_name,
               ei.raw_payload,
               te.event_id, te.event_time, te.available_time, te.recorded_time
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN {_read_parquet(base, 'event_items')} ei ON te.event_id = ei.event_id
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        WHERE te.event_type = 'microbiology_specimen'
        ORDER BY te.episode_id, te.event_time
    """).fetchall()

    result: dict[str, list[dict]] = defaultdict(list)
    for ep_id, concept, raw_payload, event_id, event_time, available_time, recorded_time in rows:
        payload = _parse_payload(raw_payload)
        result[str(ep_id)].append({
            "event_id": event_id,
            "spec_type_desc": payload.get("spec_type_desc"),
            "test_name": payload.get("test_name"),
            "charttime": str(event_time) if event_time else None,
            **_time_meta(event_time, available_time, recorded_time),
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
        SELECT d.episode_id, d.note_id, d.event_time, d.available_time,
               d.recorded_time, d.text,
               list(struct_pack(field_name := rd.field_name, field_value := rd.field_value,
                                field_ordinal := TRY_CAST(rd.field_ordinal AS BIGINT))
                    ORDER BY TRY_CAST(rd.field_ordinal AS BIGINT)) FILTER (WHERE rd.note_id IS NOT NULL) AS details
        FROM {_read_parquet(base, 'documents')} d
        JOIN batch_eps ON d.episode_id = batch_eps.episode_id
        LEFT JOIN raw_context_radiology_detail rd
          ON rd.note_id = d.note_id AND TRY_CAST(rd.subject_id AS BIGINT) = d.subject_id
        WHERE d.note_type = 'RR' AND length(d.text) > 0
        GROUP BY d.episode_id, d.note_id, d.event_time, d.available_time, d.recorded_time, d.text
        ORDER BY d.episode_id, d.event_time, d.note_id
    """).fetchall()

    result: dict[str, list[dict]] = defaultdict(list)
    seen: dict[str, set[str]] = defaultdict(set)
    for ep_id, note_id, event_time, available_time, recorded_time, text, details in rows:
        ep_key = str(ep_id)
        exam_name = _guess_exam_name(text)
        if exam_name in seen[ep_key]:
            continue
        seen[ep_key].add(exam_name)
        result[ep_key].append({
            "note_id": note_id,
            "exam_name": exam_name,
            "charttime": str(event_time) if event_time else None,
            **_time_meta(event_time, available_time, recorded_time),
            "text": text,
            "details": details or [],
        })
    return dict(result)


def aggregate_ed_triage(con: duckdb.DuckDBPyConnection, base: str) -> dict[str, dict[str, Any]]:
    """Aggregate ED triage vitals. All fields are directly in raw_payload."""
    rows = con.execute(f"""
        SELECT te.episode_id, te.event_id, te.event_time, te.available_time,
               te.recorded_time, ei.raw_payload
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN {_read_parquet(base, 'event_items')} ei ON te.event_id = ei.event_id
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        WHERE te.event_type = 'ed_triage'
    """).fetchall()

    result: dict[str, dict[str, Any]] = {}
    for ep_id, event_id, event_time, available_time, recorded_time, raw_payload in rows:
        ep_key = str(ep_id)
        if ep_key in result:
            continue
        payload = _parse_payload(raw_payload)
        result[ep_key] = {
            "event_id": event_id,
            "chief_complaint": payload.get("chiefcomplaint"),
            **_time_meta(event_time, available_time, recorded_time),
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
        SELECT te.episode_id, te.event_id, ei.raw_payload, te.event_time,
               te.available_time, te.recorded_time
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN {_read_parquet(base, 'event_items')} ei ON te.event_id = ei.event_id
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        WHERE te.event_type = 'ed_vital_signs'
        ORDER BY te.episode_id, te.event_time
    """).fetchall()

    result: dict[str, list[dict]] = defaultdict(list)
    for ep_id, event_id, raw_payload, event_time, available_time, recorded_time in rows:
        payload = _parse_payload(raw_payload)
        result[str(ep_id)].append({
            "event_id": event_id,
            "charttime": payload.get("charttime") or (str(event_time) if event_time else None),
            **_time_meta(event_time, available_time, recorded_time),
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
               te.event_id, te.event_time, te.available_time, te.recorded_time,
               te.start_time, te.end_time, te.event_subtype, te.source_table
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN {_read_parquet(base, 'event_items')} ei ON te.event_id = ei.event_id
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        WHERE {where}
        ORDER BY te.episode_id, te.event_time
    """).fetchall()

    result: dict[str, list[dict]] = defaultdict(list)
    for (
        ep_id, concept, raw_payload, event_id, event_time, available_time,
        recorded_time, start_time, end_time, subtype, source_table,
    ) in rows:
        payload = _parse_payload(raw_payload)
        item = {}
        for f in payload_fields:
            item[f] = payload.get(f)
        item["event_id"] = event_id
        item.update(_time_meta(event_time, available_time, recorded_time))
        item["start_time"] = _as_text(start_time)
        item["end_time"] = _as_text(end_time)
        item["source_table"] = source_table
        item["_event_time"] = _as_text(event_time)
        item["_concept_name"] = concept
        item["_event_subtype"] = subtype
        result[str(ep_id)].append(item)
    return dict(result)


def aggregate_transfers(con: duckdb.DuckDBPyConnection, base: str) -> dict[str, list[dict]]:
    """Aggregate transfer events into ordered care-unit path."""
    rows = con.execute(f"""
        SELECT te.episode_id, te.event_id, ei.raw_payload, te.event_time,
               te.available_time, te.recorded_time
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN {_read_parquet(base, 'event_items')} ei ON te.event_id = ei.event_id
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        WHERE te.event_type = 'transfer'
        ORDER BY te.episode_id, te.event_time
    """).fetchall()

    result: dict[str, list[dict]] = defaultdict(list)
    for ep_id, event_id, raw_payload, event_time, available_time, recorded_time in rows:
        payload = _parse_payload(raw_payload)
        result[str(ep_id)].append({
            "event_id": event_id,
            "eventtype": payload.get("eventtype"),
            "careunit": payload.get("careunit"),
            "intime": str(event_time) if event_time else None,
            "outtime": payload.get("outtime"),
            **_time_meta(event_time, available_time, recorded_time),
        })
    return dict(result)


def aggregate_icu_stays(con: duckdb.DuckDBPyConnection, base: str) -> dict[str, list[dict]]:
    """Aggregate complete ICU metadata, restoring fields omitted from care_contacts."""
    rows = con.execute(f"""
        SELECT cc.episode_id, cc.contact_id, cc.start_time, cc.end_time,
               raw.first_careunit, raw.last_careunit, TRY_CAST(raw.los AS DOUBLE)
        FROM {_read_parquet(base, 'care_contacts')} cc
        JOIN batch_eps ON cc.episode_id = batch_eps.episode_id
        LEFT JOIN raw_context_icustays raw
          ON TRY_CAST(raw.stay_id AS BIGINT) = cc.stay_id
         AND TRY_CAST(raw.subject_id AS BIGINT) = cc.subject_id
        WHERE cc.contact_type = 'icu'
        ORDER BY cc.episode_id, cc.start_time
    """).fetchall()

    result: dict[str, list[dict]] = defaultdict(list)
    for ep_id, contact_id, start, end, first_careunit, last_careunit, los in rows:
        result[str(ep_id)].append({
            "contact_id": contact_id,
            "first_careunit": first_careunit,
            "last_careunit": last_careunit,
            "intime": str(start) if start else None,
            "outtime": str(end) if end else None,
            "los": los,
        })
    return dict(result)


def aggregate_provider_orders(con: duckdb.DuckDBPyConnection, base: str) -> dict[str, list[dict]]:
    """Restore parent POE rows and all linked POE-detail EAV fields."""
    rows = con.execute(f"""
        SELECT te.episode_id, te.event_id, te.event_subtype, te.event_time,
               te.available_time, te.recorded_time, te.start_time, te.end_time,
               parent.raw_payload,
               list(struct_pack(field_name := detail.concept_name,
                                field_value := detail.raw_value,
                                item_event_id := detail.item_event_id)
                    ORDER BY detail.item_ordinal) FILTER (WHERE detail.item_event_id IS NOT NULL) AS details
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        LEFT JOIN {_read_parquet(base, 'event_items')} parent
          ON parent.event_id = te.event_id AND parent.source_table LIKE '%/poe'
        LEFT JOIN {_read_parquet(base, 'event_items')} detail
          ON detail.event_id = te.event_id AND detail.source_table LIKE '%/poe_detail'
        WHERE te.event_type = 'provider_order'
        GROUP BY te.episode_id, te.event_id, te.event_subtype, te.event_time,
                 te.available_time, te.recorded_time, te.start_time, te.end_time,
                 parent.raw_payload
        ORDER BY te.episode_id, te.event_time, te.event_id
    """).fetchall()
    result: dict[str, list[dict]] = defaultdict(list)
    for (
        ep_id, event_id, subtype, event_time, available_time, recorded_time,
        start_time, end_time, raw_payload, details,
    ) in rows:
        payload = _parse_payload(raw_payload)
        result[str(ep_id)].append({
            "event_id": event_id,
            "poe_id": payload.get("poe_id"),
            "poe_seq": payload.get("poe_seq"),
            "order_type": payload.get("order_type"),
            "order_subtype": payload.get("order_subtype") or subtype,
            "transaction_type": payload.get("transaction_type"),
            "order_status": payload.get("order_status"),
            **_time_meta(event_time, available_time, recorded_time),
            "start_time": _as_text(start_time),
            "end_time": _as_text(end_time),
            "details": details or [],
        })
    return dict(result)


def aggregate_medication_administrations(
    con: duckdb.DuckDBPyConnection, base: str
) -> dict[str, list[dict]]:
    """Restore eMAR parent rows together with all eMAR detail rows."""
    rows = con.execute(f"""
        SELECT te.episode_id, te.event_id, te.event_time, te.available_time,
               te.recorded_time, parent.raw_payload,
               list(struct_pack(
                   item_event_id := detail.item_event_id,
                   concept_name := detail.concept_name,
                   raw_code := detail.raw_code,
                   raw_value := detail.raw_value,
                   raw_unit := detail.raw_unit,
                   flag := detail.flag,
                   raw_payload := detail.raw_payload
               ) ORDER BY detail.item_ordinal)
               FILTER (WHERE detail.item_event_id IS NOT NULL) AS details
        FROM {_read_parquet(base, 'timeline_events')} te
        JOIN batch_eps ON te.episode_id = batch_eps.episode_id
        LEFT JOIN {_read_parquet(base, 'event_items')} parent
          ON parent.event_id = te.event_id AND parent.source_table LIKE '%/emar'
        LEFT JOIN {_read_parquet(base, 'event_items')} detail
          ON detail.event_id = te.event_id AND detail.source_table LIKE '%/emar_detail'
        WHERE te.event_type = 'medication_administration'
        GROUP BY te.episode_id, te.event_id, te.event_time, te.available_time,
                 te.recorded_time, parent.raw_payload
        ORDER BY te.episode_id, te.event_time, te.event_id
    """).fetchall()
    result: dict[str, list[dict]] = defaultdict(list)
    for ep_id, event_id, event_time, available_time, recorded_time, raw_payload, details in rows:
        payload = _parse_payload(raw_payload)
        result[str(ep_id)].append({
            "event_id": event_id,
            "medication": payload.get("medication"),
            "charttime": payload.get("charttime") or _as_text(event_time),
            "event_txt": payload.get("event_txt"),
            "scheduletime": payload.get("scheduletime"),
            **_time_meta(event_time, available_time, recorded_time),
            "details": details or [],
        })
    return dict(result)


def aggregate_encounter_context(
    con: duckdb.DuckDBPyConnection, base: str
) -> dict[str, dict]:
    """Restore ED metadata and pre-episode outpatient baseline at the patient seam."""
    rows = con.execute(f"""
        SELECT b.episode_id,
               MIN(TRY_CAST(e.intime AS TIMESTAMP)) AS ed_start_time,
               MAX(TRY_CAST(e.outtime AS TIMESTAMP)) AS ed_end_time,
               arg_max(e.disposition, TRY_CAST(e.outtime AS TIMESTAMP)) AS ed_disposition,
               arg_min(e.arrival_transport, TRY_CAST(e.intime AS TIMESTAMP)) AS arrival_transport
        FROM batch_eps b
        JOIN {_read_parquet(base, 'episode_index')} ep ON ep.episode_id = b.episode_id
        LEFT JOIN raw_context_edstays e
          ON TRY_CAST(e.subject_id AS BIGINT) = ep.subject_id
         AND TRY_CAST(e.hadm_id AS BIGINT) = ep.hadm_id
        GROUP BY b.episode_id
    """).fetchall()
    return {str(ep): {
        "ed_start_time": _as_text(start), "ed_end_time": _as_text(end),
        "ed_disposition": disposition, "arrival_transport": transport,
    } for ep, start, end, disposition, transport in rows}


def aggregate_patient_baseline(
    con: duckdb.DuckDBPyConnection, base: str, max_per_measure: int = 3
) -> dict[str, list[dict]]:
    """Select only measurements available before the episode starts."""
    rows = con.execute(f"""
        WITH ranked AS (
            SELECT ep.episode_id, omr.result_name, omr.result_value,
                   TRY_CAST(omr.chartdate AS TIMESTAMP) AS measurement_time,
                   ROW_NUMBER() OVER (
                       PARTITION BY ep.episode_id, lower(trim(omr.result_name))
                       ORDER BY TRY_CAST(omr.chartdate AS DATE) DESC,
                                TRY_CAST(omr.seq_num AS BIGINT) DESC
                   ) AS rank_in_measure
            FROM batch_eps b
            JOIN {_read_parquet(base, 'episode_index')} ep ON ep.episode_id = b.episode_id
            JOIN raw_context_omr omr
              ON TRY_CAST(omr.subject_id AS BIGINT) = ep.subject_id
             AND TRY_CAST(omr.chartdate AS TIMESTAMP) < ep.episode_start_time
        )
        SELECT episode_id, result_name, result_value, measurement_time
        FROM ranked
        WHERE rank_in_measure <= {int(max_per_measure)}
        ORDER BY episode_id, result_name, measurement_time
    """).fetchall()
    result: dict[str, list[dict]] = defaultdict(list)
    for ep_id, result_name, result_value, measurement_time in rows:
        result[str(ep_id)].append({
            "result_name": result_name,
            "result_value": result_value,
            "event_time": _as_text(measurement_time),
            "available_time": _as_text(measurement_time),
            "recorded_time": _as_text(measurement_time),
            "_concept_name": result_name,
        })
    return dict(result)


def aggregate_longitudinal_refs(
    con: duckdb.DuckDBPyConnection, base: str
) -> dict[str, list[dict]]:
    """Expose prior/later episode references without copying future content."""
    rows = con.execute(f"""
        SELECT r.episode_id, r.referenced_type, r.referenced_id,
               r.available_time, r.history_relation
        FROM {_read_parquet(base, 'patient_history_refs')} r
        JOIN batch_eps ON r.episode_id = batch_eps.episode_id
        ORDER BY r.episode_id, r.available_time, r.referenced_id
    """).fetchall()
    result: dict[str, list[dict]] = defaultdict(list)
    for ep_id, referenced_type, referenced_id, available_time, relation in rows:
        result[str(ep_id)].append({
            "referenced_type": referenced_type,
            "referenced_id": referenced_id,
            "available_time": _as_text(available_time),
            "history_relation": relation,
            "content_included": False,
        })
    return dict(result)


def _as_text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _time_meta(event_time: Any, available_time: Any, recorded_time: Any) -> dict[str, str | None]:
    return {
        "event_time": _as_text(event_time),
        "available_time": _as_text(available_time),
        "recorded_time": _as_text(recorded_time),
    }


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
