"""Read-only local browser for event-pipeline Parquet outputs."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse
import webbrowser

import duckdb


_DATASETS = {
    "cleaned_events": {
        "filename": "cleaned_events.parquet",
        "title": "通过事件",
        "default_sort": ("jsonl_line_number", "source_array_index", "event_id"),
        "preview_columns": (
            "jsonl_line_number",
            "subject_id",
            "hadm_id",
            "event_kind",
            "source_table",
            "source_label",
            "value_numeric",
            "value_text",
            "unit",
            "event_time",
            "available_time",
            "time_resolution_status",
        ),
        "search_columns": (
            "event_id",
            "source_label",
            "value_text",
            "source_concept_id",
            "raw_row_ref",
        ),
    },
    "cleaning_rejected": {
        "filename": "cleaning_rejected.parquet",
        "title": "拒绝源行",
        "default_sort": ("subject_id", "hadm_id", "source_row_id"),
        "preview_columns": (
            "subject_id",
            "hadm_id",
            "source_table",
            "reason_code",
            "message",
            "raw_row_ref",
        ),
        "search_columns": (
            "source_row_id",
            "reason_code",
            "message",
            "raw_row_ref",
        ),
    },
    "term_inventory": {
        "filename": "term_inventory.parquet",
        "title": "术语清单",
        "default_sort": ("entity_type", "normalized_source_label", "unit"),
        "preview_columns": (
            "entity_type",
            "source_concept_id",
            "normalized_source_label",
            "source_label_example",
            "unit",
            "event_count",
            "first_event_id",
        ),
        "search_columns": (
            "source_concept_id",
            "normalized_source_label",
            "source_label_example",
            "first_event_id",
        ),
    },
    "encounter_manifest": {
        "filename": "encounter_manifest.parquet",
        "title": "住院对账",
        "default_sort": ("jsonl_line_number", "subject_id", "hadm_id"),
        "preview_columns": (
            "jsonl_line_number",
            "subject_id",
            "hadm_id",
            "source_row_count",
            "derived_row_count",
            "event_count",
            "rejected_count",
        ),
        "search_columns": ("subject_id", "hadm_id"),
    },
    "normalized_events": {
        "stage": "normalization",
        "filename": "normalized_events.parquet",
        "title": "归一化事件",
        "default_sort": ("jsonl_line_number", "source_array_index", "event_id"),
        "preview_columns": (
            "jsonl_line_number",
            "subject_id",
            "hadm_id",
            "event_kind",
            "source_table",
            "source_label",
            "concept_id",
            "preferred_name",
            "normalization_status",
            "normalized_unit",
        ),
        "search_columns": (
            "event_id",
            "source_label",
            "source_concept_id",
            "concept_id",
            "preferred_name",
            "raw_row_ref",
        ),
    },
    "normalization_mappings": {
        "stage": "normalization",
        "filename": "normalization_mappings.parquet",
        "title": "归一化映射",
        "default_sort": ("entity_type", "normalized_source_label", "source_unit"),
        "preview_columns": (
            "entity_type",
            "source_concept_id",
            "source_label_example",
            "concept_id",
            "preferred_name",
            "normalization_status",
            "source_unit",
            "normalized_unit",
            "mapping_rule",
            "event_count",
        ),
        "search_columns": (
            "source_concept_id",
            "source_label_example",
            "concept_id",
            "preferred_name",
            "mapping_rule",
        ),
    },
    "normalization_review_queue": {
        "stage": "normalization",
        "filename": "normalization_review_queue.parquet",
        "title": "归一化审核队列",
        "default_sort": ("review_reason", "entity_type", "normalized_source_label"),
        "preview_columns": (
            "review_reason",
            "entity_type",
            "source_concept_id",
            "source_label_example",
            "unit",
            "event_count",
            "first_event_id",
        ),
        "search_columns": (
            "review_reason",
            "source_concept_id",
            "source_label_example",
            "first_event_id",
        ),
    },
}

_FILTER_COLUMNS = (
    "jsonl_line_number",
    "subject_id",
    "hadm_id",
    "event_kind",
    "source_table",
    "entity_type",
    "reason_code",
    "time_resolution_status",
    "content_specificity",
    "normalization_status",
    "unit_normalization_status",
    "mapping_rule",
    "review_reason",
)

_RAW_REF_RE = re.compile(
    r"^(?P<filename>[^#\\/]+)#L(?P<line>\d+)/"
    r"(?P<module>[A-Za-z0-9_]+)\.(?P<table>[A-Za-z0-9_]+)"
    r"\[(?P<index>\d+)\]$"
)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _quoted_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", "''")


class SourceJsonlReader:
    """Resolve a raw-row reference back to one immutable source object."""

    def __init__(self, source_path: Path):
        self.source_path = source_path.resolve()
        if not self.source_path.is_file():
            raise FileNotFoundError(self.source_path)
        self._offsets: list[int] | None = None
        self._offset_lock = threading.Lock()

    def _read_admission(self, line_number: int) -> dict[str, Any]:
        if line_number < 1:
            raise ValueError("JSONL 行号必须大于等于 1")
        self._ensure_offsets()
        assert self._offsets is not None
        if line_number > len(self._offsets):
            raise IndexError(f"源 JSONL 不存在第 {line_number} 行")
        with self.source_path.open("rb") as handle:
            handle.seek(self._offsets[line_number - 1])
            value = json.loads(handle.readline())
        if not isinstance(value, dict):
            raise ValueError(f"JSONL 第 {line_number} 行不是对象")
        return value

    def _ensure_offsets(self) -> None:
        if self._offsets is not None:
            return
        with self._offset_lock:
            if self._offsets is not None:
                return
            offsets: list[int] = []
            with self.source_path.open("rb") as handle:
                while True:
                    offset = handle.tell()
                    line = handle.readline()
                    if not line:
                        break
                    offsets.append(offset)
            self._offsets = offsets

    def resolve(self, raw_row_ref: str) -> dict[str, Any]:
        match = _RAW_REF_RE.fullmatch(raw_row_ref)
        if match is None:
            raise ValueError("raw_row_ref 格式不合法")
        if match.group("filename") != self.source_path.name:
            raise ValueError("raw_row_ref 文件名与当前源 JSONL 不一致")

        line_number = int(match.group("line"))
        index = int(match.group("index"))
        module = match.group("module")
        table = match.group("table")
        admission = self._read_admission(line_number)
        module_value = admission.get(module)
        if not isinstance(module_value, dict):
            raise KeyError(f"源记录不存在模块 {module}")
        rows = module_value.get(table)
        if not isinstance(rows, list):
            raise KeyError(f"源记录不存在数组 {module}.{table}")
        if index >= len(rows):
            raise IndexError(f"数组索引 {index} 超过 {module}.{table} 长度")
        return {
            "raw_row_ref": raw_row_ref,
            "jsonl_line_number": line_number,
            "source_module": module,
            "source_table": table,
            "source_array_index": index,
            "source_row": rows[index],
        }


class CleaningViewerStore:
    """Small query interface over immutable Parquet and manifest files."""

    def __init__(self, cleaning_dir: Path, source_jsonl: Path | None = None):
        requested_directory = cleaning_dir.resolve()
        if not requested_directory.is_dir():
            raise NotADirectoryError(requested_directory)
        if (requested_directory / "cleaning").is_dir():
            self.event_directory = requested_directory
            self.cleaning_dir = requested_directory / "cleaning"
            normalization_dir = requested_directory / "normalization"
        else:
            self.event_directory = requested_directory
            self.cleaning_dir = requested_directory
            normalization_dir = requested_directory / "normalization"
        has_normalization = normalization_dir.is_dir()

        self._connection = duckdb.connect(database=":memory:")
        self._lock = threading.Lock()
        self._columns: dict[str, tuple[str, ...]] = {}
        self._counts: dict[str, int] = {}
        for dataset, config in _DATASETS.items():
            stage = config.get("stage", "cleaning")
            if stage == "normalization" and not has_normalization:
                continue
            base_directory = (
                normalization_dir if stage == "normalization" else self.cleaning_dir
            )
            parquet_path = base_directory / str(config["filename"])
            if not parquet_path.is_file():
                raise FileNotFoundError(parquet_path)
            self._connection.execute(
                f"CREATE VIEW {dataset} AS "
                f"SELECT * FROM read_parquet('{_quoted_path(parquet_path)}')"
            )
            described = self._connection.execute(f"DESCRIBE {dataset}").fetchall()
            self._columns[dataset] = tuple(row[0] for row in described)
            self._counts[dataset] = int(
                self._connection.execute(f"SELECT count(*) FROM {dataset}").fetchone()[0]
            )

        self.run_manifest = self._read_json("run_manifest.json")
        self.reconciliation = self._read_json("source_reconciliation.json")
        resolved_source = source_jsonl.resolve() if source_jsonl else self._find_source_jsonl()
        self.source_reader = SourceJsonlReader(resolved_source) if resolved_source else None

    def close(self) -> None:
        self._connection.close()

    def _read_json(self, filename: str) -> dict[str, Any]:
        path = self.cleaning_dir / filename
        if not path.is_file():
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"{path} 顶层必须是对象")
        return value

    def _find_source_jsonl(self) -> Path | None:
        filename = self.run_manifest.get("input", {}).get("filename")
        if not isinstance(filename, str) or not filename:
            return None
        candidates: list[Path] = []
        for parent in (self.cleaning_dir, *self.cleaning_dir.parents):
            if parent.name.lower() == "data":
                candidates.append(parent / "validation" / filename)
        candidates.append(Path.cwd() / "data" / "validation" / filename)
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return None

    def catalog(self) -> dict[str, Any]:
        datasets = []
        for name in self._columns:
            config = _DATASETS[name]
            columns = self._columns[name]
            datasets.append(
                {
                    "name": name,
                    "title": config["title"],
                    "count": self._counts[name],
                    "columns": columns,
                    "preview_columns": [
                        column for column in config["preview_columns"] if column in columns
                    ],
                    "filters": [column for column in _FILTER_COLUMNS if column in columns],
                }
            )
        return {
            "cleaning_dir": str(self.cleaning_dir),
            "event_directory": str(self.event_directory),
            "read_only": True,
            "source_jsonl": (
                str(self.source_reader.source_path) if self.source_reader else None
            ),
            "datasets": datasets,
            "run_manifest": self.run_manifest,
            "source_reconciliation": self.reconciliation,
        }

    def distinct_values(self, dataset: str, column: str, limit: int = 200) -> list[Any]:
        self._validate_dataset(dataset)
        if column not in _FILTER_COLUMNS or column not in self._columns[dataset]:
            raise ValueError(f"不允许枚举字段 {column}")
        with self._lock:
            rows = self._connection.execute(
                f"SELECT DISTINCT {column} FROM {dataset} "
                f"WHERE {column} IS NOT NULL ORDER BY {column} LIMIT ?",
                [limit],
            ).fetchall()
        return [_json_value(row[0]) for row in rows]

    def query(
        self,
        dataset: str,
        *,
        page: int = 1,
        page_size: int = 50,
        filters: dict[str, str] | None = None,
        search: str = "",
    ) -> dict[str, Any]:
        self._validate_dataset(dataset)
        if page < 1:
            raise ValueError("page 必须大于等于 1")
        if page_size not in {20, 50, 100, 200}:
            raise ValueError("page_size 只允许 20、50、100 或 200")

        clauses: list[str] = []
        parameters: list[Any] = []
        for column, value in (filters or {}).items():
            if not value:
                continue
            if column not in _FILTER_COLUMNS or column not in self._columns[dataset]:
                raise ValueError(f"不允许筛选字段 {column}")
            clauses.append(f"CAST({column} AS VARCHAR) = ?")
            parameters.append(value)

        available_search_columns = [
            column
            for column in _DATASETS[dataset]["search_columns"]
            if column in self._columns[dataset]
        ]
        if search and available_search_columns:
            clauses.append(
                "(" + " OR ".join(
                    f"lower(COALESCE(CAST({column} AS VARCHAR), '')) LIKE ?"
                    for column in available_search_columns
                ) + ")"
            )
            parameters.extend([f"%{search.lower()}%"] * len(available_search_columns))

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sort_columns = [
            column
            for column in _DATASETS[dataset]["default_sort"]
            if column in self._columns[dataset]
        ]
        order = f" ORDER BY {', '.join(sort_columns)}" if sort_columns else ""
        offset = (page - 1) * page_size
        with self._lock:
            total = int(
                self._connection.execute(
                    f"SELECT count(*) FROM {dataset}{where}", parameters
                ).fetchone()[0]
            )
            cursor = self._connection.execute(
                f"SELECT * FROM {dataset}{where}{order} LIMIT ? OFFSET ?",
                [*parameters, page_size, offset],
            )
            names = [item[0] for item in cursor.description]
            rows = [
                {name: _json_value(value) for name, value in zip(names, row, strict=True)}
                for row in cursor.fetchall()
            ]
        return {
            "dataset": dataset,
            "page": page,
            "page_size": page_size,
            "total": total,
            "rows": rows,
        }

    def source_row(self, raw_row_ref: str) -> dict[str, Any]:
        if self.source_reader is None:
            raise FileNotFoundError(
                "未找到源 JSONL；启动时请使用 --source-jsonl 明确指定文件"
            )
        return self.source_reader.resolve(raw_row_ref)

    def _validate_dataset(self, dataset: str) -> None:
        if dataset not in self._columns:
            raise ValueError(f"未知数据集 {dataset}")


def _make_handler(store: CleaningViewerStore) -> type[BaseHTTPRequestHandler]:
    html_path = Path(__file__).with_name("viewer.html")
    html = html_path.read_bytes()

    class ViewerHandler(BaseHTTPRequestHandler):
        server_version = "EventPipelineViewer/1.0"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    self._send_bytes(html, "text/html; charset=utf-8")
                    return
                if parsed.path == "/api/catalog":
                    self._send_json(store.catalog())
                    return
                query = parse_qs(parsed.query, keep_blank_values=False)
                if parsed.path == "/api/distinct":
                    self._send_json(
                        {
                            "values": store.distinct_values(
                                self._one(query, "dataset"),
                                self._one(query, "column"),
                            )
                        }
                    )
                    return
                if parsed.path == "/api/rows":
                    dataset = self._one(query, "dataset")
                    filters = {
                        key: values[0]
                        for key, values in query.items()
                        if key in _FILTER_COLUMNS and values
                    }
                    self._send_json(
                        store.query(
                            dataset,
                            page=int(query.get("page", ["1"])[0]),
                            page_size=int(query.get("page_size", ["50"])[0]),
                            filters=filters,
                            search=query.get("q", [""])[0],
                        )
                    )
                    return
                if parsed.path == "/api/source":
                    self._send_json(store.source_row(self._one(query, "raw_row_ref")))
                    return
                self._send_error(HTTPStatus.NOT_FOUND, "接口不存在")
            except (ValueError, KeyError, IndexError) as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            except FileNotFoundError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, str(exc))
            except Exception as exc:  # pragma: no cover - final HTTP boundary
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def do_POST(self) -> None:  # noqa: N802
            self._send_error(HTTPStatus.METHOD_NOT_ALLOWED, "只读服务不接受写请求")

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _one(self, query: dict[str, list[str]], key: str) -> str:
            values = query.get(key)
            if not values or not values[0]:
                raise ValueError(f"缺少参数 {key}")
            return values[0]

        def _send_json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8", status)

        def _send_error(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"error": message}, status)

        def _send_bytes(
            self,
            body: bytes,
            content_type: str,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; connect-src 'self'",
            )
            self.end_headers()
            self.wfile.write(body)

    return ViewerHandler


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="在本机浏览器中只读查看事件流水线 Parquet 输出。"
    )
    parser.add_argument("cleaning_dir", type=Path)
    parser.add_argument("--source-jsonl", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--check", action="store_true", help="只验证文件并打印目录摘要，不启动服务"
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        raise ValueError("端口必须在 1 到 65535 之间")
    store = CleaningViewerStore(args.cleaning_dir, args.source_jsonl)
    if args.check:
        print(json.dumps(store.catalog(), ensure_ascii=False, indent=2))
        store.close()
        return

    address = ("127.0.0.1", args.port)
    server = ThreadingHTTPServer(address, _make_handler(store))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"只读事件浏览器已启动：{url}")
    print("按 Ctrl+C 停止。服务仅监听本机 127.0.0.1。")
    if not args.no_browser:
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        store.close()


if __name__ == "__main__":
    main()
