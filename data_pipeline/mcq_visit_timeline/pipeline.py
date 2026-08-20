"""Merge time-backfill clocks with standardized names. Never overwrites upstream."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.mcq_visit_extract.atomic import (
    atomic_write_json,
    canonical_hash,
    file_sha256,
    read_jsonl,
    read_manifest,
    remove_partial,
    write_manifest,
)
from data_pipeline.mcq_visit_standardize.io import iter_json_array

from .events import merge_visit
from .schema import (
    EVENT_ARROW_SCHEMA,
    EVENT_COLUMNS,
    FROZEN_STANDARDIZED_SHA256,
    FROZEN_TIMES_SHA256,
    SCHEMA_NAME,
    SCHEMA_VERSION,
)

BATCH_SIZE = 20_000


class TimelineError(ValueError):
    pass


def _assert_output_dir(output_dir: Path, *forbidden: Path) -> Path:
    output_dir = output_dir.resolve()
    for path in forbidden:
        if not path:
            continue
        resolved = path.resolve()
        target = resolved if resolved.is_dir() else resolved.parent
        if output_dir == target or target in output_dir.parents:
            raise TimelineError(f"refusing to write into upstream directory: {target}")
    return output_dir


def _identity(
    times_path: Path,
    standardized_path: Path,
    times_sha: str,
    standardized_sha: str,
    expected_count: int,
    limit: int | None,
    extract_manifest: Path | None,
) -> dict[str, Any]:
    return {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "times_path": str(times_path.resolve()),
        "times_sha256": times_sha,
        "standardized_path": str(standardized_path.resolve()),
        "standardized_sha256": standardized_sha,
        "expected_count": expected_count,
        "limit": limit,
        "extract_manifest": str(extract_manifest.resolve()) if extract_manifest else None,
    }


def _load_selection_hadm(extract_manifest: Path | None) -> list[str] | None:
    if extract_manifest is None:
        return None
    selection = extract_manifest.parent / "selection.jsonl"
    if not selection.is_file():
        raise TimelineError(f"selection.jsonl missing next to extract manifest: {selection}")
    rows = read_jsonl(selection)
    return [str(row.get("hadm_id") or "").strip() for row in rows]


def _zip_visits(
    times_path: Path,
    standardized_path: Path,
    *,
    limit: int | None,
) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    timed_iter = iter_json_array(times_path)
    named_iter = iter_json_array(standardized_path)
    count = 0
    while True:
        timed = next(timed_iter, None)
        named = next(named_iter, None)
        if timed is None and named is None:
            return
        if timed is None or named is None:
            if limit is not None and count >= limit:
                return
            raise TimelineError("times and standardized visit counts differ")
        count += 1
        yield timed, named
        if limit is not None and count >= limit:
            return


def _write_event_batch(writer: pq.ParquetWriter | None, batch: list[dict[str, Any]], tmp: Path) -> pq.ParquetWriter:
    table = pa.Table.from_pylist(batch, schema=EVENT_ARROW_SCHEMA)
    if writer is None:
        writer = pq.ParquetWriter(tmp, EVENT_ARROW_SCHEMA, compression="zstd")
    writer.write_table(table)
    return writer


def run(
    *,
    times_path: Path,
    standardized_path: Path,
    output_dir: Path,
    expected_count: int,
    extract_manifest: Path | None = None,
    limit: int | None = None,
    skip_fingerprint: bool = False,
    progress_every: int = 200,
) -> dict[str, Any]:
    if not times_path.is_file():
        raise TimelineError(f"times visits.json missing: {times_path}")
    if not standardized_path.is_file():
        raise TimelineError(f"standardized visits.json missing: {standardized_path}")
    output_dir = _assert_output_dir(
        output_dir,
        times_path.parent,
        standardized_path.parent,
        extract_manifest.parent if extract_manifest else None,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    times_sha = file_sha256(times_path)
    standardized_sha = file_sha256(standardized_path)
    target_count = limit if limit is not None else expected_count
    if not skip_fingerprint and target_count == 10000 and limit is None:
        if times_sha.upper() != FROZEN_TIMES_SHA256:
            raise TimelineError(
                f"times sha256 {times_sha} != frozen {FROZEN_TIMES_SHA256}; pass --skip-fingerprint to override"
            )
        if standardized_sha.upper() != FROZEN_STANDARDIZED_SHA256:
            raise TimelineError(
                "standardized sha256 mismatch vs frozen v1.0.9; pass --skip-fingerprint to override"
            )

    identity = _identity(
        times_path,
        standardized_path,
        times_sha,
        standardized_sha,
        expected_count,
        limit,
        extract_manifest,
    )
    identity_sha = canonical_hash(identity)
    manifest_path = output_dir / "manifest.json"
    existing = read_manifest(manifest_path)
    if existing is not None and existing.get("identity_sha256") != identity_sha:
        raise TimelineError("manifest identity mismatch; refusing to mix runs")
    if existing is not None and existing.get("status") == "complete":
        return existing

    selection_hadm = _load_selection_hadm(extract_manifest)
    manifest = existing or {
        "identity": identity,
        "identity_sha256": identity_sha,
        "status": "running",
        "gold": 0,
        "evaluation_status": "exploratory_unreviewed",
    }
    write_manifest(manifest_path, manifest)

    timelines_path = output_dir / "visit_timelines.jsonl"
    facts_path = output_dir / "presentation_facts.jsonl"
    events_path = output_dir / "visit_events.parquet"
    for path in (timelines_path, facts_path, events_path):
        remove_partial(path)

    timelines_tmp = timelines_path.with_name(timelines_path.name + ".partial")
    facts_tmp = facts_path.with_name(facts_path.name + ".partial")
    events_tmp = events_path.with_name(events_path.name + ".partial")

    kind_counts: Counter[str] = Counter()
    lab_available = 0
    lab_total = 0
    visits = 0
    hadm_ids: list[str] = []
    writer: pq.ParquetWriter | None = None
    batch: list[dict[str, Any]] = []

    try:
        with timelines_tmp.open("w", encoding="utf-8", newline="\n") as timeline_handle, facts_tmp.open(
            "w", encoding="utf-8", newline="\n"
        ) as facts_handle:
            for timed, named in _zip_visits(times_path, standardized_path, limit=limit):
                header, events, facts = merge_visit(timed, named)
                hadm_ids.append(str(header["hadm_id"]))
                visits += 1
                kind_counts.update(str(event["event_kind"]) for event in events)
                for event in events:
                    if event["event_kind"] == "lab_resulted":
                        lab_total += 1
                        if event.get("available_time"):
                            lab_available += 1
                    batch.append({key: event.get(key) for key in EVENT_COLUMNS})
                if len(batch) >= BATCH_SIZE:
                    writer = _write_event_batch(writer, batch, events_tmp)
                    batch = []
                timeline_handle.write(
                    json.dumps({**header, "events": events}, ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )
                facts_handle.write(json.dumps(facts, ensure_ascii=False, separators=(",", ":")) + "\n")
                if progress_every and visits % progress_every == 0:
                    print(f"mcq_visit_timeline visits={visits} events={sum(kind_counts.values())}")
            timeline_handle.flush()
            os.fsync(timeline_handle.fileno())
            facts_handle.flush()
            os.fsync(facts_handle.fileno())
        if batch:
            writer = _write_event_batch(writer, batch, events_tmp)
        if writer is None:
            empty = pa.Table.from_pylist([], schema=EVENT_ARROW_SCHEMA)
            pq.write_table(empty, events_tmp, compression="zstd")
        else:
            writer.close()
            writer = None
    except Exception:
        if writer is not None:
            writer.close()
        raise

    if visits != target_count:
        raise TimelineError(f"row count {visits} != expected {target_count}")
    if len(set(hadm_ids)) != len(hadm_ids):
        raise TimelineError("hadm_id is not unique")
    if selection_hadm is not None:
        expected_ids = selection_hadm[:target_count] if limit is not None else selection_hadm
        if limit is None and len(expected_ids) != visits:
            raise TimelineError(f"selection count {len(expected_ids)} != visits {visits}")
        if hadm_ids != [str(value).strip() for value in expected_ids]:
            raise TimelineError("hadm_id order/set does not match extract selection.jsonl")

    os.replace(timelines_tmp, timelines_path)
    os.replace(facts_tmp, facts_path)
    os.replace(events_tmp, events_path)

    lab_rate = round(lab_available / lab_total, 4) if lab_total else None
    summary = {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "visits": visits,
        "unique_hadm_id": len(set(hadm_ids)),
        "event_count": sum(kind_counts.values()),
        "event_kind_counts": dict(sorted(kind_counts.items())),
        "lab_result_rows": lab_total,
        "lab_storetime_rate": lab_rate,
        "medication_rows": int(kind_counts.get("medication_prescribed", 0)),
        "procedure_rows": int(kind_counts.get("procedure_recorded", 0)),
        "radiology_rows": int(kind_counts.get("radiology_reported", 0)),
        "times_sha256": times_sha,
        "standardized_sha256": standardized_sha,
        "events_sha256": file_sha256(events_path),
        "timelines_sha256": file_sha256(timelines_path),
        "facts_sha256": file_sha256(facts_path),
        "gold": 0,
        "status": "exploratory_unreviewed",
        "does_not_overwrite_upstream": True,
    }
    atomic_write_json(output_dir / "summary.json", summary)
    manifest["status"] = "complete"
    manifest["summary"] = summary
    write_manifest(manifest_path, manifest)
    return manifest


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge visit clocks and standardized names into a timeline")
    parser.add_argument("--times", type=Path, required=True, help="time-backfill visits.json")
    parser.add_argument("--standardized", type=Path, required=True, help="visits_standardized.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--extract-manifest", type=Path, help="frozen extract manifest.json for hadm identity")
    parser.add_argument("--limit", type=int, help="smoke: first N visits in file order")
    parser.add_argument("--skip-fingerprint", action="store_true")
    parser.add_argument("--progress-every", type=int, default=200)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        manifest = run(
            times_path=args.times,
            standardized_path=args.standardized,
            output_dir=args.output_dir,
            expected_count=args.expected_count,
            extract_manifest=args.extract_manifest,
            limit=args.limit,
            skip_fingerprint=args.skip_fingerprint,
            progress_every=args.progress_every,
        )
    except (TimelineError, ValueError, FileNotFoundError) as exc:
        print(f"mcq_visit_timeline failed: {exc}")
        return 1
    summary = manifest.get("summary") or {}
    print(
        f"complete visits={summary.get('visits')} "
        f"events={summary.get('event_count')} "
        f"labs={summary.get('lab_result_rows')} "
        f"output={args.output_dir}"
    )
    return 0
