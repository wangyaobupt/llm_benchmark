from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from string import Template
from typing import Any

import duckdb

from . import __version__
from .paths import DatasetPaths


OUTPUT_FILES = (
    "case_index.parquet",
    "text_documents.parquet",
    "note_details.parquet",
    "quality_report.json",
)


def _sql_literal(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def _load_sql(name: str, substitutions: dict[str, str] | None = None) -> str:
    sql_path = Path(__file__).resolve().parents[0] / "sql" / name
    sql = sql_path.read_text(encoding="utf-8")
    return Template(sql).substitute(substitutions or {})


def _ensure_safe_output(data_root: Path, output_dir: Path, overwrite: bool) -> None:
    root = data_root.resolve()
    output = output_dir.resolve()
    if output == root or root in output.parents:
        raise ValueError("输出目录不能位于原始 MIMIC 数据目录内。")
    existing = [output / name for name in OUTPUT_FILES if (output / name).exists()]
    if existing and not overwrite:
        details = "\n".join(f"- {path}" for path in existing)
        raise FileExistsError(f"输出已存在；如需明确覆盖请增加 --overwrite：\n{details}")
    for path in existing:
        if path.is_file():
            path.unlink()


def _metrics_to_report(rows: list[tuple[str, str, str, int]]) -> dict[str, Any]:
    report: dict[str, Any] = {
        "pipeline": {
            "name": "mimic-benchmark-stage1",
            "version": __version__,
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "duckdb": duckdb.__version__,
            "sources": {
                "mimic_iv": "3.1",
                "mimic_iv_note": "2.2",
                "mimic_iv_ed": "2.2",
            },
        }
    }
    for section, dataset, metric, value in rows:
        report.setdefault(section, {}).setdefault(dataset, {})[metric] = int(value)
    return report


def build_outputs(
    data_root: Path,
    output_dir: Path,
    *,
    memory_limit: str = "8GB",
    threads: int = 4,
    overwrite: bool = False,
) -> dict[str, Any]:
    if threads < 1:
        raise ValueError("threads 必须大于等于 1。")

    paths = DatasetPaths.from_root(Path(data_root))
    paths.validate()
    output = Path(output_dir).resolve()
    _ensure_safe_output(paths.data_root, output, overwrite)
    output.mkdir(parents=True, exist_ok=True)

    substitutions = {
        "patients_path": _sql_literal(paths.patients),
        "admissions_path": _sql_literal(paths.admissions),
        "discharge_path": _sql_literal(paths.discharge),
        "discharge_detail_path": _sql_literal(paths.discharge_detail),
        "radiology_path": _sql_literal(paths.radiology),
        "radiology_detail_path": _sql_literal(paths.radiology_detail),
        "edstays_path": _sql_literal(paths.edstays),
        "triage_path": _sql_literal(paths.triage),
        "case_index_path": _sql_literal(output / "case_index.parquet"),
        "text_documents_path": _sql_literal(output / "text_documents.parquet"),
        "note_details_path": _sql_literal(output / "note_details.parquet"),
    }

    temp_dir = Path(tempfile.mkdtemp(prefix="duckdb-", dir=output))
    connection = duckdb.connect(config={"memory_limit": memory_limit, "threads": str(threads)})
    try:
        escaped_temp = _sql_literal(temp_dir)
        connection.execute(f"SET temp_directory = {escaped_temp}")
        connection.execute("SET preserve_insertion_order = false")
        connection.execute(_load_sql("create_views.sql", substitutions))
        connection.execute(_load_sql("build_views.sql"))
        connection.execute(_load_sql("export_outputs.sql", substitutions))
        metric_rows = connection.execute(
            _load_sql("quality_checks.sql", substitutions)
        ).fetchall()
        report = _metrics_to_report(metric_rows)
    finally:
        connection.close()
        shutil.rmtree(temp_dir)

    report_path = output / "quality_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
