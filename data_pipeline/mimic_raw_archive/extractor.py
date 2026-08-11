"""Deep Module implementing staged, sharded and resumable raw extraction."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import shutil
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import duckdb

from data_pipeline.mimic_source_catalog import SOURCE_BY_KEY

from . import SCHEMA_NAME, SCHEMA_VERSION
from .catalog import (
    ARCHIVE_SOURCES,
    REFERENCE_SOURCE_KEYS,
    ArchiveSource,
    validate_catalog,
)
from .config import RawArchiveConfig
from .manifest import (
    canonical_hash,
    file_sha256,
    read_manifest,
    source_fingerprint,
    write_manifest,
)
from .schema import build_record
from .selection import select_admissions


def run(config: RawArchiveConfig) -> dict[str, Any]:
    """Public Interface: produce or resume one raw admission archive run."""
    config.validate()
    validate_catalog()
    _validate_source_headers(config)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    selection = _load_or_create_selection(config)
    manifest_path = config.output_dir / "manifest.json"
    manifest = _load_or_create_manifest(config, selection, manifest_path)
    _create_staging(config, selection, manifest, manifest_path)
    _stage_reference_tables(config, manifest, manifest_path)
    _assemble_missing_shards(config, selection, manifest, manifest_path)
    merge_report = _merge_shards(config, manifest)
    manifest["merged"] = merge_report
    write_manifest(manifest_path, manifest)
    return manifest


def _validate_source_headers(config: RawArchiveConfig) -> None:
    keys = [source.key for source in ARCHIVE_SOURCES] + list(REFERENCE_SOURCE_KEYS)
    errors = []
    for key in keys:
        spec = SOURCE_BY_KEY[key]
        path = config.data_root / spec.relative_path
        if not path.is_file():
            errors.append(f"missing: {path}")
            continue
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
            actual = tuple(next(csv.reader(handle), ()))
        if actual != spec.header:
            errors.append(f"header drift: {path}")
    if errors:
        raise ValueError("raw source validation failed:\n" + "\n".join(errors))


def _load_or_create_selection(config: RawArchiveConfig) -> list[dict[str, Any]]:
    path = config.output_dir / "selection.jsonl"
    if path.exists():
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        if len(rows) != config.sample_size:
            raise ValueError("existing selection size does not match configuration")
        _validate_selection_rows(rows)
        return rows

    if config.selection_input is not None:
        admissions = [
            json.loads(line)
            for line in config.selection_input.read_text(encoding="utf-8").splitlines()
            if line
        ]
        if len(admissions) != config.sample_size:
            raise ValueError(
                f"external selection rows {len(admissions)} != sample_size {config.sample_size}"
            )
        _validate_selection_rows(admissions)
    else:
        admissions = select_admissions(
            config.data_root / SOURCE_BY_KEY["admissions"].relative_path,
            config.sample_size,
            config.development_percent,
        )
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in admissions:
            output = dict(row)
            output["shard_id"] = int(row["selection_rank"]) // config.shard_size
            handle.write(json.dumps(output, separators=(",", ":")) + "\n")
    temporary.replace(path)
    return [
        {**row, "shard_id": int(row["selection_rank"]) // config.shard_size}
        for row in admissions
    ]


def _validate_selection_rows(rows: list[dict[str, Any]]) -> None:
    required = {"subject_id", "hadm_id", "selection_rank"}
    if any(not required.issubset(row) for row in rows):
        raise ValueError("selection rows require subject_id, hadm_id and selection_rank")
    ranks = [int(row["selection_rank"]) for row in rows]
    if sorted(ranks) != list(range(len(rows))):
        raise ValueError("selection_rank must be contiguous and unique from zero")
    hadm_ids = [str(row["hadm_id"]) for row in rows]
    if len(hadm_ids) != len(set(hadm_ids)):
        raise ValueError("selection contains duplicate hadm_id")


def _load_or_create_manifest(
    config: RawArchiveConfig,
    selection: list[dict[str, Any]],
    path: Path,
) -> dict[str, Any]:
    fingerprints = {
        key: source_fingerprint(
            config.data_root / SOURCE_BY_KEY[key].relative_path,
            SOURCE_BY_KEY[key].header,
        )
        for key in [source.key for source in ARCHIVE_SOURCES] + list(REFERENCE_SOURCE_KEYS)
    }
    identity = {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "data_root": config.data_root.resolve().as_posix(),
        "sample_size": config.sample_size,
        "shard_size": config.shard_size,
        "development_percent": config.development_percent,
        "archive_sources": [source.key for source in ARCHIVE_SOURCES],
        "reference_sources": list(REFERENCE_SOURCE_KEYS),
        "selection_sha256": canonical_hash(selection),
        "source_fingerprints": fingerprints,
    }
    identity_hash = canonical_hash(identity)
    existing = read_manifest(path)
    if existing is not None:
        if existing.get("identity_sha256") != identity_hash:
            raise ValueError("manifest identity mismatch; refusing to mix extraction runs")
        return existing
    manifest = {
        "identity": identity,
        "identity_sha256": identity_hash,
        "staging": {},
        "reference_tables": {},
        "shards": {},
        "merged": None,
    }
    write_manifest(path, manifest)
    return manifest


def _connect(config: RawArchiveConfig, temp_name: str) -> duckdb.DuckDBPyConnection:
    temp_dir = config.output_dir / "duckdb_temp" / temp_name
    temp_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(
        config={
            "threads": str(config.duckdb_threads),
            "memory_limit": config.duckdb_memory_limit,
        }
    )
    con.execute(f"SET temp_directory={_sql_literal(temp_dir)}")
    con.execute("SET preserve_insertion_order=false")
    return con


def _populate_selection(
    con: duckdb.DuckDBPyConnection, selection: list[dict[str, Any]]
) -> None:
    con.execute(
        "CREATE TEMP TABLE selected_admissions("
        "shard_id INTEGER, subject_id VARCHAR, hadm_id VARCHAR)"
    )
    con.executemany(
        "INSERT INTO selected_admissions VALUES (?, ?, ?)",
        [(row["shard_id"], row["subject_id"], row["hadm_id"]) for row in selection],
    )


def _create_staging(
    config: RawArchiveConfig,
    selection: list[dict[str, Any]],
    manifest: dict[str, Any],
    manifest_path: Path,
) -> None:
    staging_root = config.output_dir / "staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    for source in ARCHIVE_SOURCES:
        final_dir = staging_root / source.key
        if manifest["staging"].get(source.key, {}).get("status") == "complete":
            if not final_dir.exists():
                raise FileNotFoundError(f"manifest references missing staging: {final_dir}")
            continue
        if final_dir.exists():
            manifest["staging"][source.key] = {
                "status": "complete",
                "recovered_after_rename": True,
            }
            write_manifest(manifest_path, manifest)
            continue

        partial_dir = staging_root / f"{source.key}.partial"
        completion_marker = partial_dir / "_ARCHIVE_COPY_COMPLETE.json"
        if completion_marker.is_file():
            copy_report = json.loads(completion_marker.read_text(encoding="utf-8"))
            partial_dir.replace(final_dir)
            manifest["staging"][source.key] = {
                "status": "complete",
                "rows": int(copy_report["rows"]),
                "recovered_from_completion_marker": True,
            }
            write_manifest(manifest_path, manifest)
            continue

        _remove_partial_directory(partial_dir, staging_root)
        query = _staging_query(config, source)
        con = _connect(config, f"staging-{source.key}")
        try:
            _populate_selection(con, selection)
            result = con.execute(
                f"COPY ({query}) TO {_sql_literal(partial_dir)} "
                "(FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY (_archive_shard_id))"
            ).fetchone()
        finally:
            con.close()
        if result is None:
            raise RuntimeError(f"COPY returned no row count for {source.key}")
        copy_rows = int(result[0])
        completion_marker.write_text(
            json.dumps({"source": source.key, "rows": copy_rows}),
            encoding="utf-8",
        )
        partial_dir.replace(final_dir)
        manifest["staging"][source.key] = {
            "status": "complete",
            "rows": copy_rows,
        }
        write_manifest(manifest_path, manifest)


def _staging_query(config: RawArchiveConfig, source: ArchiveSource) -> str:
    child_spec = source.source
    child_path = config.data_root / child_spec.relative_path
    child_fields = ", ".join(f'c."{field}"' for field in child_spec.header)
    child = f"read_csv_auto({_sql_literal(child_path)}, header=true, all_varchar=true) c"
    prefix = (
        "SELECT s.shard_id AS _archive_shard_id, "
        "s.subject_id AS _archive_subject_id, s.hadm_id AS _archive_hadm_id, "
        f"{child_fields} FROM "
    )
    if source.link == "direct_hadm":
        return (
            prefix + child
            + " JOIN selected_admissions s ON c.subject_id=s.subject_id AND c.hadm_id=s.hadm_id"
        )
    if source.link == "subject":
        return prefix + child + " JOIN selected_admissions s ON c.subject_id=s.subject_id"
    if source.link == "ed_parent":
        return (
            prefix + child
            + " JOIN selected_admissions s ON c.subject_id=s.subject_id AND c.hadm_id=s.hadm_id"
        )
    if source.link == "ed_child":
        parent_spec = SOURCE_BY_KEY["edstays"]
        parent_path = config.data_root / parent_spec.relative_path
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
        match_sql = " AND ".join(
            f"c.{field}=p.{field}" for field in source.match_fields
        )
        return (
            prefix + child + " JOIN " + parent
            + f" ON c.subject_id=p.subject_id AND {match_sql}"
            + " JOIN selected_admissions s ON p.subject_id=s.subject_id AND p.hadm_id=s.hadm_id"
        )
    raise ValueError(f"unsupported linkage rule: {source.link}")


def _stage_reference_tables(
    config: RawArchiveConfig,
    manifest: dict[str, Any],
    manifest_path: Path,
) -> None:
    root = config.output_dir / "reference_tables"
    root.mkdir(parents=True, exist_ok=True)
    con = _connect(config, "references")
    try:
        for key in REFERENCE_SOURCE_KEYS:
            destination = root / f"{key}.parquet"
            if manifest["reference_tables"].get(key, {}).get("status") == "complete":
                if not destination.exists():
                    raise FileNotFoundError(destination)
                continue
            source = config.data_root / SOURCE_BY_KEY[key].relative_path
            partial = destination.with_suffix(destination.suffix + ".partial")
            if partial.exists():
                partial.unlink()
            con.execute(
                f"COPY (SELECT * FROM read_csv_auto({_sql_literal(source)}, header=true, all_varchar=true)) "
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


def _assemble_missing_shards(
    config: RawArchiveConfig,
    selection: list[dict[str, Any]],
    manifest: dict[str, Any],
    manifest_path: Path,
) -> None:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in selection:
        grouped[int(row["shard_id"])].append(row)
    pending = []
    for shard_id, rows in sorted(grouped.items()):
        part = config.output_dir / "parts" / f"part-{shard_id:05d}.jsonl"
        state = manifest["shards"].get(str(shard_id), {})
        if state.get("status") == "complete":
            if not part.exists() or file_sha256(part) != state.get("sha256"):
                raise ValueError(f"completed shard integrity failure: {shard_id}")
            continue
        pending.append((shard_id, rows))
    if not pending:
        return
    (config.output_dir / "parts").mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=config.workers) as executor:
        futures = {
            executor.submit(_assemble_shard, config, shard_id, rows): shard_id
            for shard_id, rows in pending
        }
        for future in as_completed(futures):
            shard_id = futures[future]
            report = future.result()
            manifest["shards"][str(shard_id)] = report
            write_manifest(manifest_path, manifest)


def _assemble_shard(
    config: RawArchiveConfig,
    shard_id: int,
    selection: list[dict[str, Any]],
) -> dict[str, Any]:
    con = _connect(config, f"shard-{shard_id:05d}")
    admissions: dict[str, dict[str, Any]] = {
        str(row["hadm_id"]): {
            "subject_id": str(row["subject_id"]),
            "rows": defaultdict(list),
        }
        for row in selection
    }
    source_counts: Counter[str] = Counter()
    try:
        for source in ARCHIVE_SOURCES:
            shard_dir = (
                config.output_dir / "staging" / source.key
                / f"_archive_shard_id={shard_id}"
            )
            files = list(shard_dir.glob("*.parquet")) if shard_dir.exists() else []
            if not files:
                continue
            columns = ["_archive_hadm_id", *source.source.header]
            select_columns = ", ".join(f'"{column}"' for column in columns)
            cursor = con.execute(
                f"SELECT {select_columns} FROM read_parquet({_sql_literal(shard_dir / '*.parquet')})"
            )
            while True:
                batch = cursor.fetchmany(10_000)
                if not batch:
                    break
                for values in batch:
                    hadm_id = str(values[0])
                    row = dict(zip(source.source.header, values[1:]))
                    admissions[hadm_id]["rows"][source.key].append(row)
                    source_counts[source.key] += 1
    finally:
        con.close()

    part = config.output_dir / "parts" / f"part-{shard_id:05d}.jsonl"
    partial = part.with_suffix(part.suffix + ".partial")
    if partial.exists():
        partial.unlink()
    bytes_written = 0
    records = 0
    with partial.open("w", encoding="utf-8", newline="\n") as handle:
        for selected in sorted(selection, key=lambda row: int(row["selection_rank"])):
            hadm_id = str(selected["hadm_id"])
            payload = admissions[hadm_id]
            record = build_record(payload["subject_id"], hadm_id, payload["rows"])
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            handle.write(line + "\n")
            bytes_written += len(line.encode("utf-8")) + 1
            records += 1
    partial.replace(part)
    return {
        "status": "complete",
        "records": records,
        "bytes": bytes_written,
        "sha256": file_sha256(part),
        "source_rows": dict(source_counts),
    }


def _merge_shards(config: RawArchiveConfig, manifest: dict[str, Any]) -> dict[str, Any]:
    expected_records = sum(
        int(state["records"]) for state in manifest["shards"].values()
        if state.get("status") == "complete"
    )
    if expected_records != config.sample_size:
        raise ValueError(
            f"cannot merge: complete shard records {expected_records} != {config.sample_size}"
        )
    config.merged_path.parent.mkdir(parents=True, exist_ok=True)
    partial = config.merged_path.with_suffix(config.merged_path.suffix + ".partial")
    if partial.exists():
        partial.unlink()
    records = 0
    with partial.open("wb") as output:
        for shard_id in sorted(int(key) for key in manifest["shards"]):
            part = config.output_dir / "parts" / f"part-{shard_id:05d}.jsonl"
            with part.open("rb") as source:
                for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
                    output.write(chunk)
            records += int(manifest["shards"][str(shard_id)]["records"])
    partial.replace(config.merged_path)
    return {
        "status": "complete",
        "records": records,
        "bytes": config.merged_path.stat().st_size,
        "sha256": file_sha256(config.merged_path),
        "path": config.merged_path.as_posix(),
    }


def _remove_partial_directory(path: Path, allowed_parent: Path) -> None:
    if not path.exists():
        return
    resolved = path.resolve()
    parent = allowed_parent.resolve()
    if resolved.parent != parent or not resolved.name.endswith(".partial"):
        raise ValueError(f"unsafe partial directory target: {resolved}")
    shutil.rmtree(resolved)


def _sql_literal(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build sharded raw MIMIC admission JSONL with resume support"
    )
    parser.add_argument("--data-root", type=Path, default=RawArchiveConfig.data_root)
    parser.add_argument("--output-dir", type=Path, default=RawArchiveConfig.output_dir)
    parser.add_argument("--merged-output", type=Path, default=RawArchiveConfig.merged_path)
    parser.add_argument("--sample-size", type=int)
    parser.add_argument("--selection-input", type=Path)
    parser.add_argument("--shard-size", type=int, default=1_000)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--duckdb-threads", type=int, default=4)
    parser.add_argument("--duckdb-memory-limit", default="12GB")
    return parser


def main() -> None:
    args = create_parser().parse_args()
    sample_size = args.sample_size
    if sample_size is None and args.selection_input is not None:
        with args.selection_input.open("r", encoding="utf-8") as handle:
            sample_size = sum(1 for line in handle if line.strip())
    if sample_size is None:
        sample_size = 10_000
    config = RawArchiveConfig(
        data_root=args.data_root,
        output_dir=args.output_dir,
        merged_path=args.merged_output,
        sample_size=sample_size,
        shard_size=args.shard_size,
        workers=args.workers,
        duckdb_threads=args.duckdb_threads,
        duckdb_memory_limit=args.duckdb_memory_limit,
        selection_input=args.selection_input,
    )
    report = run(config)
    print(json.dumps(report["merged"], ensure_ascii=False, indent=2))
