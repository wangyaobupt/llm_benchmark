"""Single-file local browser and append-only decision recorder for review packages."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse
import webbrowser

import duckdb


APP_VERSION = "normalization-review-ui/1.1.0"
ANNOTATION_FILENAME = "normalization_review_annotations.jsonl"
LEGACY_DECISIONS = ["accepted", "rejected", "corrected", "needs_evidence"]
RAW_REF_RE = re.compile(
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
    def __init__(self, source_path: Path):
        self.source_path = source_path.resolve()
        if not self.source_path.is_file():
            raise FileNotFoundError(self.source_path)
        self._offsets: list[int] | None = None
        self._lock = threading.Lock()

    def _ensure_offsets(self) -> None:
        if self._offsets is not None:
            return
        with self._lock:
            if self._offsets is not None:
                return
            offsets: list[int] = []
            with self.source_path.open("rb") as handle:
                while True:
                    offset = handle.tell()
                    if not handle.readline():
                        break
                    offsets.append(offset)
            self._offsets = offsets

    def resolve(self, raw_row_ref: str) -> dict[str, Any]:
        match = RAW_REF_RE.fullmatch(raw_row_ref)
        if match is None:
            raise ValueError("raw_row_ref 格式不合法")
        if match.group("filename") != self.source_path.name:
            raise ValueError("raw_row_ref 文件名与当前源 JSONL 不一致")
        self._ensure_offsets()
        assert self._offsets is not None
        line_number = int(match.group("line"))
        if line_number < 1 or line_number > len(self._offsets):
            raise IndexError(f"源 JSONL 不存在第 {line_number} 行")
        with self.source_path.open("rb") as handle:
            handle.seek(self._offsets[line_number - 1])
            admission = json.loads(handle.readline())
        module = match.group("module")
        table = match.group("table")
        index = int(match.group("index"))
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


class ReviewStore:
    """Read immutable review metadata and append human decisions to a sidecar."""

    def __init__(self, review_directory: Path, source_jsonl: Path | None = None):
        self.review_directory = Path(review_directory).resolve()
        if not self.review_directory.is_dir():
            raise NotADirectoryError(self.review_directory)
        self.summary_path = self._first_existing(
            "normalization_review_summary.json", "review_summary.json"
        )
        self.decisions_path = self._first_existing(
            "normalization_review_decisions.parquet",
            "consolidated_review_decisions.parquet",
        )
        self.samples_path = self._first_existing(
            "normalization_review_samples.parquet",
            "cross_batch_evidence_samples.parquet",
        )
        for path in (self.summary_path, self.decisions_path, self.samples_path):
            if not path.is_file():
                raise FileNotFoundError(path)
        self.summary_data = json.loads(self.summary_path.read_text(encoding="utf-8"))
        self.annotation_path = self.review_directory / ANNOTATION_FILENAME
        self._lock = threading.RLock()
        self._connection = duckdb.connect(database=":memory:")
        self._connection.execute(
            "CREATE VIEW review_decisions AS SELECT * FROM read_parquet('"
            + _quoted_path(self.decisions_path)
            + "')"
        )
        self.decision_columns = {
            row[0]
            for row in self._connection.execute("DESCRIBE review_decisions").fetchall()
        }
        self._connection.execute(
            "CREATE VIEW review_samples AS SELECT * FROM read_parquet('"
            + _quoted_path(self.samples_path)
            + "')"
        )
        self.sample_columns = {
            row[0]
            for row in self._connection.execute("DESCRIBE review_samples").fetchall()
        }
        self._latest_annotations: dict[str, dict[str, Any]] = {}
        self._annotation_history: dict[str, list[dict[str, Any]]] = {}
        self._load_annotations()
        self.source_readers: dict[str, SourceJsonlReader] = {}
        batches = self.summary_data.get("inputs", {}).get("batches", [])
        if isinstance(batches, list) and batches:
            if source_jsonl:
                raise ValueError("多批审阅不能使用单个 --source-jsonl 覆盖源文件")
            for batch in batches:
                batch_id = batch.get("batch_id")
                source_path = batch.get("source_jsonl")
                if isinstance(batch_id, str) and isinstance(source_path, str):
                    self.source_readers[batch_id] = SourceJsonlReader(Path(source_path))
        else:
            resolved_source = (
                Path(source_jsonl).resolve()
                if source_jsonl
                else self._find_source_jsonl()
            )
            if resolved_source:
                self.source_readers["default"] = SourceJsonlReader(resolved_source)

    def _first_existing(self, *names: str) -> Path:
        for name in names:
            path = self.review_directory / name
            if path.is_file():
                return path
        return self.review_directory / names[0]

    def close(self) -> None:
        self._connection.close()

    def _find_source_jsonl(self) -> Path | None:
        event_directory = self.review_directory.parent
        manifest_path = event_directory / "cleaning" / "run_manifest.json"
        if not manifest_path.is_file():
            return None
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        filename = manifest.get("input", {}).get("filename")
        if not isinstance(filename, str) or not filename:
            return None
        candidates = (
            event_directory.parent / filename,
            event_directory / filename,
            Path.cwd() / filename,
            Path.cwd() / "data" / "validation" / filename,
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return None

    def _load_annotations(self) -> None:
        latest: dict[str, dict[str, Any]] = {}
        history: dict[str, list[dict[str, Any]]] = {}
        if self.annotation_path.is_file():
            with self.annotation_path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ValueError(
                            f"{self.annotation_path} 第 {line_number} 行不是合法 JSON"
                        ) from exc
                    review_id = value.get("review_id")
                    if not isinstance(review_id, str) or not review_id:
                        raise ValueError(
                            f"{self.annotation_path} 第 {line_number} 行缺少 review_id"
                        )
                    history.setdefault(review_id, []).append(value)
                    latest[review_id] = value
        self._latest_annotations = latest
        self._annotation_history = history

    def summary(self) -> dict[str, Any]:
        with self._lock:
            counts = Counter(
                value["decision"] for value in self._latest_annotations.values()
            )
            summary_counts = self.summary_data.get("counts", {})
            selected = int(
                summary_counts.get(
                    "pilot_review_rows",
                    int(summary_counts.get("required_review_rows", 0))
                    + int(summary_counts.get("sampled_review_rows", 0)),
                )
            )
            completed_decisions = set(
                self.summary_data.get("decision_taxonomy", {}).get(
                    "completed", ["accepted", "rejected", "corrected"]
                )
            )
            completed = sum(
                count
                for decision, count in counts.items()
                if decision in completed_decisions
            )
            return {
                **self.summary_data,
                "review_ui": {
                    "version": APP_VERSION,
                    "source_jsonl": (
                        str(next(iter(self.source_readers.values())).source_path)
                        if len(self.source_readers) == 1
                        else None
                    ),
                    "source_batches": {
                        batch: str(reader.source_path)
                        for batch, reader in sorted(self.source_readers.items())
                    },
                    "annotation_file": ANNOTATION_FILENAME,
                    "annotation_count": sum(counts.values()),
                    "latest_decision_counts": dict(sorted(counts.items())),
                    "selected_for_human_review": selected,
                    "completed_human_decisions": completed,
                    "remaining_human_decisions": max(selected - completed, 0),
                },
            }

    def query_decisions(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        priority_rank: str = "",
        review_scope: str = "",
        entity_type: str = "",
        review_reason: str = "",
        mapping_rule: str = "",
        pilot_category: str = "",
        current_status: str = "",
        sort: str = "priority",
    ) -> dict[str, Any]:
        if page < 1 or page_size not in {20, 50, 100, 200}:
            raise ValueError("page/page_size 不合法")
        pilot_first = (
            "CASE WHEN d.review_scope = 'pilot' THEN 0 ELSE 1 END, "
            "d.pilot_category_rank NULLS LAST, "
            if "pilot_category_rank" in self.decision_columns
            else ""
        )
        sort_sql = {
            "priority": pilot_first + "d.priority_rank, d.event_count DESC, d.review_id",
            "impact": "d.event_count DESC, d.priority_rank, d.review_id",
            "label": "d.entity_type, d.normalized_source_label, d.review_id",
            "status": "current_status, d.priority_rank, d.event_count DESC",
        }.get(sort)
        if sort_sql is None:
            raise ValueError("sort 不合法")
        clauses: list[str] = []
        parameters: list[Any] = []
        if priority_rank:
            clauses.append("d.priority_rank = ?")
            parameters.append(int(priority_rank))
        for column, value in (
            ("review_scope", review_scope),
            ("entity_type", entity_type),
            ("mapping_rule", mapping_rule),
            ("pilot_category", pilot_category),
        ):
            if value and column in self.decision_columns:
                clauses.append(f"d.{column} = ?")
                parameters.append(value)
        if review_reason:
            clauses.append("list_contains(d.review_reasons, ?)")
            parameters.append(review_reason)
        if current_status:
            clauses.append(
                "COALESCE(a.decision, d.review_status) = ?"
            )
            parameters.append(current_status)
        if search:
            searchable = [
                column
                for column in (
                    "source_concept_id",
                    "source_label_example",
                    "concept_id",
                    "preferred_name",
                    "mapping_rule",
                    "first_event_id",
                    "pilot_category",
                )
                if column in self.decision_columns
            ]
            clauses.append(
                "(" + " OR ".join(
                    f"lower(COALESCE(CAST(d.{column} AS VARCHAR), '')) LIKE ?"
                    for column in searchable
                ) + ")"
            )
            parameters.extend([f"%{search.casefold()}%"] * len(searchable))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        annotations = list(self._latest_annotations.values())
        with self._lock:
            self._replace_annotations_table(annotations)
            base = (
                " FROM review_decisions d LEFT JOIN latest_annotations a "
                "ON d.review_id = a.review_id"
            )
            total = self._connection.execute(
                "SELECT count(*)" + base + where, parameters
            ).fetchone()[0]
            cursor = self._connection.execute(
                "SELECT d.*, COALESCE(a.decision, d.review_status) AS current_status, "
                "a.decision AS latest_decision, a.reviewer AS latest_reviewer, "
                "a.review_comment AS latest_comment, a.timestamp_utc AS latest_timestamp"
                + base
                + where
                + f" ORDER BY {sort_sql} LIMIT ? OFFSET ?",
                [*parameters, page_size, (page - 1) * page_size],
            )
            names = [item[0] for item in cursor.description]
            rows = [
                {name: _json_value(value) for name, value in zip(names, row, strict=True)}
                for row in cursor.fetchall()
            ]
        return {
            "page": page,
            "page_size": page_size,
            "total": int(total),
            "rows": rows,
        }

    def _replace_annotations_table(self, annotations: list[dict[str, Any]]) -> None:
        self._connection.execute("DROP TABLE IF EXISTS latest_annotations")
        self._connection.execute(
            "CREATE TEMP TABLE latest_annotations ("
            "review_id VARCHAR, decision VARCHAR, reviewer VARCHAR, "
            "review_comment VARCHAR, timestamp_utc VARCHAR)"
        )
        if annotations:
            self._connection.executemany(
                "INSERT INTO latest_annotations VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        row["review_id"],
                        row.get("decision"),
                        row.get("reviewer"),
                        row.get("review_comment"),
                        row.get("timestamp_utc"),
                    )
                    for row in annotations
                ],
            )

    def distinct_values(self) -> dict[str, list[Any]]:
        output: dict[str, list[Any]] = {}
        with self._lock:
            for column in (
                "entity_type",
                "mapping_rule",
                "review_scope",
                "pilot_category",
                "priority_rank",
            ):
                if column not in self.decision_columns:
                    output[column] = []
                    continue
                output[column] = [
                    row[0]
                    for row in self._connection.execute(
                        f"SELECT DISTINCT {column} FROM review_decisions "
                        f"WHERE {column} IS NOT NULL ORDER BY {column}"
                    ).fetchall()
                ]
            output["review_reason"] = [
                row[0]
                for row in self._connection.execute(
                    "SELECT DISTINCT unnest(review_reasons) AS reason "
                    "FROM review_decisions ORDER BY reason"
                ).fetchall()
            ]
        allowed = self.summary_data.get("decision_taxonomy", {}).get(
            "allowed", LEGACY_DECISIONS
        )
        output["current_status"] = ["pending", *allowed, "not_selected"]
        return output

    def detail(self, review_id: str) -> dict[str, Any]:
        with self._lock:
            cursor = self._connection.execute(
                "SELECT * FROM review_decisions WHERE review_id = ?", [review_id]
            )
            row = cursor.fetchone()
            if row is None:
                raise KeyError("review_id 不存在")
            names = [item[0] for item in cursor.description]
            decision = {
                name: _json_value(value) for name, value in zip(names, row, strict=True)
            }
            sample_order = (
                "batch_id, event_id"
                if "batch_id" in self.sample_columns
                else "event_id"
            )
            sample_cursor = self._connection.execute(
                "SELECT * FROM review_samples WHERE mapping_review_id = ? "
                f"ORDER BY {sample_order} LIMIT 50",
                [review_id],
            )
            sample_names = [item[0] for item in sample_cursor.description]
            samples = [
                {
                    name: _json_value(value)
                    for name, value in zip(sample_names, sample, strict=True)
                }
                for sample in sample_cursor.fetchall()
            ]
            history = list(self._annotation_history.get(review_id, []))
        return {
            "decision": decision,
            "samples": samples,
            "latest_annotation": self._latest_annotations.get(review_id),
            "annotation_history": history,
        }

    def source_row(
        self, raw_row_ref: str, batch_id: str | None = None
    ) -> dict[str, Any]:
        if not self.source_readers:
            raise FileNotFoundError(
                "未自动找到源 JSONL；请使用 --source-jsonl 明确指定"
            )
        if batch_id:
            reader = self.source_readers.get(batch_id)
            if reader is None:
                raise KeyError(f"未知批次 {batch_id}")
        elif len(self.source_readers) == 1:
            reader = next(iter(self.source_readers.values()))
        else:
            raise ValueError("多批审阅回查必须提供 batch_id")
        return {"batch_id": batch_id or "default", **reader.resolve(raw_row_ref)}

    def save_annotation(self, payload: dict[str, Any]) -> dict[str, Any]:
        review_id = str(payload.get("review_id") or "").strip()
        decision = str(payload.get("decision") or "").strip()
        reviewer = str(payload.get("reviewer") or "").strip()
        comment = str(payload.get("review_comment") or "").strip()
        corrected_concept_id = str(
            payload.get("corrected_concept_id") or ""
        ).strip() or None
        corrected_preferred_name = str(
            payload.get("corrected_preferred_name") or ""
        ).strip() or None
        corrected_normalized_unit = str(
            payload.get("corrected_normalized_unit") or ""
        ).strip() or None
        taxonomy = self.summary_data.get("decision_taxonomy", {})
        allowed_decisions = set(taxonomy.get("allowed", LEGACY_DECISIONS))
        comment_required = set(
            taxonomy.get(
                "comment_required", ["rejected", "corrected", "needs_evidence"]
            )
        )
        correction_required = set(
            taxonomy.get("correction_fields_required", ["corrected"])
        )
        correction_concept_or_unit = set(
            taxonomy.get("correction_concept_or_unit_required", [])
        )
        if decision not in allowed_decisions:
            raise ValueError("decision 不合法")
        if not reviewer:
            raise ValueError("reviewer 不能为空")
        if decision in comment_required and not comment:
            raise ValueError("该决定必须填写 review_comment")
        if decision in correction_required and (
            not corrected_concept_id or not corrected_preferred_name
        ):
            raise ValueError("该纠正决定必须填写纠正后的概念ID和名称")
        if decision in correction_concept_or_unit and not (
            (corrected_concept_id and corrected_preferred_name)
            or corrected_normalized_unit
        ):
            raise ValueError("确定性纠正必须填写概念ID和名称，或填写标准单位")
        with self._lock:
            current = self._connection.execute(
                "SELECT normalization_status, unit_normalization_status "
                "FROM review_decisions WHERE review_id = ?",
                [review_id],
            ).fetchone()
            if current is None:
                raise KeyError("review_id 不存在")
            normalization_status, unit_status = current
            if decision == "accepted_mapped" and (
                normalization_status != "mapped" or unit_status == "unresolved"
            ):
                raise ValueError("当前术语或单位未解决，不能标记 accepted_mapped")
            if decision == "accepted_unresolved" and not (
                normalization_status == "unresolved" or unit_status == "unresolved"
            ):
                raise ValueError("当前术语和单位均已映射，不能标记 accepted_unresolved")
            timestamp = datetime.now(timezone.utc).isoformat()
            annotation = {
                "schema": {
                    "name": "normalization_review_annotation",
                    "version": "1.1.0",
                },
                "annotation_id": "annotation-"
                + hashlib.sha256(
                    f"{review_id}|{timestamp}|{os.getpid()}".encode("utf-8")
                ).hexdigest()[:24],
                "review_run_id": self.summary_data.get("review_run_id"),
                "review_id": review_id,
                "decision": decision,
                "corrected_concept_id": corrected_concept_id,
                "corrected_preferred_name": corrected_preferred_name,
                "corrected_normalized_unit": corrected_normalized_unit,
                "reviewer": reviewer,
                "review_comment": comment or None,
                "timestamp_utc": timestamp,
            }
            serialized = json.dumps(annotation, ensure_ascii=False, sort_keys=True)
            with self.annotation_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._annotation_history.setdefault(review_id, []).append(annotation)
            self._latest_annotations[review_id] = annotation
        return annotation


HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>归一化人工审阅</title><style>
:root{--bg:#f3f6fb;--panel:#fff;--ink:#162033;--muted:#68758a;--line:#dce3ee;--blue:#315efb;--green:#16855b;--red:#c33b45;--amber:#b36b00;--shadow:0 10px 30px rgba(33,47,77,.08)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}button,input,select,textarea{font:inherit}button{cursor:pointer}.top{padding:22px 28px;background:#10182a;color:#fff}.top h1{margin:0 0 5px;font-size:24px}.top p{margin:0;color:#b8c4db}.cards{display:grid;grid-template-columns:repeat(6,minmax(130px,1fr));gap:12px;padding:18px 22px}.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:13px 15px;box-shadow:var(--shadow)}.card b{display:block;font-size:22px}.card span{color:var(--muted)}.layout{display:grid;grid-template-columns:minmax(480px,42%) 1fr;gap:16px;padding:0 22px 24px;height:calc(100vh - 190px)}.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);overflow:hidden}.filters{display:grid;grid-template-columns:2fr repeat(2,1fr);gap:8px;padding:12px;border-bottom:1px solid var(--line)}input,select,textarea{width:100%;border:1px solid var(--line);border-radius:8px;padding:8px;background:#fff;color:var(--ink)}.list{height:calc(100% - 112px);overflow:auto}.row{padding:11px 13px;border-bottom:1px solid #edf1f6;cursor:pointer}.row:hover,.row.active{background:#eef3ff}.row-head{display:flex;justify-content:space-between;gap:10px}.label{font-weight:650}.meta{color:var(--muted);font-size:12px}.badges{display:flex;flex-wrap:wrap;gap:5px;margin-top:6px}.badge{padding:2px 7px;border-radius:999px;background:#edf1f7;font-size:11px}.p0{background:#fde8ea;color:var(--red)}.p1{background:#fff1d6;color:var(--amber)}.mapped{background:#def4ea;color:var(--green)}.unresolved{background:#fff1d6;color:var(--amber)}.pager{display:flex;justify-content:space-between;align-items:center;padding:10px 12px;border-top:1px solid var(--line)}.pager button,.primary{border:0;border-radius:8px;padding:8px 12px;background:var(--blue);color:#fff}.pager button:disabled{opacity:.35}.detail{height:100%;overflow:auto;padding:18px}.empty{display:grid;place-items:center;height:100%;color:var(--muted)}h2,h3{margin:0 0 12px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 18px}.field{padding:7px 0;border-bottom:1px solid #edf1f6}.field span{display:block;color:var(--muted);font-size:12px}.field code{word-break:break-all}.sample{border:1px solid var(--line);border-radius:10px;padding:10px;margin:8px 0;background:#fafcff}.raw{white-space:pre-wrap;word-break:break-word;background:#10182a;color:#dbe5fa;border-radius:8px;padding:12px;max-height:320px;overflow:auto}.form{margin-top:16px;padding:14px;background:#f7f9fd;border:1px solid var(--line);border-radius:12px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.form textarea{grid-column:1/-1;min-height:75px}.notice{padding:8px 10px;border-radius:8px;margin:8px 0}.ok{background:#def4ea;color:var(--green)}.error{background:#fde8ea;color:var(--red)}@media(max-width:1100px){.cards{grid-template-columns:repeat(3,1fr)}.layout{grid-template-columns:1fr;height:auto}.panel{min-height:650px}}
</style></head><body>
<header class="top"><h1>归一化人工审阅</h1><p id="runline">加载审阅元数据…</p></header><section class="cards" id="cards"></section>
<main class="layout"><section class="panel"><div class="filters">
<input id="search" placeholder="搜索术语、代码、概念或event_id">
<select id="priority"><option value="">全部优先级</option></select>
<select id="status"><option value="">全部状态</option></select>
<select id="scope"><option value="">全部审阅范围</option></select><select id="pilot"><option value="">全部试审类别</option></select><select id="reason"><option value="">全部原因</option></select><select id="entity"><option value="">全部实体</option></select><select id="sort"><option value="priority">按优先级</option><option value="impact">按影响事件数</option><option value="label">按术语</option><option value="status">按状态</option></select>
</div><div class="list" id="list"></div><div class="pager"><button id="prev">上一页</button><span id="pageinfo"></span><button id="next">下一页</button></div></section>
<section class="panel"><div class="detail" id="detail"><div class="empty">从左侧选择一个审阅项目</div></div></section></main>
<script>
const state={page:1,pageSize:50,total:0,active:null,summary:null};const $=id=>document.getElementById(id);const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url,opt){const r=await fetch(url,opt);const j=await r.json();if(!r.ok)throw new Error(j.error||r.statusText);return j}
function card(label,value){return `<div class="card"><b>${esc(value)}</b><span>${esc(label)}</span></div>`}
async function loadSummary(){const s=await api('/api/summary');state.summary=s;const u=s.review_ui,c=s.counts,n=s.normalization_status_counts||{};const gate=s.acceptance.automated_review_passed??s.acceptance.ready_for_human_review;const connected=Object.keys(u.source_batches||{}).length;$('runline').textContent=`review run ${s.review_run_id} · 自动门禁 ${gate?'通过':'失败'} · 已连接 ${connected} 批原始JSONL`;$('cards').innerHTML=card('归一化事件',Number(c.normalized_events||0).toLocaleString())+card('唯一术语',Number(c.unique_mapping_rows??c.mapping_rows??0).toLocaleString())+card('Unresolved事件',Number(n.unresolved||0).toLocaleString())+card('选中待审',u.selected_for_human_review.toLocaleString())+card('已完成',u.completed_human_decisions.toLocaleString())+card('剩余',u.remaining_human_decisions.toLocaleString())}
async function loadFilters(){const f=await api('/api/filters');for(const [id,key] of [['status','current_status'],['scope','review_scope'],['pilot','pilot_category'],['reason','review_reason'],['entity','entity_type'],['priority','priority_rank']])for(const v of f[key]||[])$(id).insertAdjacentHTML('beforeend',`<option value="${esc(v)}">${id==='priority'?'P':''}${esc(v)}</option>`);if((f.review_scope||[]).includes('pilot'))$('scope').value='pilot'}
function params(){const p=new URLSearchParams({page:state.page,page_size:state.pageSize,search:$('search').value,priority_rank:$('priority').value,current_status:$('status').value,review_scope:$('scope').value,pilot_category:$('pilot').value,review_reason:$('reason').value,entity_type:$('entity').value,sort:$('sort').value});return p}
async function loadList(){const d=await api('/api/decisions?'+params());state.total=d.total;$('list').innerHTML=d.rows.map(r=>`<div class="row ${state.active===r.review_id?'active':''}" data-id="${esc(r.review_id)}"><div class="row-head"><span class="label">${esc(r.source_label_example||r.normalized_source_label||'<missing>')}</span><b>${Number(r.event_count).toLocaleString()}</b></div><div class="meta">${esc(r.entity_type)} · ${esc(r.source_concept_id||'无源代码')} → ${esc(r.concept_id||'unresolved')}</div><div class="badges"><span class="badge p${r.priority_rank}">P${r.priority_rank}</span><span class="badge ${r.normalization_status}">${esc(r.normalization_status)}</span><span class="badge">${esc(r.current_status)}</span>${(r.review_reasons||[]).map(x=>`<span class="badge">${esc(x)}</span>`).join('')}</div></div>`).join('')||'<div class="empty">没有符合条件的项目</div>';$('pageinfo').textContent=`第 ${d.page} 页 · 共 ${d.total.toLocaleString()} 项`;$('prev').disabled=state.page<=1;$('next').disabled=state.page*state.pageSize>=d.total;document.querySelectorAll('.row').forEach(x=>x.onclick=()=>loadDetail(x.dataset.id))}
function fields(d){const items=[['原始术语',d.source_label_example],['源概念代码',d.source_concept_id],['当前概念',d.concept_id],['标准名称',d.preferred_name],['实体类型',d.entity_type],['映射规则',d.mapping_rule],['状态',d.normalization_status],['原始单位',d.source_unit],['标准单位',d.normalized_unit],['单位状态',d.unit_normalization_status],['影响事件数',Number(d.event_count).toLocaleString()],['覆盖批次',d.batch_ids?.join(', ')],['分批事件数',d.batch_event_counts_json],['试审类别',d.pilot_category],['首个事件',d.first_event_id]];return items.map(([k,v])=>`<div class="field"><span>${k}</span><code>${esc(v??'—')}</code></div>`).join('')}
async function loadDetail(id){state.active=id;await loadList();const x=await api('/api/decision?review_id='+encodeURIComponent(id)),d=x.decision,a=x.latest_annotation||{};let samples=x.samples.map(s=>`<div class="sample"><b>${esc(s.batch_id||'单批')} · ${esc(s.event_kind)} · ${esc(s.source_table)}</b><div>${esc(s.source_label)} → ${esc(s.concept_id||'unresolved')}</div><div class="meta">${esc(s.subject_id)} / ${esc(s.hadm_id)} · ${esc(s.raw_row_ref)}</div><button class="primary rawbtn" data-ref="${esc(s.raw_row_ref)}" data-batch="${esc(s.batch_id||'')}">回查原始行</button></div>`).join('')||'<p class="meta">本条没有事件样本。</p>';const decisions=(state.summary.decision_taxonomy?.allowed||['accepted','rejected','corrected','needs_evidence']).map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');$('detail').innerHTML=`<h2>${esc(d.source_label_example||d.normalized_source_label)}</h2><div class="badges">${(d.review_reasons||[]).map(v=>`<span class="badge">${esc(v)}</span>`).join('')}</div><div class="grid">${fields(d)}</div><h3 style="margin-top:18px">事件样本</h3>${samples}<div id="rawbox"></div><div class="form"><h3>记录人工决定</h3><div id="notice"></div><div class="form-grid"><select id="decision"><option value="">选择决定</option>${decisions}</select><input id="reviewer" placeholder="审阅者" value="${esc(a.reviewer||'')}"><input id="correctedId" placeholder="纠正后的concept_id" value="${esc(a.corrected_concept_id||'')}"><input id="correctedName" placeholder="纠正后的preferred_name" value="${esc(a.corrected_preferred_name||'')}"><input id="correctedUnit" placeholder="纠正后的normalized_unit" value="${esc(a.corrected_normalized_unit||'')}"><textarea id="comment" placeholder="审阅依据或备注">${esc(a.review_comment||'')}</textarea></div><button class="primary" id="save" style="margin-top:10px">保存决定</button><div class="meta" style="margin-top:8px">只追加写入 normalization_review_annotations.jsonl，不修改Parquet。历史记录：${x.annotation_history.length} 条。</div></div>`;if(a.decision)$('decision').value=a.decision;document.querySelectorAll('.rawbtn').forEach(b=>b.onclick=()=>loadRaw(b.dataset.ref,b.dataset.batch));$('save').onclick=()=>saveDecision(id)}
async function loadRaw(ref,batch){const box=$('rawbox');try{const p=new URLSearchParams({raw_row_ref:ref,batch_id:batch||''});const x=await api('/api/source?'+p);box.innerHTML=`<h3>原始源行</h3><pre class="raw">${esc(JSON.stringify(x,null,2))}</pre>`}catch(e){box.innerHTML=`<div class="notice error">${esc(e.message)}</div>`}}
async function saveDecision(id){const payload={review_id:id,decision:$('decision').value,reviewer:$('reviewer').value,corrected_concept_id:$('correctedId').value,corrected_preferred_name:$('correctedName').value,corrected_normalized_unit:$('correctedUnit').value,review_comment:$('comment').value};try{await api('/api/annotations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});$('notice').innerHTML='<div class="notice ok">已保存到追加式审阅日志</div>';await loadSummary();await loadDetail(id)}catch(e){$('notice').innerHTML=`<div class="notice error">${esc(e.message)}</div>`}}
let timer;for(const id of ['priority','status','scope','pilot','reason','entity','sort'])$(id).onchange=()=>{state.page=1;loadList()};$('search').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>{state.page=1;loadList()},250)};$('prev').onclick=()=>{state.page--;loadList()};$('next').onclick=()=>{state.page++;loadList()};(async()=>{try{await loadSummary();await loadFilters();await loadList()}catch(e){document.body.innerHTML=`<pre class="raw">${esc(e.stack||e.message)}</pre>`}})();
</script></body></html>'''


def _make_handler(store: ReviewStore) -> type[BaseHTTPRequestHandler]:
    html = HTML.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        server_version = "NormalizationReviewUI/1.0"

        def _headers(self, status: HTTPStatus, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()

        def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8")
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            one = lambda key, default="": query.get(key, [default])[0]
            try:
                if parsed.path == "/":
                    self._headers(HTTPStatus.OK, "text/html; charset=utf-8")
                    self.wfile.write(html)
                elif parsed.path == "/api/summary":
                    self._json(store.summary())
                elif parsed.path == "/api/filters":
                    self._json(store.distinct_values())
                elif parsed.path == "/api/decisions":
                    self._json(
                        store.query_decisions(
                            page=int(one("page", "1")),
                            page_size=int(one("page_size", "50")),
                            search=one("search"),
                            priority_rank=one("priority_rank"),
                            review_scope=one("review_scope"),
                            entity_type=one("entity_type"),
                            review_reason=one("review_reason"),
                            mapping_rule=one("mapping_rule"),
                            pilot_category=one("pilot_category"),
                            current_status=one("current_status"),
                            sort=one("sort", "priority"),
                        )
                    )
                elif parsed.path == "/api/decision":
                    self._json(store.detail(one("review_id")))
                elif parsed.path == "/api/source":
                    self._json(
                        store.source_row(
                            one("raw_row_ref"), one("batch_id") or None
                        )
                    )
                else:
                    self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            except (ValueError, KeyError, FileNotFoundError, IndexError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/annotations":
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 1024 * 1024:
                    raise ValueError("请求体大小不合法")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("请求体必须是JSON对象")
                self._json(store.save_annotation(payload), HTTPStatus.CREATED)
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "review_directory",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    parser.add_argument("--source-jsonl", type=Path)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    store = ReviewStore(args.review_directory, args.source_jsonl)
    if args.check:
        summary = store.summary()
        print(
            json.dumps(
                {
                    "review_directory": str(store.review_directory),
                    "app_version": APP_VERSION,
                    "review_run_id": summary.get("review_run_id"),
                    "decisions": summary.get("counts", {}).get("mapping_rows"),
                    "samples": summary.get("counts", {}).get("event_samples"),
                    "source_jsonl": summary["review_ui"]["source_jsonl"],
                    "source_batches": summary["review_ui"]["source_batches"],
                    "annotations": summary["review_ui"]["annotation_count"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        store.close()
        return 0
    if not 1 <= args.port <= 65535:
        raise ValueError("port 必须在 1 到 65535 之间")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), _make_handler(store))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"归一化审阅窗口：{url}")
    print("按 Ctrl+C 停止。人工决定只写入 normalization_review_annotations.jsonl。")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
