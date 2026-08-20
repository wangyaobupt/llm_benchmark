"""Resumable MIMIC → 10k visit extract."""

from __future__ import annotations

import argparse
import csv
import gzip
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq

from data_pipeline.mimic_source_catalog import SOURCE_BY_KEY

from .assemble import (
    DeliverableError,
    assert_deliverable_record,
    project_result,
    write_csv,
    write_json_array,
)
from .atomic import (
    atomic_write_jsonl,
    canonical_hash,
    file_sha256,
    read_jsonl,
    read_manifest,
    remove_partial,
    write_manifest,
)
from .catalog import DICTIONARY_KEYS, FACT_SOURCES, REQUIRED_SOURCE_KEYS, validate_catalog
from .columns import RESULT_COLUMNS, SCHEMA_NAME, SCHEMA_VERSION
from .config import VisitExtractConfig
from .extract import build_visit
from .funnel import FunnelError, run_funnel
from .progress import write_progress
from .selection import in_sample_pool, select_eligible


class VisitExtractError(ValueError):
    pass


def _sql_literal(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def _validate_source_headers(config: VisitExtractConfig) -> dict[str, dict[str, Any]]:
    from data_pipeline.mimic_raw_archive.manifest import source_fingerprint

    errors: list[str] = []
    fingerprints: dict[str, dict[str, Any]] = {}
    for key in REQUIRED_SOURCE_KEYS:
        spec = SOURCE_BY_KEY[key]
        path = config.data_root / spec.relative_path
        if not path.is_file():
            errors.append(f"missing: {path}")
            continue
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
            actual = tuple(next(csv.reader(handle), ()))
        if actual != spec.header:
            errors.append(f"header drift: {path}")
            continue
        fingerprints[key] = source_fingerprint(path, spec.header)
    if errors:
        raise VisitExtractError("source validation failed:\n" + "\n".join(errors))
    return fingerprints


def _identity(config: VisitExtractConfig, fingerprints: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "data_root": config.data_root.resolve().as_posix(),
        "sample_size": config.sample_size,
        "shard_size": config.shard_size,
        "development_percent": config.development_percent,
        "sample_pool": config.sample_pool,
        "funnel_shard_size": config.funnel_shard_size,
        "result_columns": list(RESULT_COLUMNS),
        "source_fingerprints": fingerprints,
    }


def _load_or_create_manifest(
    config: VisitExtractConfig,
    fingerprints: dict[str, dict[str, Any]],
    path: Path,
) -> dict[str, Any]:
    identity = _identity(config, fingerprints)
    identity_sha256 = canonical_hash(identity)
    existing = read_manifest(path)
    if existing is not None:
        if existing.get("identity_sha256") != identity_sha256:
            raise VisitExtractError(
                "manifest identity mismatch; refusing to mix extraction runs"
            )
        return existing
    manifest = {
        "identity": identity,
        "identity_sha256": identity_sha256,
        "funnel": {},
        "selection": {},
        "staging": {},
        "reference_tables": {},
        "shards": {},
        "working": {},
        "deliverables": {},
    }
    write_manifest(path, manifest)
    return manifest


def _load_or_create_selection(
    config: VisitExtractConfig,
    eligible: list[dict[str, Any]],
    manifest: dict[str, Any],
    manifest_path: Path,
) -> list[dict[str, Any]]:
    path = config.output_dir / "selection.jsonl"
    if path.exists():
        rows = read_jsonl(path)
        if len(rows) != config.sample_size:
            raise VisitExtractError(
                f"selection row count {len(rows)} != sample_size {config.sample_size}"
            )
        ranks = [row.get("selection_rank") for row in rows]
        if ranks != list(range(config.sample_size)):
            raise VisitExtractError("selection_rank must be 0..sample_size-1")
        hadm_ids = [row["hadm_id"] for row in rows]
        if len(set(hadm_ids)) != len(hadm_ids):
            raise VisitExtractError("selection hadm_id is not unique")
        actual = file_sha256(path)
        recorded = manifest.get("selection", {}).get("sha256")
        if recorded and recorded != actual:
            raise VisitExtractError("selection integrity failure")
        manifest["selection"] = {
            "status": "complete",
            "records": len(rows),
            "sha256": actual,
            "reused": True,
        }
        write_manifest(manifest_path, manifest)
        return rows
    if path.with_name(path.name + ".partial").exists():
        remove_partial(path)
    rows = select_eligible(
        eligible,
        sample_size=config.sample_size,
        development_percent=config.development_percent,
        sample_pool=config.sample_pool,
    )
    atomic_write_jsonl(path, rows)
    manifest["selection"] = {
        "status": "complete",
        "records": len(rows),
        "sha256": file_sha256(path),
        "reused": False,
    }
    write_manifest(manifest_path, manifest)
    return rows


def _connect(config: VisitExtractConfig, name: str) -> duckdb.DuckDBPyConnection:
    temp_dir = config.output_dir / "duckdb_temp" / name
    temp_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET threads={config.duckdb_threads}")
    con.execute(f"SET memory_limit='{config.duckdb_memory_limit}'")
    con.execute(f"SET temp_directory={_sql_literal(temp_dir)}")
    con.execute("SET preserve_insertion_order=false")
    return con


def _staging_query(config: VisitExtractConfig, source: Any) -> str:
    child_spec = SOURCE_BY_KEY[source.key]
    child_path = config.data_root / child_spec.relative_path
    child_fields = ", ".join(f'c."{field}"' for field in child_spec.header)
    child = f"read_csv_auto({_sql_literal(child_path)}, header=true, all_varchar=true) c"
    prefix = (
        "SELECT s.shard_id AS _sel_shard_id, s.subject_id AS _sel_subject_id, "
        f"s.hadm_id AS _sel_hadm_id, {child_fields} FROM "
    )
    if source.link in {"direct_hadm", "ed_parent"}:
        return (
            prefix + child
            + " JOIN selected_admissions s ON c.subject_id=s.subject_id AND c.hadm_id=s.hadm_id"
        )
    if source.link == "subject":
        return prefix + child + " JOIN selected_admissions s ON c.subject_id=s.subject_id"
    if source.link == "ed_child":
        parent_path = config.data_root / SOURCE_BY_KEY["edstays"].relative_path
        parent = f"read_csv_auto({_sql_literal(parent_path)}, header=true, all_varchar=true) p"
        return (
            prefix + child + " JOIN " + parent
            + " ON c.subject_id=p.subject_id AND c.stay_id=p.stay_id"
            + " JOIN selected_admissions s ON p.subject_id=s.subject_id AND p.hadm_id=s.hadm_id"
        )
    if source.link == "parent":
        parent_spec = SOURCE_BY_KEY[source.parent_key]
        parent_path = config.data_root / parent_spec.relative_path
        parent = f"read_csv_auto({_sql_literal(parent_path)}, header=true, all_varchar=true) p"
        match_sql = " AND ".join(f'c."{field}"=p."{field}"' for field in source.match_fields)
        return (
            prefix + child + " JOIN " + parent
            + f" ON c.subject_id=p.subject_id AND {match_sql}"
            + " JOIN selected_admissions s ON p.subject_id=s.subject_id AND p.hadm_id=s.hadm_id"
        )
    raise VisitExtractError(f"unsupported linkage: {source.link}")


def _parquet_sha256(path: Path) -> str:
    return file_sha256(path)


def _stage_tables(
    config: VisitExtractConfig,
    selection: list[dict[str, Any]],
    manifest: dict[str, Any],
    manifest_path: Path,
) -> None:
    staging_root = config.output_dir / "staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    reference_root = config.output_dir / "reference_tables"
    reference_root.mkdir(parents=True, exist_ok=True)
    con = _connect(config, "staging")
    try:
        con.execute(
            "CREATE TABLE selected_admissions (shard_id INTEGER, subject_id VARCHAR, hadm_id VARCHAR)"
        )
        con.executemany(
            "INSERT INTO selected_admissions VALUES (?, ?, ?)",
            [
                (
                    int(row["selection_rank"]) // config.shard_size,
                    str(row["subject_id"]),
                    str(row["hadm_id"]),
                )
                for row in selection
            ],
        )
        for source in FACT_SOURCES:
            destination = staging_root / f"{source.key}.parquet"
            entry = manifest.setdefault("staging", {}).get(source.key, {})
            if entry.get("status") == "complete":
                if not destination.exists():
                    raise FileNotFoundError(f"staging complete but missing: {destination}")
                if file_sha256(destination) != entry.get("sha256"):
                    raise VisitExtractError(f"staging integrity failure: {source.key}")
                continue
            write_progress(config.output_dir, phase="staging", detail=source.key)
            remove_partial(destination)
            partial = destination.with_name(destination.name + ".partial")
            query = _staging_query(config, source)
            con.execute(
                f"COPY ({query}) TO {_sql_literal(partial)} "
                "(FORMAT PARQUET, COMPRESSION ZSTD)"
            )
            partial.replace(destination)
            manifest["staging"][source.key] = {
                "status": "complete",
                "sha256": _parquet_sha256(destination),
                "rows": int(pq.read_metadata(destination).num_rows),
            }
            write_manifest(manifest_path, manifest)
        for key in DICTIONARY_KEYS:
            destination = reference_root / f"{key}.parquet"
            entry = manifest.setdefault("reference_tables", {}).get(key, {})
            if entry.get("status") == "complete":
                if not destination.exists():
                    raise FileNotFoundError(destination)
                if file_sha256(destination) != entry.get("sha256"):
                    raise VisitExtractError(f"reference integrity failure: {key}")
                continue
            write_progress(config.output_dir, phase="reference", detail=key)
            source_path = config.data_root / SOURCE_BY_KEY[key].relative_path
            remove_partial(destination)
            partial = destination.with_name(destination.name + ".partial")
            con.execute(
                "COPY (SELECT * FROM read_csv_auto("
                f"{_sql_literal(source_path)}, header=true, all_varchar=true)) "
                f"TO {_sql_literal(partial)} (FORMAT PARQUET, COMPRESSION ZSTD)"
            )
            partial.replace(destination)
            manifest["reference_tables"][key] = {
                "status": "complete",
                "sha256": file_sha256(destination),
            }
            write_manifest(manifest_path, manifest)
    finally:
        con.close()


def _load_dictionaries(config: VisitExtractConfig) -> dict[str, Any]:
    root = config.output_dir / "reference_tables"
    lab_rows = pq.read_table(root / "d_labitems.parquet").to_pylist()
    dx_rows = pq.read_table(root / "d_icd_diagnoses.parquet").to_pylist()
    px_rows = pq.read_table(root / "d_icd_procedures.parquet").to_pylist()
    return {
        "d_labitems": {
            str(row["itemid"]).strip(): row
            for row in lab_rows
            if row.get("itemid") not in (None, "")
        },
        "d_icd_diagnoses": {
            (str(row["icd_code"]).strip(), str(row["icd_version"]).strip()): str(
                row.get("long_title") or ""
            ).strip()
            for row in dx_rows
            if row.get("long_title")
        },
        "d_icd_procedures": {
            (str(row["icd_code"]).strip(), str(row["icd_version"]).strip()): str(
                row.get("long_title") or ""
            ).strip()
            for row in px_rows
            if row.get("long_title")
        },
    }


def _load_shard_tables(
    config: VisitExtractConfig,
    shard_id: int,
    hadm_ids: list[str],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    wanted = set(hadm_ids)
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    staging_root = config.output_dir / "staging"
    con = _connect(config, f"shard-{shard_id}")
    try:
        for source in FACT_SOURCES:
            path = staging_root / f"{source.key}.parquet"
            if not path.exists():
                continue
            rows = con.execute(
                f"SELECT * FROM read_parquet({_sql_literal(path)}) "
                "WHERE _sel_shard_id = ?",
                [shard_id],
            ).to_arrow_table().to_pylist()
            for row in rows:
                hadm_id = str(row.get("_sel_hadm_id") or "")
                if hadm_id not in wanted:
                    continue
                clean = {
                    key: value
                    for key, value in row.items()
                    if not str(key).startswith("_sel_")
                }
                grouped[hadm_id][source.key].append(clean)
    finally:
        con.close()
    return grouped


def _assemble_shards(
    config: VisitExtractConfig,
    selection: list[dict[str, Any]],
    dictionaries: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
) -> None:
    working_dir = config.output_dir / "working"
    working_dir.mkdir(parents=True, exist_ok=True)
    by_shard: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in selection:
        by_shard[int(row["selection_rank"]) // config.shard_size].append(row)
    for shard_id in sorted(by_shard):
        key = str(shard_id)
        path = working_dir / f"part-{shard_id:05d}.jsonl"
        entry = manifest.setdefault("shards", {}).get(key, {})
        if entry.get("status") == "complete":
            if not path.exists():
                raise FileNotFoundError(f"completed shard missing: {path}")
            if file_sha256(path) != entry.get("sha256"):
                raise VisitExtractError(f"completed shard integrity failure: {path}")
            continue
        write_progress(config.output_dir, phase="assemble", detail=str(shard_id))
        remove_partial(path)
        shard_rows = sorted(by_shard[shard_id], key=lambda item: item["selection_rank"])
        tables = _load_shard_tables(
            config, shard_id, [row["hadm_id"] for row in shard_rows]
        )
        records = []
        for selection_row in shard_rows:
            record = build_visit(
                selection_row=selection_row,
                tables=tables.get(str(selection_row["hadm_id"]), {}),
                dictionaries=dictionaries,
            )
            if record is None:
                raise VisitExtractError(
                    f"sampled visit failed extract: hadm_id={selection_row['hadm_id']}"
                )
            records.append(record)
        atomic_write_jsonl(path, records)
        manifest["shards"][key] = {
            "status": "complete",
            "records": len(records),
            "sha256": file_sha256(path),
            "path": path.name,
        }
        write_manifest(manifest_path, manifest)


def _merge_working(
    config: VisitExtractConfig,
    selection: list[dict[str, Any]],
    manifest: dict[str, Any],
    manifest_path: Path,
) -> list[dict[str, Any]]:
    working_dir = config.output_dir / "working"
    shard_ids = sorted({int(row["selection_rank"]) // config.shard_size for row in selection})
    records: list[dict[str, Any]] = []
    for shard_id in shard_ids:
        path = working_dir / f"part-{shard_id:05d}.jsonl"
        entry = manifest.get("shards", {}).get(str(shard_id), {})
        if entry.get("status") != "complete":
            raise VisitExtractError(f"shard {shard_id} is not complete")
        if file_sha256(path) != entry.get("sha256"):
            raise VisitExtractError(f"working shard hash mismatch: {path}")
        records.extend(read_jsonl(path))
    if len(records) != config.sample_size:
        raise VisitExtractError(
            f"working records {len(records)} != sample_size {config.sample_size}"
        )
    merged_path = working_dir / "visits.working.jsonl"
    atomic_write_jsonl(merged_path, records)
    manifest["working"] = {
        "status": "complete",
        "records": len(records),
        "sha256": file_sha256(merged_path),
    }
    write_manifest(manifest_path, manifest)
    return records


def _publish(
    config: VisitExtractConfig,
    working_records: list[dict[str, Any]],
    manifest: dict[str, Any],
    manifest_path: Path,
) -> None:
    results = []
    for record in working_records:
        projected = project_result(record)
        assert_deliverable_record(projected)
        results.append(projected)
    write_progress(config.output_dir, phase="publish", detail="visits.csv / visits.json")
    csv_path = config.output_dir / "visits.csv"
    json_path = config.output_dir / "visits.json"
    csv_hash = write_csv(csv_path, results)
    json_hash = write_json_array(json_path, results)
    manifest["deliverables"] = {
        "status": "complete",
        "records": len(results),
        "csv_sha256": csv_hash,
        "json_sha256": json_hash,
    }
    write_manifest(manifest_path, manifest)
    (csv_path.with_name("visits.csv.sha256")).write_text(csv_hash + "\n", encoding="ascii")
    (json_path.with_name("visits.json.sha256")).write_text(json_hash + "\n", encoding="ascii")


def run(config: VisitExtractConfig) -> dict[str, Any]:
    config.validate()
    validate_catalog()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    write_progress(config.output_dir, phase="source_validation")
    fingerprints = _validate_source_headers(config)
    manifest_path = config.output_dir / "manifest.json"
    manifest = _load_or_create_manifest(config, fingerprints, manifest_path)

    deliverables = manifest.get("deliverables", {})
    csv_path = config.output_dir / "visits.csv"
    json_path = config.output_dir / "visits.json"
    if (
        deliverables.get("status") == "complete"
        and csv_path.exists()
        and json_path.exists()
        and file_sha256(csv_path) == deliverables.get("csv_sha256")
        and file_sha256(json_path) == deliverables.get("json_sha256")
    ):
        write_progress(config.output_dir, phase="complete", detail="deliverables already complete")
        return manifest

    eligible, counts = run_funnel(config, manifest, manifest_path)
    development_eligible = [
        row
        for row in eligible
        if in_sample_pool(
            str(row["subject_id"]),
            development_percent=config.development_percent,
            sample_pool=config.sample_pool,
        )
    ]
    counts["eligible_development_count"] = len(development_eligible)
    from .atomic import atomic_write_json

    atomic_write_json(config.output_dir / "funnel.json", counts)
    write_progress(config.output_dir, phase="selection")
    selection = _load_or_create_selection(config, eligible, manifest, manifest_path)
    _stage_tables(config, selection, manifest, manifest_path)
    dictionaries = _load_dictionaries(config)
    _assemble_shards(config, selection, dictionaries, manifest, manifest_path)
    working_records = _merge_working(config, selection, manifest, manifest_path)
    _publish(config, working_records, manifest, manifest_path)
    write_progress(
        config.output_dir,
        phase="complete",
        detail=f"{len(working_records)} visits",
    )
    return manifest


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract 10k MCQ visit rows from MIMIC CSV.GZ")
    parser.add_argument("--data-root", type=Path, default=Path("data/RawData"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/derived/mcq_visit_extract/random10k_dev20"),
    )
    parser.add_argument("--sample-size", type=int, default=10_000)
    parser.add_argument("--shard-size", type=int, default=1_000)
    parser.add_argument("--development-percent", type=int, default=20)
    parser.add_argument("--sample-pool", choices=("development", "all"), default="development")
    parser.add_argument("--duckdb-threads", type=int, default=4)
    parser.add_argument("--duckdb-memory-limit", default="12GB")
    parser.add_argument("--funnel-shard-size", type=int, default=5_000)
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Start a local HTML progress dashboard in the background",
    )
    parser.add_argument("--monitor-host", default="127.0.0.1")
    parser.add_argument("--monitor-port", type=int, default=8766)
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the dashboard in a browser (implies --monitor)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    config = VisitExtractConfig(
        data_root=args.data_root,
        output_dir=args.output_dir,
        sample_size=args.sample_size,
        shard_size=args.shard_size,
        development_percent=args.development_percent,
        sample_pool=args.sample_pool,
        duckdb_threads=args.duckdb_threads,
        duckdb_memory_limit=args.duckdb_memory_limit,
        funnel_shard_size=args.funnel_shard_size,
    )
    if args.monitor or args.open_browser:
        from .monitor import start_monitor_thread

        url = start_monitor_thread(
            config.output_dir,
            host=args.monitor_host,
            port=args.monitor_port,
            open_browser=args.open_browser or args.monitor,
        )
        print(f"progress dashboard: {url}", flush=True)
    try:
        manifest = run(config)
    except (VisitExtractError, FunnelError, DeliverableError, FileNotFoundError, ValueError) as exc:
        print(f"mcq_visit_extract failed: {exc}")
        return 1
    deliverables = manifest.get("deliverables", {})
    print(
        f"complete records={deliverables.get('records')} "
        f"output={config.output_dir}"
    )
    return 0
