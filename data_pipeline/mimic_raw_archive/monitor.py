"""Local read-only dashboard for a raw archive extraction run."""

from __future__ import annotations

import argparse
import ctypes
import json
import shutil
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .catalog import ARCHIVE_SOURCES, REFERENCE_SOURCE_KEYS
from .config import RawArchiveConfig


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MIMIC 原始归档监控</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--card:#151c30;--line:#293553;--text:#edf2ff;--muted:#91a0bf;--ok:#50d890;--run:#69a7ff;--bad:#ff718b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,"Microsoft YaHei",sans-serif}
main{max-width:1280px;margin:auto;padding:28px}.top{display:flex;justify-content:space-between;gap:16px;align-items:end}h1{margin:0;font-size:26px}.muted{color:var(--muted)}
.badge{padding:7px 12px;border-radius:99px;background:#263450}.complete{color:var(--ok)}.running{color:var(--run)}.failed,.stopped{color:var(--bad)}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:22px 0}.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:17px}.value{font-size:28px;font-weight:700;margin-top:8px}.label{color:var(--muted);font-size:13px}
.bar{height:10px;background:#25304a;border-radius:10px;overflow:hidden;margin-top:12px}.bar>i{display:block;height:100%;background:linear-gradient(90deg,#4e91ff,#50d890)}
.panel{background:var(--card);border:1px solid var(--line);border-radius:14px;margin-top:14px;padding:18px}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line)}th{color:var(--muted);position:sticky;top:0;background:var(--card)}
.tables{max-height:390px;overflow:auto}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;background:var(--muted)}.dot.complete{background:var(--ok)}.dot.running{background:var(--run)}
@media(max-width:850px){.grid{grid-template-columns:repeat(2,1fr)}.top{display:block}}
</style></head>
<body><main>
<div class="top"><div><h1>MIMIC 单次住院原始归档</h1><div class="muted" id="path"></div></div><div class="badge" id="status">读取中</div></div>
<div class="grid">
 <div class="card"><div class="label">源表 staging</div><div class="value" id="staging">—</div><div class="bar"><i id="stagingBar"></i></div></div>
 <div class="card"><div class="label">JSONL 分片</div><div class="value" id="shards">—</div><div class="bar"><i id="shardBar"></i></div></div>
 <div class="card"><div class="label">最终 JSONL</div><div class="value" id="merged">—</div><div class="muted" id="records"></div></div>
 <div class="card"><div class="label">实际运行时间 / ETA</div><div class="value" id="elapsed">—</div><div class="muted" id="eta"></div></div>
 <div class="card"><div class="label">工作目录</div><div class="value" id="workSize">—</div><div class="muted">含 staging、分片、manifest</div></div>
 <div class="card"><div class="label">磁盘总占用</div><div class="value" id="diskTotal">—</div><div class="muted" id="diskFree"></div></div>
 <div class="card"><div class="label">物理内存</div><div class="value" id="memory">—</div><div class="muted" id="memoryFree"></div></div>
 <div class="card"><div class="label">当前阶段</div><div class="value" id="phase">—</div><div class="muted" id="updated"></div></div>
</div>
<div class="panel"><b>当前10,000例 EDA</b><div class="grid" id="edaCards" style="margin-bottom:0"></div></div>
<div class="panel"><b>32张住院内源表</b><div class="tables"><table><thead><tr><th>表</th><th>状态</th><th>staging</th><th>最近写入</th></tr></thead><tbody id="tableRows"></tbody></table></div></div>
<div class="panel muted">页面每5秒读取一次本地 manifest 和文件元数据，不读取患者记录内容。单张大表处理期间只显示“处理中”，不伪造表内百分比。</div>
</main><script>
const gib=n=>(n/1073741824).toFixed(n>=1073741824?3:4)+' GiB';
const dur=s=>{s=Math.max(0,Math.round(s||0));let m=Math.floor(s/60),h=Math.floor(m/60);return h?`${h}时${m%60}分`:`${m}分${s%60}秒`};
async function refresh(){try{let r=await fetch('/api/status',{cache:'no-store'}),d=await r.json();
 status.textContent=d.status_label;status.className='badge '+d.status;path.textContent=d.merged_path;
 staging.textContent=`${d.staging_complete}/${d.staging_total}`;stagingBar.style.width=(100*d.staging_complete/d.staging_total)+'%';
 shards.textContent=`${d.shards_complete}/${d.shards_total}`;shardBar.style.width=(100*d.shards_complete/Math.max(1,d.shards_total))+'%';
 merged.textContent=d.merged_bytes?gib(d.merged_bytes):'尚未生成';records.textContent=d.records?`${d.records.toLocaleString()} 次住院`:'';
 elapsed.textContent=dur(d.elapsed_seconds);eta.textContent=d.status==='complete'?'已完成':(d.eta_seconds==null?'当前阶段无法可靠估算':`预计剩余 ${dur(d.eta_seconds)}`);
 workSize.textContent=gib(d.workdir_bytes);diskTotal.textContent=gib(d.disk_total_bytes);diskFree.textContent=`目标盘剩余 ${gib(d.disk_free_bytes)}`;
 memory.textContent=`${gib(d.memory_used_bytes)}`;memoryFree.textContent=`总计 ${gib(d.memory_total_bytes)}，可用 ${gib(d.memory_available_bytes)}`;
 phase.textContent=d.phase;updated.textContent=`状态更新时间 ${d.updated_at}`;
 if(d.eda){let e=d.eda;edaCards.innerHTML=`<div><div class="label">唯一患者</div><div class="value">${e.subjects.toLocaleString()}</div></div><div><div class="label">冠状动脉谱住院</div><div class="value">${e.cad_admissions.toLocaleString()}</div></div><div><div class="label">平均每次住院</div><div class="value">${(e.mean_line_bytes/1024).toFixed(1)} KiB</div></div><div><div class="label">Schema / 孤立行</div><div class="value">${e.invalid_records} / ${e.orphan_rows}</div></div>`}else{edaCards.innerHTML='<span class="muted">EDA metrics尚未生成</span>'}
 tableRows.innerHTML=d.tables.map(x=>`<tr><td>${x.key}</td><td><span class="dot ${x.status}"></span>${x.status_label}</td><td>${gib(x.bytes)}</td><td>${x.modified_at||'—'}</td></tr>`).join('');
 }catch(e){status.textContent='读取失败';status.className='badge failed'}}
refresh();setInterval(refresh,5000);
</script></body></html>"""


def _directory_stats(path: Path) -> tuple[int, float | None]:
    total = 0
    latest: float | None = None
    if not path.exists():
        return total, latest
    for item in path.rglob("*"):
        if item.is_file():
            stat = item.stat()
            total += stat.st_size
            latest = stat.st_mtime if latest is None else max(latest, stat.st_mtime)
    return total, latest


def _iso(timestamp: float | None) -> str | None:
    return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds") if timestamp else None


def _memory_status() -> tuple[int, int]:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
            ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong),
            ("total_page_file", ctypes.c_ulonglong), ("available_page_file", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
            ("available_extended_virtual", ctypes.c_ulonglong),
        ]

    state = MemoryStatus()
    state.length = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
        raise OSError("GlobalMemoryStatusEx failed")
    return int(state.total_physical), int(state.available_physical)


def collect_status(
    output_dir: Path,
    merged_path: Path,
    eda_metrics_path: Path | None = None,
    activity_path: Path | None = None,
) -> dict[str, Any]:
    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    staging_state = manifest.get("staging", {})
    shard_state = manifest.get("shards", {})
    merged_state = manifest.get("merged") or {}
    selection_path = output_dir / "selection.jsonl"
    started = selection_path.stat().st_ctime if selection_path.exists() else None
    manifest_modified = manifest_path.stat().st_mtime if manifest_path.exists() else None
    completed = merged_state.get("status") == "complete" and merged_path.exists()
    now = time.time()

    tables = []
    for source in ARCHIVE_SOURCES:
        directory = output_dir / "staging" / source.key
        size, modified = _directory_stats(directory)
        is_complete = staging_state.get(source.key, {}).get("status") == "complete"
        tables.append({
            "key": source.key,
            "status": "complete" if is_complete else "pending",
            "status_label": "完成" if is_complete else "等待/处理中",
            "bytes": size,
            "modified_at": _iso(modified),
        })

    staging_complete = sum(item["status"] == "complete" for item in tables)
    sample_size = int(manifest.get("identity", {}).get("sample_size", 0))
    shard_size = int(manifest.get("identity", {}).get("shard_size", 1))
    shards_total = (sample_size + shard_size - 1) // shard_size if sample_size else 0
    shards_complete = sum(value.get("status") == "complete" for value in shard_state.values())
    workdir_bytes, workdir_modified = _directory_stats(output_dir)
    merged_bytes = merged_path.stat().st_size if merged_path.exists() else 0
    disk = shutil.disk_usage(merged_path.parent if merged_path.parent.exists() else output_dir.parent)
    memory_total, memory_available = _memory_status()

    external_activity = (
        activity_path.stat().st_mtime
        if activity_path is not None and activity_path.is_file()
        else None
    )
    activity_modified = max(
        manifest_modified or 0,
        workdir_modified or 0,
        external_activity or 0,
    ) or None

    if completed:
        status, status_label, phase = "complete", "提取完成", "已合并并校验"
        end = manifest_modified or now
    elif activity_modified and now - activity_modified <= 180:
        status, status_label = "running", "正在提取"
        phase = "源表 staging" if staging_complete < len(ARCHIVE_SOURCES) else "分片组装/合并"
        end = now
    elif manifest_path.exists():
        status, status_label, phase = "stopped", "未完成且无近期写入", "等待续跑或诊断"
        end = now
    else:
        status, status_label, phase = "stopped", "尚未启动", "等待 manifest"
        end = now

    eda = None
    if eda_metrics_path is not None and eda_metrics_path.is_file():
        raw_eda = json.loads(eda_metrics_path.read_text(encoding="utf-8"))
        eda = {
            "subjects": int(raw_eda["subjects"]),
            "cad_admissions": int(raw_eda["cad"]["admissions"]),
            "mean_line_bytes": float(raw_eda["line_bytes"]["mean"]),
            "invalid_records": int(raw_eda["schema"]["invalid_records"]),
            "orphan_rows": sum(int(value) for value in raw_eda["orphan_child_rows"].values()),
        }

    return {
        "status": status, "status_label": status_label, "phase": phase,
        "staging_complete": staging_complete, "staging_total": len(ARCHIVE_SOURCES),
        "reference_complete": sum(value.get("status") == "complete" for value in manifest.get("reference_tables", {}).values()),
        "reference_total": len(REFERENCE_SOURCE_KEYS),
        "shards_complete": shards_complete, "shards_total": shards_total,
        "records": int(merged_state.get("records", 0)),
        "merged_bytes": merged_bytes, "workdir_bytes": workdir_bytes,
        "disk_total_bytes": workdir_bytes + merged_bytes, "disk_free_bytes": disk.free,
        "memory_total_bytes": memory_total, "memory_available_bytes": memory_available,
        "memory_used_bytes": memory_total - memory_available,
        "elapsed_seconds": max(0, end - started) if started else 0,
        "eta_seconds": 0 if completed else None,
        "updated_at": _iso(activity_modified),
        "manifest_updated_at": _iso(manifest_modified),
        "merged_path": str(merged_path),
        "tables": tables, "eda": eda,
    }


class StatusCache:
    def __init__(self, collector: Any, ttl_seconds: float = 30.0) -> None:
        self.collector = collector
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._value: dict[str, Any] | None = None
        self._refreshed_at = 0.0

    def get(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._value is None:
            with self._lock:
                if self._value is None:
                    self._refresh_locked()
            return self._value
        if now - self._refreshed_at >= self.ttl_seconds:
            threading.Thread(target=self._refresh_if_available, daemon=True).start()
        return self._value

    def _refresh_if_available(self) -> None:
        if not self._lock.acquire(blocking=False):
            return
        try:
            self._refresh_locked()
        finally:
            self._lock.release()

    def _refresh_locked(self) -> None:
        self._value = self.collector()
        self._refreshed_at = time.monotonic()


def create_handler(
    output_dir: Path,
    merged_path: Path,
    eda_metrics_path: Path | None = None,
    activity_path: Path | None = None,
) -> type[BaseHTTPRequestHandler]:
    cache = StatusCache(
        lambda: collect_status(
            output_dir,
            merged_path,
            eda_metrics_path,
            activity_path,
        )
    )
    cache.get()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/api/status":
                payload = json.dumps(
                    cache.get(),
                    ensure_ascii=False,
                ).encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            elif self.path in ("/", "/index.html"):
                payload = HTML.encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            else:
                self.send_error(404); return
            self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(payload)))
            self.end_headers(); self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def main() -> None:
    defaults = RawArchiveConfig()
    parser = argparse.ArgumentParser(description="Serve a local read-only raw archive dashboard")
    parser.add_argument("--output-dir", type=Path, default=defaults.output_dir)
    parser.add_argument("--merged-output", type=Path, default=defaults.merged_path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--eda-metrics",
        type=Path,
        default=Path("docs/reports/mimic-raw-10000-eda-metrics.json"),
    )
    parser.add_argument("--activity-file", type=Path)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer(
        (args.host, args.port),
        create_handler(
            args.output_dir,
            args.merged_output,
            args.eda_metrics,
            args.activity_file,
        ),
    )
    url = f"http://{args.host}:{args.port}/"
    print(url, flush=True)
    if args.open_browser:
        webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
