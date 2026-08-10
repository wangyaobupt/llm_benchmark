from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import duckdb


SOURCE_DATABASE = "MIMIC-IV"
SOURCE_VERSION = "3.1"
DEFAULT_DATA_ROOT = Path("D:/Projects/llm_benchmark/data/RawData")
DEFAULT_OUTPUT_DIR = Path("D:/Projects/llm_benchmark/data/解析")
DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024
LOOKUP_EXPORT_COLUMNS: tuple[str, ...] = (
    "source_database",
    "source_version",
    "source_module",
    "dictionary_name",
    "code_system",
    "code",
    "code_version",
    "label",
    "description",
    "category",
    "source_path",
)


@dataclass(frozen=True)
class DictionarySpec:
    name: str
    module: str
    relative_path: str
    code_system: str
    code_column: str
    label_column: str
    description_column: str | None = None
    category_column: str | None = None
    version_column: str | None = None
    key_columns: tuple[str, ...] = ()


DICTIONARIES: tuple[DictionarySpec, ...] = (
    DictionarySpec(
        name="d_labitems",
        module="hosp",
        relative_path="mimic-iv-3.1/hosp/d_labitems.csv.gz",
        code_system="MIMIC-IV laboratory itemid",
        code_column="itemid",
        label_column="label",
        category_column="category",
        key_columns=("itemid",),
    ),
    DictionarySpec(
        name="d_items",
        module="icu",
        relative_path="mimic-iv-3.1/icu/d_items.csv.gz",
        code_system="MIMIC-IV ICU itemid",
        code_column="itemid",
        label_column="label",
        category_column="category",
        key_columns=("itemid",),
    ),
    DictionarySpec(
        name="d_icd_diagnoses",
        module="hosp",
        relative_path="mimic-iv-3.1/hosp/d_icd_diagnoses.csv.gz",
        code_system="ICD diagnosis",
        code_column="icd_code",
        label_column="long_title",
        version_column="icd_version",
        key_columns=("icd_code", "icd_version"),
    ),
    DictionarySpec(
        name="d_icd_procedures",
        module="hosp",
        relative_path="mimic-iv-3.1/hosp/d_icd_procedures.csv.gz",
        code_system="ICD procedure",
        code_column="icd_code",
        label_column="long_title",
        version_column="icd_version",
        key_columns=("icd_code", "icd_version"),
    ),
    DictionarySpec(
        name="d_hcpcs",
        module="hosp",
        relative_path="mimic-iv-3.1/hosp/d_hcpcs.csv.gz",
        code_system="HCPCS",
        code_column="code",
        label_column="short_description",
        description_column="long_description",
        category_column="category",
        key_columns=("code",),
    ),
)


def _sql_literal(value: str | Path) -> str:
    return "'" + str(Path(value).resolve()).replace("\\", "/").replace("'", "''") + "'"


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _text_expression(column: str | None) -> str:
    if column is None:
        return "NULL::VARCHAR"
    return f"NULLIF(trim({_quoted(column)}), '')"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_metadata(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _export_csv_with_bom(
    connection: duckdb.DuckDBPyConnection,
    query: str,
    path: Path,
) -> None:
    partial = path.with_suffix(path.suffix + ".partial")
    connection.execute(
        f"COPY ({query}) TO {_sql_literal(partial)} "
        "(FORMAT CSV, HEADER true, FORCE_QUOTE *)"
    )
    with path.open("wb") as output, partial.open("rb") as source:
        output.write(b"\xef\xbb\xbf")
        shutil.copyfileobj(source, output, length=1024 * 1024)
    partial.unlink()


def _export_json_array(
    connection: duckdb.DuckDBPyConnection,
    query: str,
    path: Path,
) -> None:
    connection.execute(
        f"COPY ({query}) TO {_sql_literal(path)} (FORMAT JSON, ARRAY true)"
    )


def _export_open_formats(
    connection: duckdb.DuckDBPyConnection,
    staging: Path,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    csv_dir = staging / "csv"
    json_dir = staging / "json"
    lookup_json_dir = json_dir / "code_lookup"
    csv_dir.mkdir()
    json_dir.mkdir()
    lookup_json_dir.mkdir()
    by_name = {entry["name"]: entry for entry in entries}
    lookup_columns = ", ".join(_quoted(column) for column in LOOKUP_EXPORT_COLUMNS)

    for spec in DICTIONARIES:
        raw_query = f"SELECT * FROM {_quoted(spec.name)}"
        csv_path = csv_dir / f"{spec.name}.csv"
        json_path = json_dir / f"{spec.name}.json"
        lookup_json_path = lookup_json_dir / f"{spec.name}.json"
        _export_csv_with_bom(connection, raw_query, csv_path)
        _export_json_array(connection, raw_query, json_path)
        _export_json_array(
            connection,
            f"SELECT {lookup_columns} FROM code_lookup "
            f"WHERE dictionary_name = '{spec.name}'",
            lookup_json_path,
        )
        by_name[spec.name]["csv"] = _file_metadata(csv_path, staging)
        by_name[spec.name]["json"] = _file_metadata(json_path, staging)
        by_name[spec.name]["lookup_json"] = _file_metadata(lookup_json_path, staging)

    lookup_csv = csv_dir / "code_lookup.csv"
    _export_csv_with_bom(
        connection,
        f"SELECT {lookup_columns} FROM code_lookup",
        lookup_csv,
    )
    return {
        "csv": _file_metadata(lookup_csv, staging),
        "json_parts": [
            by_name[spec.name]["lookup_json"] for spec in DICTIONARIES
        ],
        "json_split_reason": (
            "A single standard JSON array exceeded 50 MiB, so the unified lookup is split "
            "by dictionary while retaining identical columns."
        ),
    }


def _source_header(path: Path) -> list[str]:
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))


def _validate_sources(data_root: Path) -> list[tuple[DictionarySpec, Path, list[str]]]:
    sources = []
    for spec in DICTIONARIES:
        path = data_root / spec.relative_path
        if not path.is_file():
            raise FileNotFoundError(f"missing MIMIC-IV dictionary: {path}")
        header = _source_header(path)
        required = {
            spec.code_column,
            spec.label_column,
            *spec.key_columns,
        }
        for optional in (spec.description_column, spec.category_column, spec.version_column):
            if optional is not None:
                required.add(optional)
        missing = sorted(required.difference(header))
        if missing:
            raise ValueError(f"{path} is missing required columns: {missing}")
        sources.append((spec, path, header))
    return sources


def _prepare_output(output_dir: Path) -> Path:
    if output_dir.exists():
        raise FileExistsError(
            f"output already exists: {output_dir}; remove it explicitly before rebuilding"
        )
    staging = output_dir.with_name(output_dir.name + ".partial")
    if staging.exists():
        raise FileExistsError(f"partial output already exists: {staging}")
    (staging / "tables").mkdir(parents=True)
    return staging


def _create_lookup_table(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE code_lookup (
            source_database VARCHAR NOT NULL,
            source_version VARCHAR NOT NULL,
            source_module VARCHAR NOT NULL,
            dictionary_name VARCHAR NOT NULL,
            code_system VARCHAR NOT NULL,
            code VARCHAR NOT NULL,
            code_version VARCHAR,
            label VARCHAR,
            description VARCHAR,
            category VARCHAR,
            source_path VARCHAR NOT NULL,
            attributes_json VARCHAR NOT NULL
        )
        """
    )


def _load_dictionary(
    connection: duckdb.DuckDBPyConnection,
    spec: DictionarySpec,
    source_path: Path,
    header: list[str],
    tables_dir: Path,
) -> dict[str, Any]:
    table = _quoted(spec.name)
    connection.execute(
        f"CREATE TABLE {table} AS "
        f"SELECT * FROM read_csv_auto({_sql_literal(source_path)}, header=true, all_varchar=true)"
    )
    row_count = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    null_key_condition = " OR ".join(
        f"{_quoted(column)} IS NULL OR trim({_quoted(column)}) = ''" for column in spec.key_columns
    )
    null_key_rows = connection.execute(
        f"SELECT count(*) FROM {table} WHERE {null_key_condition}"
    ).fetchone()[0]
    key_sql = ", ".join(_quoted(column) for column in spec.key_columns)
    duplicate_key_groups = connection.execute(
        f"SELECT count(*) FROM ("
        f"SELECT {key_sql}, count(*) AS n FROM {table} "
        f"GROUP BY {key_sql} HAVING count(*) > 1)"
    ).fetchone()[0]
    if null_key_rows or duplicate_key_groups:
        raise ValueError(
            f"{spec.name} key validation failed: "
            f"null_key_rows={null_key_rows}, duplicate_key_groups={duplicate_key_groups}"
        )

    parquet_path = tables_dir / f"{spec.name}.parquet"
    connection.execute(
        f"COPY {table} TO {_sql_literal(parquet_path)} (FORMAT PARQUET, COMPRESSION ZSTD)"
    )

    source_path_text = spec.relative_path.replace("\\", "/")
    connection.execute(
        f"""
        INSERT INTO code_lookup
        SELECT
            '{SOURCE_DATABASE}',
            '{SOURCE_VERSION}',
            '{spec.module}',
            '{spec.name}',
            '{spec.code_system}',
            trim({_quoted(spec.code_column)}),
            {_text_expression(spec.version_column)},
            {_text_expression(spec.label_column)},
            {_text_expression(spec.description_column)},
            {_text_expression(spec.category_column)},
            '{source_path_text}',
            to_json({table})
        FROM {table}
        """
    )
    return {
        "name": spec.name,
        "module": spec.module,
        "source_path": source_path_text,
        "source_bytes": source_path.stat().st_size,
        "source_sha256": _sha256(source_path),
        "columns": header,
        "key_columns": list(spec.key_columns),
        "rows": row_count,
        "null_key_rows": null_key_rows,
        "duplicate_key_groups": duplicate_key_groups,
        "parquet_path": f"tables/{parquet_path.name}",
        "parquet_bytes": parquet_path.stat().st_size,
        "parquet_sha256": _sha256(parquet_path),
    }


def _write_readme(path: Path, manifest: dict[str, Any]) -> None:
    rows = "\n".join(
        f"| `{item['name']}` | {item['module']} | {item['rows']:,} | "
        f"`{', '.join(item['key_columns'])}` |"
        for item in manifest["dictionaries"]
    )
    path.write_text(
        f"""# MIMIC-IV 3.1 编码解析字典

本目录由 `python -m mimic_dictionary` 从本机授权的 MIMIC-IV 3.1 原始文件生成。
仅包含 MIMIC-IV，不包含 MIMIC-III、患者事件、`provider` 或 `caregiver`。

## 内容

| 字典 | 模块 | 行数 | 主键 |
|---|---|---:|---|
{rows}

- `tables/*.parquet`：保留各官方字典的全部原始字段和原始拼写。
- `mimic_code_lookup.parquet`：跨字典统一查询视图。
- `mimic_dictionaries.duckdb`：包含五张原始字典表与 `code_lookup` 表。
- `csv/*.csv`：UTF-8 BOM CSV；包含五张原始字典和统一索引。
- `json/*.json`：五张原始字典的标准 JSON 数组。
- `json/code_lookup/*.json`：按字典拆分的统一索引标准 JSON 数组。
- `manifest.json`：来源、版本、字段、行数、文件大小和 SHA-256。

## 查询示例

```sql
SELECT code, label, category, attributes_json
FROM code_lookup
WHERE dictionary_name = 'd_labitems' AND code = '50878';
```

Python：

```python
import duckdb

rows = duckdb.connect('data/解析/mimic_dictionaries.duckdb', read_only=True).execute(
    "SELECT * FROM code_lookup WHERE dictionary_name = ? AND code = ?",
    ['d_labitems', '50878'],
).fetchall()
```

ICD 编码必须同时使用 `code_version` 区分 ICD-9 与 ICD-10。
源数据受 PhysioNet 使用协议约束，本目录不得公开分发或提交至公共 Git 仓库。
""",
        encoding="utf-8",
    )


def build_dictionaries(
    data_root: Path = DEFAULT_DATA_ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    data_root = data_root.resolve()
    output_dir = output_dir.resolve()
    sources = _validate_sources(data_root)
    staging = _prepare_output(output_dir)
    database_path = staging / "mimic_dictionaries.duckdb"
    connection = duckdb.connect(str(database_path))
    entries: list[dict[str, Any]] = []
    try:
        _create_lookup_table(connection)
        for spec, source_path, header in sources:
            entries.append(
                _load_dictionary(connection, spec, source_path, header, staging / "tables")
            )
        lookup_rows = connection.execute("SELECT count(*) FROM code_lookup").fetchone()[0]
        lookup_parquet = staging / "mimic_code_lookup.parquet"
        connection.execute(
            f"COPY code_lookup TO {_sql_literal(lookup_parquet)} "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        open_formats = _export_open_formats(connection, staging, entries)
        connection.execute("CHECKPOINT")
    finally:
        connection.close()

    manifest: dict[str, Any] = {
        "schema_name": "mimic_code_dictionaries",
        "schema_version": "1.0.0",
        "source_database": SOURCE_DATABASE,
        "source_version": SOURCE_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_root": data_root.as_posix(),
        "excluded": [
            "MIMIC-III 1.4 dictionaries",
            "provider.csv.gz (deidentified identifier registry, not a semantic code dictionary)",
            "caregiver.csv.gz (deidentified identifier registry, not a semantic code dictionary)",
        ],
        "dictionary_count": len(entries),
        "lookup_rows": lookup_rows,
        "dictionaries": entries,
        "lookup": {
            "path": "mimic_code_lookup.parquet",
            "bytes": lookup_parquet.stat().st_size,
            "sha256": _sha256(lookup_parquet),
        },
        "open_formats": open_formats,
        "database": {
            "path": "mimic_dictionaries.duckdb",
            "bytes": database_path.stat().st_size,
            "sha256": _sha256(database_path),
        },
        "total_output_bytes": 0,
    }
    _write_readme(staging / "README.md", manifest)
    manifest_path = staging / "manifest.json"
    for _ in range(3):
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        total_bytes = sum(path.stat().st_size for path in staging.rglob("*") if path.is_file())
        if manifest["total_output_bytes"] == total_bytes:
            break
        manifest["total_output_bytes"] = total_bytes
    else:
        raise RuntimeError("manifest size did not stabilize")
    oversized = [
        path for path in staging.rglob("*")
        if path.is_file() and path.stat().st_size > max_file_bytes
    ]
    if oversized:
        details = ", ".join(
            f"{path.relative_to(staging).as_posix()}={path.stat().st_size}"
            for path in oversized
        )
        shutil.rmtree(staging)
        raise ValueError(
            f"parsed dictionary files exceed per-file limit {max_file_bytes}: {details}"
        )
    staging.replace(output_dir)
    return manifest


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build query-ready MIMIC-IV 3.1 semantic code dictionaries"
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    return parser


def main() -> None:
    args = create_parser().parse_args()
    manifest = build_dictionaries(args.data_root, args.output_dir, args.max_file_bytes)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
