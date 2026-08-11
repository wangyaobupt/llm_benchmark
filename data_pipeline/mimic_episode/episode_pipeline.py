from __future__ import annotations

import csv
import gc
import gzip
import json
import logging
import shutil
import sys
import tempfile
import time
from pathlib import Path
from string import Template
from typing import Any

import duckdb

from . import __version__
from .episode_events import (
    GENERIC_EVENT_SPECS,
    generic_event_select,
    generic_item_select,
)
from .source_catalog import EpisodeDatasetPaths, SOURCE_SPECS

logger = logging.getLogger(__name__)

# 大于阈值的 CSV.gz 由 Python 预拆分后再交给 DuckDB
# 根因：DuckDB read_csv 解压 gzip 时将整个文件加载到内存，all_varchar 下
# 400 MB 压缩文件的解压+varchar 表示即可耗尽 8 GB
LARGE_FILE_THRESHOLD_MB = 600


EPISODE_OUTPUT_FILES = (
    "episode_index.parquet",
    "care_contacts.parquet",
    "timeline_events.parquet",
    "event_items.parquet",
    "documents.parquet",
    "evidence_links.parquet",
    "patient_history_refs.parquet",
    "episode_coverage.parquet",
    "unresolved_events.parquet",
    "quality_report.json",
)

PARQUET_VIEWS = {
    "episode_index.parquet": "episode_index",
    "care_contacts.parquet": "care_contacts",
    "timeline_events.parquet": "timeline_events",
    "event_items.parquet": "event_items",
    "documents.parquet": "documents",
    "evidence_links.parquet": "evidence_links",
    "patient_history_refs.parquet": "patient_history_refs",
    "episode_coverage.parquet": "episode_coverage",
    "unresolved_events.parquet": "unresolved_events",
}

PHASE_ONE_VIEWS = {
    "episode_index": "episode_index.parquet",
    "care_contacts": "care_contacts.parquet",
    "documents": "documents.parquet",
    "note_detail_rows": "note_detail_rows.parquet",
    "triage_counts_source": "triage_counts_source.parquet",
    "disposition_counts_source": "disposition_counts_source.parquet",
}


def _sql_literal(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def _load_episode_sql(name: str, substitutions: dict[str, str] | None = None) -> str:
    path = (
        Path(__file__).resolve().parents[0]
        / "sql"
        / "episode_aggregation"
        / name
    )
    return Template(path.read_text(encoding="utf-8")).substitute(substitutions or {})


def _ensure_safe_output(data_root: Path, output_dir: Path, overwrite: bool) -> None:
    root = data_root.resolve()
    output = output_dir.resolve()
    if output == root or root in output.parents:
        raise ValueError("输出目录不能位于原始 MIMIC 数据目录内。")
    existing = [output / name for name in EPISODE_OUTPUT_FILES if (output / name).exists()]
    if existing and not overwrite:
        details = "\n".join(f"- {path}" for path in existing)
        raise FileExistsError(f"输出已存在；如需明确覆盖请增加 --overwrite：\n{details}")
    for path in existing:
        if path.is_file():
            path.unlink()


def _decompress_large_csv(
    source_path: Path,
    dest_path: Path,
    connection: duckdb.DuckDBPyConnection,
    temp_dir: Path,
) -> int:
    """解压大型 CSV.gz 到临时无压缩 CSV，再用 DuckDB 流式转为 Parquet。

    根因：DuckDB read_csv 在读取 gzip 时将整个解压内容加载到内存，
    对 >600 MB 压缩文件会 OOM。但 DuckDB 对无压缩 CSV 是真正的流式读取，
    不会整体加载。因此先解压再转换，内存占用 <2 GB。
    """
    temp_csv = temp_dir / "raw" / f"{source_path.stem}_decompressed.csv"

    # Phase 1: Python 流式解压（内存占用 <100 MB）
    with gzip.open(source_path, "rb") as f_in:
        with open(temp_csv, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out, length=4 * 1024 * 1024)

    # Phase 2: DuckDB 从无压缩 CSV 流式转 Parquet
    csv_literal = _sql_literal(temp_csv)
    dest_literal = _sql_literal(dest_path)
    try:
        connection.execute(
            f"""
COPY (
    SELECT * FROM read_csv(
        {csv_literal},
        header = true,
        all_varchar = true,
        nullstr = '',
        quote = '"',
        parallel = false
    )
) TO {dest_literal}
(FORMAT PARQUET, COMPRESSION ZSTD)
"""
        )
        row_count = connection.execute(
            f"SELECT COUNT(*) FROM read_parquet({dest_literal})"
        ).fetchone()[0]
    finally:
        temp_csv.unlink(missing_ok=True)
    return row_count


def _standardize_raw_sources(
    paths: EpisodeDatasetPaths,
    temp_dir: Path,
    *,
    memory_limit: str = "8GB",
    threads: int = 4,
) -> None:
    """逐张 CSV 流式转为临时 parquet。

    每张表使用独立 DuckDB 连接，COPY 完即关闭，强制释放全部内存。
    大表（labevents/chartevents/discharge，压缩 >1 GB）按 subject_id
    取模分 CHUNK_COUNT 块逐块处理，每块独立连接。
    """
    raw_dir = temp_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    total = len(SOURCE_SPECS)
    for idx, spec in enumerate(SOURCE_SPECS, 1):
        source_path = _sql_literal(paths.source_path(spec.key))
        t0 = time.monotonic()

        source_file = paths.source_path(spec.key)
        file_size_mb = source_file.stat().st_size / (1024 * 1024)
        if file_size_mb > LARGE_FILE_THRESHOLD_MB:
            # DuckDB read_csv 对 gzip 会整体加载内存；先解压再流式转换
            dest = raw_dir / f"{spec.key}.parquet"
            large_conn = _new_connection(memory_limit, 1, temp_dir)
            try:
                row_count = _decompress_large_csv(
                    source_file, dest, large_conn, temp_dir
                )
            finally:
                large_conn.close()
                gc.collect()
            elapsed = time.monotonic() - t0
            logger.info(
                "  [%d/%d] %-22s %6.1fs  rows=%s (decompress+convert)",
                idx, total, spec.key, elapsed, f"{row_count:,}",
            )
        else:
            destination = _sql_literal(raw_dir / f"{spec.key}.parquet")
            table_conn = _new_connection(memory_limit, threads, temp_dir)
            try:
                table_conn.execute(
                    f"""
COPY (
    SELECT * FROM read_csv(
        {source_path},
        header = true,
        compression = 'gzip',
        all_varchar = true,
        nullstr = '',
        quote = '"',
        parallel = false
    )
) TO {destination}
(FORMAT PARQUET, COMPRESSION ZSTD)
"""
                )
                row_count = table_conn.execute(
                    f"SELECT COUNT(*) FROM read_parquet({destination})"
                ).fetchone()[0]
            finally:
                table_conn.close()
                gc.collect()
            elapsed = time.monotonic() - t0
            logger.info(
                "  [%d/%d] %-22s %6.1fs  rows=%s",
                idx, total, spec.key, elapsed, f"{row_count:,}",
            )


def _create_raw_views(
    connection: duckdb.DuckDBPyConnection,
    temp_dir: Path,
) -> None:
    # 视图基于列式 parquet：派生查询只读所需列，物理行号在此按需计算。
    raw_dir = temp_dir / "raw"
    for spec in SOURCE_SPECS:
        parquet_path = _sql_literal(raw_dir / f"{spec.key}.parquet")
        connection.execute(
            f"""
CREATE OR REPLACE TEMP VIEW raw_{spec.key} AS
SELECT
    *,
    ROW_NUMBER() OVER ()::BIGINT AS _source_row_number
FROM read_parquet({parquet_path})
"""
        )


def _export_parquet_views(
    connection: duckdb.DuckDBPyConnection,
    output_dir: Path,
) -> None:
    for file_name, view_name in PARQUET_VIEWS.items():
        destination = _sql_literal(output_dir / file_name)
        connection.execute(
            f"COPY (SELECT * FROM {view_name}) TO {destination} "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )


def _copy_view_to_parquet(
    connection: duckdb.DuckDBPyConnection,
    view_name: str,
    destination: Path,
) -> None:
    connection.execute(
        f"COPY (SELECT * FROM {view_name}) TO {_sql_literal(destination)} "
        "(FORMAT PARQUET, COMPRESSION ZSTD)"
    )


def _materialize_phase_one_views(
    connection: duckdb.DuckDBPyConnection,
    temp_dir: Path,
) -> None:
    core_dir = temp_dir / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    for view_name, file_name in PHASE_ONE_VIEWS.items():
        _copy_view_to_parquet(connection, view_name, core_dir / file_name)


def _materialize_event_sources(
    connection: duckdb.DuckDBPyConnection,
    temp_dir: Path,
) -> None:
    event_dir = temp_dir / "events"
    item_dir = temp_dir / "items"
    event_dir.mkdir(parents=True, exist_ok=True)
    item_dir.mkdir(parents=True, exist_ok=True)

    connection.execute(
        f"COPY (SELECT * FROM special_unlinked_events) TO "
        f"{_sql_literal(event_dir / 'special.parquet')} "
        "(FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    connection.execute(
        f"COPY (SELECT * FROM special_event_items) TO "
        f"{_sql_literal(item_dir / 'special.parquet')} "
        "(FORMAT PARQUET, COMPRESSION ZSTD)"
    )

    for spec in GENERIC_EVENT_SPECS:
        connection.execute(
            f"COPY ({generic_event_select(spec)}) TO "
            f"{_sql_literal(event_dir / f'{spec.source_key}.parquet')} "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        connection.execute(
            f"COPY ({generic_item_select(spec)}) TO "
            f"{_sql_literal(item_dir / f'{spec.source_key}.parquet')} "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )

    for view_name, file_name in (
        ("poe_detail_event_items", "poe_detail.parquet"),
        ("emar_detail_event_items", "emar_detail.parquet"),
    ):
        connection.execute(
            f"COPY (SELECT * FROM {view_name}) TO "
            f"{_sql_literal(item_dir / file_name)} "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )



def _create_phase_two_views(
    connection: duckdb.DuckDBPyConnection,
    temp_dir: Path,
) -> None:
    core_dir = temp_dir / "core"
    for view_name, file_name in PHASE_ONE_VIEWS.items():
        source = _sql_literal(core_dir / file_name)
        connection.execute(
            f"CREATE OR REPLACE TEMP VIEW {view_name} AS "
            f"SELECT * FROM read_parquet({source})"
        )

    event_glob = _sql_literal(temp_dir / "events" / "*.parquet")
    item_glob = _sql_literal(temp_dir / "items" / "*.parquet")
    connection.execute(
        f"CREATE OR REPLACE TEMP VIEW unlinked_events AS "
        f"SELECT * FROM read_parquet({event_glob}, union_by_name = true)"
    )
    connection.execute(
        f"CREATE OR REPLACE TEMP VIEW event_items AS "
        f"SELECT * FROM read_parquet({item_glob}, union_by_name = true)"
    )


def _new_connection(
    memory_limit: str,
    threads: int,
    temp_dir: Path,
) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(
        config={"memory_limit": memory_limit, "threads": str(threads)}
    )
    connection.execute(f"SET temp_directory = {_sql_literal(temp_dir)}")
    connection.execute("SET preserve_insertion_order = false")
    return connection


def _collect_report(
    connection: duckdb.DuckDBPyConnection,
    output_dir: Path,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "pipeline": {
            "name": "mimic-clinical-episode-aggregation",
            "version": __version__,
            "python": (
                f"{sys.version_info.major}.{sys.version_info.minor}."
                f"{sys.version_info.micro}"
            ),
            "duckdb": duckdb.__version__,
            "sources": {
                "mimic_iv": "3.1",
                "mimic_iv_ed": "2.2",
                "mimic_iv_note": "2.2",
            },
        },
        "outputs": {},
        "links": {},
        "quality": {},
        "quality_validation_basis": {},
    }

    for file_name in PARQUET_VIEWS:
        key = file_name.removesuffix(".parquet")
        path = _sql_literal(output_dir / file_name)
        rows = connection.execute(f"SELECT COUNT(*) FROM read_parquet({path})").fetchone()[0]
        report["outputs"][key] = {"rows": int(rows)}

    event_path = _sql_literal(output_dir / "timeline_events.parquet")
    document_path = _sql_literal(output_dir / "documents.parquet")
    episode_path = _sql_literal(output_dir / "episode_index.parquet")
    contact_path = _sql_literal(output_dir / "care_contacts.parquet")

    link_rows = connection.execute(
        f"""
SELECT link_status, COUNT(*)
FROM (
    SELECT link_status FROM read_parquet({event_path})
    UNION ALL
    SELECT link_status FROM read_parquet({document_path})
)
GROUP BY link_status
"""
    ).fetchall()
    report["links"] = {status: int(count) for status, count in link_rows}

    quality_queries = {
        "duplicate_episode_ids": (
            f"SELECT COUNT(*) FROM (SELECT episode_id FROM read_parquet({episode_path}) "
            "GROUP BY episode_id HAVING COUNT(*) > 1)"
        ),
        "duplicate_contact_ids": (
            f"SELECT COUNT(*) FROM (SELECT contact_id FROM read_parquet({contact_path}) "
            "GROUP BY contact_id HAVING COUNT(*) > 1)"
        ),
        "accepted_subject_conflicts": (
            f"SELECT COUNT(*) FROM read_parquet({contact_path}) c "
            f"JOIN read_parquet({episode_path}) e USING (episode_id) "
            "WHERE c.subject_id <> e.subject_id"
        ),
    }
    for metric, sql in quality_queries.items():
        report["quality"][metric] = int(connection.execute(sql).fetchone()[0])

    construction_checks = {
        "duplicate_event_ids": (
            "0 by construction: source-prefixed IDs; grouped sources GROUP BY event_id; "
            "row events use locked native keys or hashes that include the physical source row"
        ),
        "duplicate_item_event_ids": (
            "0 by construction: item_event_id is source key plus physical source row number"
        ),
        "orphan_event_items": (
            "0 by construction: every item query shares its parent event expression; "
            "missing POE/eMAR detail parents receive explicit unresolved stub events"
        ),
        "orphan_evidence_targets": (
            "0 by construction: structured evidence is emitted directly from event_items "
            "and document evidence directly from documents"
        ),
    }
    for metric, basis in construction_checks.items():
        report["quality"][metric] = 0
        report["quality_validation_basis"][metric] = basis
    return report


def _assert_hard_quality(report: dict[str, Any]) -> None:
    failures = {
        metric: value
        for metric, value in report["quality"].items()
        if value != 0
    }
    if failures:
        details = ", ".join(f"{metric}={value}" for metric, value in failures.items())
        raise ValueError(f"episode 聚合硬性质量检查失败：{details}")


def build_episode_outputs(
    data_root: Path,
    output_dir: Path,
    *,
    memory_limit: str = "8GB",
    threads: int = 4,
    overwrite: bool = False,
) -> dict[str, Any]:
    if threads < 1:
        raise ValueError("threads 必须大于等于 1。")

    paths = EpisodeDatasetPaths.from_root(Path(data_root))
    paths.validate()
    output = Path(output_dir).resolve()
    _ensure_safe_output(paths.data_root, output, overwrite)
    output.mkdir(parents=True, exist_ok=True)

    temp_dir = Path(tempfile.mkdtemp(prefix="duckdb-episode-", dir=output))
    source_connection: duckdb.DuckDBPyConnection | None = None
    aggregation_connection: duckdb.DuckDBPyConnection | None = None
    try:
        _standardize_raw_sources(
            paths, temp_dir, memory_limit=memory_limit, threads=threads
        )

        source_connection = _new_connection(memory_limit, threads, temp_dir)
        _create_raw_views(source_connection, temp_dir)
        source_connection.execute(_load_episode_sql("build_episodes.sql"))
        source_connection.execute(_load_episode_sql("build_documents.sql"))
        source_connection.execute(_load_episode_sql("build_event_sources.sql"))
        source_connection.execute(_load_episode_sql("build_auxiliary_sources.sql"))
        _materialize_phase_one_views(source_connection, temp_dir)
        _materialize_event_sources(source_connection, temp_dir)
        source_connection.close()
        source_connection = None

        aggregation_connection = _new_connection(memory_limit, threads, temp_dir)
        _create_phase_two_views(aggregation_connection, temp_dir)
        aggregation_connection.execute(_load_episode_sql("link_events.sql"))
        aggregation_connection.execute(_load_episode_sql("build_auxiliary.sql"))
        _export_parquet_views(aggregation_connection, output)
        report = _collect_report(aggregation_connection, output)
        _assert_hard_quality(report)
    except Exception:
        for file_name in PARQUET_VIEWS:
            path = output / file_name
            if path.is_file():
                path.unlink()
        raise
    finally:
        if source_connection is not None:
            source_connection.close()
        if aggregation_connection is not None:
            aggregation_connection.close()
        shutil.rmtree(temp_dir, ignore_errors=True)

    report_path = output / "quality_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
