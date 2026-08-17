"""Audit visit JSONL completeness against the upstream episode Parquet layer.

The audit emits aggregate metrics only. It never writes patient identifiers,
clinical text, exact event timestamps, or row-level data to its report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


DEFAULT_JSONL = Path("G:/Projects/llm_benchmark/data/rwd_benchmark_visits.jsonl")
DEFAULT_EPISODES = Path("G:/Projects/医疗数据集评测-MIMIC/outputs/episodes")
DEFAULT_OUTPUT = Path("docs/reports/data-layer-completeness-audit-metrics.json")


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        stripped = value.strip()
        return bool(stripped) and stripped != "___"
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def pct(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return round(100.0 * numerator / denominator, 4)


def summarize_distribution(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {"min": None, "median": None, "p90": None, "p99": None, "max": None, "mean": None}
    values.sort()

    def quantile(q: float) -> int:
        index = min(len(values) - 1, max(0, math.ceil(q * len(values)) - 1))
        return values[index]

    return {
        "min": values[0],
        "median": quantile(0.50),
        "p90": quantile(0.90),
        "p99": quantile(0.99),
        "max": values[-1],
        "mean": round(sum(values) / len(values), 4),
    }


def nested_get(record: dict[str, Any], path: str) -> Any:
    current: Any = record
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def observe_schema(
    value: Any,
    prefix: str,
    path_presence: Counter[str],
    path_nonempty: Counter[str],
    path_types: dict[str, Counter[str]],
    array_lengths: dict[str, list[int]],
) -> None:
    """Observe object structure without iterating every large nested array item."""
    path_presence[prefix] += 1
    path_types[prefix][type_name(value)] += 1
    if is_present(value):
        path_nonempty[prefix] += 1

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}" if prefix else key
            observe_schema(child, child_path, path_presence, path_nonempty, path_types, array_lengths)
    elif isinstance(value, list):
        array_lengths[prefix].append(len(value))
        first_non_null = next((item for item in value if item is not None), None)
        if isinstance(first_non_null, dict):
            for key, child in first_non_null.items():
                child_path = f"{prefix}[].{key}"
                path_presence[child_path] += 1
                path_types[child_path][type_name(child)] += 1
                if is_present(child):
                    path_nonempty[child_path] += 1


def has_any_time(items: list[Any], names: tuple[str, ...]) -> bool:
    for item in items:
        if not isinstance(item, dict):
            continue
        if any(is_present(item.get(name)) for name in names):
            return True
        results = item.get("results")
        if isinstance(results, list):
            for result in results:
                if isinstance(result, dict) and any(is_present(result.get(name)) for name in names):
                    return True
    return False


def scan_jsonl(path: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    started = time.time()
    visits = 0
    malformed = 0
    duplicate_visits = 0
    visit_keys: set[tuple[str, str]] = set()
    subject_counts: Counter[str] = Counter()
    rows: list[tuple[str, int, int]] = []
    top_signatures: Counter[str] = Counter()
    group_signatures: dict[str, Counter[str]] = defaultdict(Counter)
    path_presence: Counter[str] = Counter()
    path_nonempty: Counter[str] = Counter()
    path_types: dict[str, Counter[str]] = defaultdict(Counter)
    array_lengths: dict[str, list[int]] = defaultdict(list)
    coverage: Counter[str] = Counter()
    timestamp_coverage: Counter[str] = Counter()

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            visits += 1

            identifiers = record.get("identifiers") or {}
            subject_id = str(identifiers.get("subject_id") or "")
            hadm_id = str(identifiers.get("hadm_id") or "")
            visit_key = (subject_id, hadm_id)
            if visit_key in visit_keys:
                duplicate_visits += 1
            else:
                visit_keys.add(visit_key)
            subject_counts[subject_id] += 1
            if hadm_id.isdigit() and subject_id.isdigit():
                rows.append((f"H:{hadm_id}", int(subject_id), int(hadm_id)))

            top_keys = tuple(sorted(record.keys()))
            top_signatures["|".join(top_keys)] += 1
            for group, value in record.items():
                if isinstance(value, dict):
                    group_signatures[group]["|".join(sorted(value.keys()))] += 1
                observe_schema(value, group, path_presence, path_nonempty, path_types, array_lengths)

            narrative = record.get("narrative") or {}
            investigations = record.get("investigations") or {}
            diagnoses = record.get("diagnoses") or {}
            treatments = record.get("treatments") or {}
            disposition = record.get("disposition") or {}
            vitals = record.get("vitals") or {}
            demographics = record.get("demographics") or {}

            has_presentation = is_present(narrative.get("chief_complaint"))
            has_initial_vitals = any(
                is_present(vitals.get(key))
                for key in ("temperature", "heartrate", "resprate", "o2sat", "sbp", "dbp", "acuity")
            )
            has_investigation = any(
                is_present(investigations.get(key))
                for key in ("laboratory", "microbiology", "radiology", "cardiology", "respiratory")
            )
            has_diagnosis = is_present((diagnoses.get("primary") or {}).get("icd_code"))
            has_treatment = any(
                is_present(treatments.get(key))
                for key in (
                    "medications",
                    "pharmacy_orders",
                    "medication_administrations",
                    "procedures",
                    "hcpcs",
                )
            )
            has_pathway = any(
                is_present(disposition.get(key))
                for key in ("primary_service", "transfer_path", "icu_stays")
            )
            has_discharge = any(
                is_present(disposition.get(key))
                for key in (
                    "discharge_location",
                    "brief_hospital_course",
                    "discharge_medications",
                    "discharge_condition",
                    "discharge_record",
                )
            )

            flags = {
                "presentation": has_presentation,
                "initial_vitals": has_initial_vitals,
                "narrative_hpi": is_present(narrative.get("history_of_present_illness")),
                "narrative_pmh": is_present(narrative.get("past_medical_history")),
                "narrative_social_history": is_present(narrative.get("social_history")),
                "narrative_home_medications": is_present(narrative.get("medications_on_admission")),
                "narrative_allergies": is_present(narrative.get("allergies")),
                "narrative_physical_exam": is_present(narrative.get("physical_exam")),
                "discharge_note_full": is_present(narrative.get("discharge_note_full")),
                "structured_home_medications": is_present(demographics.get("home_medications")),
                "baseline_measurements": is_present(demographics.get("baseline")),
                "laboratory": is_present(investigations.get("laboratory")),
                "microbiology": is_present(investigations.get("microbiology")),
                "radiology": is_present(investigations.get("radiology")),
                "cardiology": is_present(investigations.get("cardiology")),
                "respiratory": is_present(investigations.get("respiratory")),
                "any_investigation": has_investigation,
                "primary_diagnosis": has_diagnosis,
                "ed_diagnoses": is_present(diagnoses.get("ed_diagnoses")),
                "prescriptions": is_present(treatments.get("medications")),
                "pharmacy_orders": is_present(treatments.get("pharmacy_orders")),
                "medication_administrations": is_present(treatments.get("medication_administrations")),
                "procedures": is_present(treatments.get("procedures")),
                "hcpcs": is_present(treatments.get("hcpcs")),
                "any_treatment": has_treatment,
                "primary_service": is_present(disposition.get("primary_service")),
                "transfer_path": is_present(disposition.get("transfer_path")),
                "icu_stays": is_present(disposition.get("icu_stays")),
                "drg": is_present(disposition.get("drg")),
                "brief_hospital_course": is_present(disposition.get("brief_hospital_course")),
                "discharge_medications": is_present(disposition.get("discharge_medications")),
                "discharge_condition": is_present(disposition.get("discharge_condition")),
                "discharge_instructions": is_present(disposition.get("discharge_record")),
                "discharge_location": is_present(disposition.get("discharge_location")),
                "ed_disposition": is_present(disposition.get("ed_disposition")),
                "provider_orders": is_present(record.get("provider_orders")),
                "pathway": has_pathway,
                "discharge": has_discharge,
                "flow_presentation_investigation_diagnosis": has_presentation and has_investigation and has_diagnosis,
                "flow_through_treatment": has_presentation and has_investigation and has_diagnosis and has_treatment,
                "flow_through_discharge": has_presentation and has_investigation and has_diagnosis and has_treatment and has_discharge,
                "flow_with_initial_vitals": has_presentation and has_initial_vitals and has_investigation and has_diagnosis and has_treatment and has_discharge,
                "flow_with_pathway": has_presentation and has_investigation and has_diagnosis and has_treatment and has_pathway and has_discharge,
            }
            for name, enabled in flags.items():
                if enabled:
                    coverage[name] += 1

            for key, fields in {
                "laboratory": ("charttime", "storetime"),
                "microbiology": ("charttime", "chartdate", "storetime", "storedate"),
                "radiology": ("charttime", "storetime"),
                "cardiology": ("ordertime",),
                "respiratory": ("ordertime",),
            }.items():
                items = investigations.get(key) or []
                if isinstance(items, list) and items and has_any_time(items, fields):
                    timestamp_coverage[f"{key}_visit_with_any_time"] += 1

            for key, fields in {
                "prescriptions": ("starttime", "stoptime"),
                "pharmacy_orders": ("starttime", "stoptime", "entertime", "verifiedtime"),
                "medication_administrations": ("charttime", "scheduletime", "storetime"),
                "procedures": ("chartdate", "starttime", "endtime"),
                "hcpcs": ("chartdate",),
            }.items():
                actual_key = {
                    "prescriptions": "medications",
                    "pharmacy_orders": "pharmacy_orders",
                    "medication_administrations": "medication_administrations",
                    "procedures": "procedures",
                    "hcpcs": "hcpcs",
                }[key]
                items = treatments.get(actual_key) or []
                if isinstance(items, list) and items and has_any_time(items, fields):
                    timestamp_coverage[f"{key}_visit_with_any_time"] += 1

    repeated_subjects = sum(1 for count in subject_counts.values() if count > 1)
    visits_in_repeated_subjects = sum(count for count in subject_counts.values() if count > 1)
    target_df = pd.DataFrame(rows, columns=["episode_id", "subject_id", "hadm_id"])

    result = {
        "file": str(path),
        "file_bytes": path.stat().st_size,
        "scan_seconds": round(time.time() - started, 3),
        "visits": visits,
        "malformed_json_lines": malformed,
        "duplicate_visit_keys": duplicate_visits,
        "unique_subjects": len(subject_counts),
        "subjects_with_multiple_visits": repeated_subjects,
        "visits_from_multi_visit_subjects": visits_in_repeated_subjects,
        "multi_visit_subject_pct": pct(repeated_subjects, len(subject_counts)),
        "top_level_signatures": dict(top_signatures.most_common()),
        "group_signatures": {key: dict(value.most_common()) for key, value in sorted(group_signatures.items())},
        "coverage": {
            name: {"count": count, "pct": pct(count, visits)}
            for name, count in sorted(coverage.items())
        },
        "timestamp_coverage": {
            name: {"count": count, "pct": pct(count, visits)}
            for name, count in sorted(timestamp_coverage.items())
        },
        "schema_paths": {
            path_name: {
                "present_count": path_presence[path_name],
                "present_pct": pct(path_presence[path_name], visits),
                "nonempty_count": path_nonempty[path_name],
                "nonempty_pct": pct(path_nonempty[path_name], visits),
                "types": dict(path_types[path_name]),
            }
            for path_name in sorted(path_presence)
        },
        "array_length_distributions": {
            name: summarize_distribution(values)
            for name, values in sorted(array_lengths.items())
        },
    }
    return result, target_df


def rows_to_records(cursor: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def audit_parquet(base: Path, target_df: pd.DataFrame) -> dict[str, Any]:
    started = time.time()
    con = duckdb.connect()
    con.register("target_df", target_df)
    con.execute("CREATE TEMP TABLE target_visits AS SELECT DISTINCT * FROM target_df")

    def parquet(name: str) -> str:
        return str(base / f"{name}.parquet").replace("\\", "/")

    coverage_query = f"""
        SELECT
            COUNT(*) AS target_episodes,
            SUM(CAST(has_chief_complaint AS BIGINT)) AS has_chief_complaint,
            SUM(CAST(has_triage_vitals AS BIGINT)) AS has_triage_vitals,
            SUM(CAST(has_serial_vitals AS BIGINT)) AS has_serial_vitals,
            SUM(CAST(has_laboratory AS BIGINT)) AS has_laboratory,
            SUM(CAST(has_microbiology AS BIGINT)) AS has_microbiology,
            SUM(CAST(has_radiology AS BIGINT)) AS has_radiology,
            SUM(CAST(has_orders AS BIGINT)) AS has_orders,
            SUM(CAST(has_prescriptions AS BIGINT)) AS has_prescriptions,
            SUM(CAST(has_medication_administration AS BIGINT)) AS has_medication_administration,
            SUM(CAST(has_procedures AS BIGINT)) AS has_procedures,
            SUM(CAST(has_diagnoses AS BIGINT)) AS has_diagnoses,
            SUM(CAST(has_disposition AS BIGINT)) AS has_disposition,
            SUM(CAST(has_discharge_summary AS BIGINT)) AS has_discharge_summary
        FROM read_parquet('{parquet("episode_coverage")}') ec
        JOIN target_visits t USING (episode_id)
    """
    coverage = rows_to_records(con.execute(coverage_query))[0]
    denominator = coverage["target_episodes"]
    coverage_with_pct = {
        key: value if key == "target_episodes" else {"count": value, "pct": pct(value, denominator)}
        for key, value in coverage.items()
    }

    event_query = f"""
        SELECT
            te.event_type,
            COUNT(*) AS event_count,
            COUNT(DISTINCT te.episode_id) AS episode_count,
            COUNT(te.event_time) AS event_time_count,
            COUNT(te.available_time) AS available_time_count,
            COUNT(te.recorded_time) AS recorded_time_count,
            COUNT(te.start_time) AS start_time_count,
            COUNT(te.end_time) AS end_time_count
        FROM read_parquet('{parquet("timeline_events")}') te
        JOIN target_visits t USING (episode_id)
        GROUP BY te.event_type
        ORDER BY te.event_type
    """
    event_types = rows_to_records(con.execute(event_query))
    for row in event_types:
        row["episode_pct"] = pct(row["episode_count"], denominator)
        row["event_time_pct"] = pct(row["event_time_count"], row["event_count"])
        row["available_time_pct"] = pct(row["available_time_count"], row["event_count"])
        row["recorded_time_pct"] = pct(row["recorded_time_count"], row["event_count"])

    source_query = f"""
        SELECT
            te.source_table,
            COUNT(*) AS event_count,
            COUNT(DISTINCT te.episode_id) AS episode_count
        FROM read_parquet('{parquet("timeline_events")}') te
        JOIN target_visits t USING (episode_id)
        GROUP BY te.source_table
        ORDER BY te.source_table
    """
    timeline_sources = rows_to_records(con.execute(source_query))
    for row in timeline_sources:
        row["episode_pct"] = pct(row["episode_count"], denominator)

    document_query = f"""
        SELECT
            d.document_type,
            d.source_table,
            COUNT(*) AS document_count,
            COUNT(DISTINCT d.episode_id) AS episode_count,
            COUNT(d.event_time) AS event_time_count,
            COUNT(d.available_time) AS available_time_count,
            COUNT(d.recorded_time) AS recorded_time_count
        FROM read_parquet('{parquet("documents")}') d
        JOIN target_visits t USING (episode_id)
        GROUP BY d.document_type, d.source_table
        ORDER BY d.document_type, d.source_table
    """
    documents = rows_to_records(con.execute(document_query))
    for row in documents:
        row["episode_pct"] = pct(row["episode_count"], denominator)

    contact_query = f"""
        SELECT
            c.contact_type,
            COUNT(*) AS contact_count,
            COUNT(DISTINCT c.episode_id) AS episode_count,
            COUNT(c.start_time) AS start_time_count,
            COUNT(c.end_time) AS end_time_count
        FROM read_parquet('{parquet("care_contacts")}') c
        JOIN target_visits t USING (episode_id)
        GROUP BY c.contact_type
        ORDER BY c.contact_type
    """
    contacts = rows_to_records(con.execute(contact_query))
    for row in contacts:
        row["episode_pct"] = pct(row["episode_count"], denominator)

    longitudinal_query = f"""
        WITH target_subjects AS (
            SELECT DISTINCT subject_id FROM target_visits
        ), ordered AS (
            SELECT
                e.episode_id,
                e.subject_id,
                e.episode_start_time,
                LEAD(e.episode_start_time) OVER (
                    PARTITION BY e.subject_id ORDER BY e.episode_start_time, e.episode_id
                ) AS next_episode_start
            FROM read_parquet('{parquet("episode_index")}') e
            JOIN target_subjects s USING (subject_id)
        )
        SELECT
            COUNT(*) AS target_episodes,
            SUM(CASE WHEN o.next_episode_start IS NOT NULL THEN 1 ELSE 0 END) AS with_later_episode,
            COUNT(DISTINCT CASE WHEN o.next_episode_start IS NOT NULL THEN o.subject_id END) AS subjects_with_later_episode
        FROM ordered o
        JOIN target_visits t USING (episode_id)
    """
    longitudinal = rows_to_records(con.execute(longitudinal_query))[0]
    longitudinal["with_later_episode_pct"] = pct(longitudinal["with_later_episode"], longitudinal["target_episodes"])

    temporal_query = f"""
        SELECT
            te.event_type,
            COUNT(*) AS event_count,
            SUM(CASE WHEN te.event_time < ei.episode_start_time THEN 1 ELSE 0 END) AS before_episode_start,
            SUM(CASE WHEN te.event_time > ei.clinical_end_time THEN 1 ELSE 0 END) AS after_clinical_end,
            SUM(CASE WHEN te.available_time IS NOT NULL AND te.event_time IS NOT NULL
                           AND te.available_time < te.event_time THEN 1 ELSE 0 END) AS available_before_event
        FROM read_parquet('{parquet("timeline_events")}') te
        JOIN target_visits t USING (episode_id)
        JOIN read_parquet('{parquet("episode_index")}') ei USING (episode_id)
        GROUP BY te.event_type
        ORDER BY te.event_type
    """
    temporal = rows_to_records(con.execute(temporal_query))
    for row in temporal:
        for key in ("before_episode_start", "after_clinical_end", "available_before_event"):
            row[f"{key}_pct"] = pct(row[key], row["event_count"])

    result = {
        "base": str(base),
        "scan_seconds": round(time.time() - started, 3),
        "coverage": coverage_with_pct,
        "event_types": event_types,
        "timeline_sources": timeline_sources,
        "documents": documents,
        "care_contacts": contacts,
        "longitudinal_observation": longitudinal,
        "temporal_integrity": temporal,
    }
    con.close()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--episodes", type=Path, default=DEFAULT_EPISODES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    json_metrics, target_df = scan_jsonl(args.jsonl)
    parquet_metrics = audit_parquet(args.episodes, target_df)
    output = {
        "audit_schema_version": "1.0.0",
        "privacy": "aggregate-only; no identifiers, clinical text, or exact timestamps",
        "jsonl": json_metrics,
        "episode_parquet": parquet_metrics,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(json.dumps({"output": str(args.output), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
