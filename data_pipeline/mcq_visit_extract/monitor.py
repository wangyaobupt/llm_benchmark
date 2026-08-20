"""Local read-only HTML dashboard for mcq_visit_extract progress."""

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

from .catalog import DICTIONARY_KEYS, FACT_SOURCES
from .progress import ACTIVITY_NAME, PHASE_LABELS

HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>出题 Visit 抽取进度</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--card:#151c30;--line:#293553;--text:#edf2ff;--muted:#91a0bf;--ok:#50d890;--run:#69a7ff;--bad:#ff718b;--wait:#8b97b3}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,"Microsoft YaHei",sans-serif}
main{max-width:1280px;margin:auto;padding:28px}
.top{display:flex;justify-content:space-between;gap:16px;align-items:end}
h1{margin:0;font-size:26px}.muted{color:var(--muted)}
.badge{padding:7px 12px;border-radius:99px;background:#263450;white-space:nowrap}
.complete{color:var(--ok)}.running{color:var(--run)}.failed,.stopped{color:var(--bad)}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:22px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:17px}
.value{font-size:28px;font-weight:700;margin-top:8px}.label{color:var(--muted);font-size:13px}
.bar{height:10px;background:#25304a;border-radius:10px;overflow:hidden;margin-top:12px}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,#4e91ff,#50d890);width:0}
.panel{background:var(--card);border:1px solid var(--line);border-radius:14px;margin-top:14px;padding:18px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line)}
th{color:var(--muted);position:sticky;top:0;background:var(--card)}
.tables{max-height:360px;overflow:auto}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;background:var(--wait)}
.dot.complete{background:var(--ok)}.dot.running{background:var(--run)}.dot.pending{background:var(--wait)}
.steps{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.step{padding:6px 10px;border-radius:999px;border:1px solid var(--line);font-size:12px;color:var(--muted)}
.step.complete{border-color:#2e6b4f;color:var(--ok)}.step.running{border-color:#3d6cb0;color:var(--run)}
@media(max-width:850px){.grid{grid-template-columns:repeat(2,1fr)}.top{display:block}}
</style></head>
<body><main>
<div class="top">
  <div>
    <h1>出题 Visit 抽取</h1>
    <div class="muted" id="path"></div>
  </div>
  <div class="badge" id="runStatus">读取中</div>
</div>
<div class="grid">
  <div class="card"><div class="label">纳入漏斗</div><div class="value" id="funnel">—</div><div class="bar"><i id="funnelBar"></i></div></div>
  <div class="card"><div class="label">源表 staging</div><div class="value" id="staging">—</div><div class="bar"><i id="stagingBar"></i></div></div>
  <div class="card"><div class="label">Visit 分片</div><div class="value" id="shards">—</div><div class="bar"><i id="shardBar"></i></div></div>
  <div class="card"><div class="label">交付文件</div><div class="value" id="deliver">—</div><div class="muted" id="records"></div></div>
  <div class="card"><div class="label">已运行 / 预计剩余</div><div class="value" id="elapsed">—</div><div class="muted" id="eta"></div></div>
  <div class="card"><div class="label">工作目录</div><div class="value" id="workSize">—</div><div class="muted" id="diskFree"></div></div>
  <div class="card"><div class="label">当前阶段</div><div class="value" id="phase">—</div><div class="muted" id="detail"></div></div>
  <div class="card"><div class="label">抽样</div><div class="value" id="sample">—</div><div class="muted" id="pool"></div></div>
</div>
<div class="panel">
  <b>漏斗计数</b>
  <div class="grid" id="funnelCards" style="margin-bottom:0"></div>
  <div class="steps" id="steps"></div>
</div>
<div class="panel"><b>源表与字典</b><div class="tables"><table><thead><tr><th>表</th><th>状态</th><th>体积</th><th>最近写入</th></tr></thead><tbody id="tableRows"></tbody></table></div></div>
<div class="panel"><b>Visit 分片</b><div class="tables"><table><thead><tr><th>分片</th><th>状态</th><th>行数</th></tr></thead><tbody id="shardRows"></tbody></table></div></div>
<div class="panel muted">页面每 2 秒读取本地 manifest / 心跳文件 / 文件体积，不打开 visits.csv 或出院小结原文。单张大表 COPY 期间只显示“处理中”，不伪造表内百分比。</div>
</main>
<script>
const gib=n=>{if(!n)return '0 B';if(n<1024)return n+' B';if(n<1048576)return (n/1024).toFixed(1)+' KiB';if(n<1073741824)return (n/1048576).toFixed(1)+' MiB';return (n/1073741824).toFixed(3)+' GiB'};
const dur=s=>{s=Math.max(0,Math.round(s||0));const m=Math.floor(s/60),h=Math.floor(m/60);return h?`${h}时${m%60}分`:`${m}分${s%60}秒`};
const pct=(a,b)=>b?Math.min(100,100*a/b):0;
async function refresh(){
  try{
    const r=await fetch('/api/status',{cache:'no-store'});
    const d=await r.json();
    runStatus.textContent=d.status_label; runStatus.className='badge '+d.status;
    path.textContent=d.output_dir;
    funnel.textContent=`${d.funnel_steps_complete}/${d.funnel_steps_total}`;
    funnelBar.style.width=pct(d.funnel_steps_complete,d.funnel_steps_total)+'%';
    staging.textContent=`${d.staging_complete}/${d.staging_total}`;
    stagingBar.style.width=pct(d.staging_complete,d.staging_total)+'%';
    shards.textContent=`${d.shards_complete}/${d.shards_total}`;
    shardBar.style.width=pct(d.shards_complete,d.shards_total)+'%';
    deliver.textContent=d.deliverables_complete?'已写出':'未完成';
    records.textContent=d.records?`${d.records.toLocaleString()} 行 · CSV ${gib(d.csv_bytes)} · JSON ${gib(d.json_bytes)}`:'';
    elapsed.textContent=dur(d.elapsed_seconds);
    eta.textContent=d.status==='complete'?'已完成':(d.eta_seconds==null?'当前阶段无法可靠估算':`预计剩余 ${dur(d.eta_seconds)}`);
    workSize.textContent=gib(d.workdir_bytes);
    diskFree.textContent=`目标盘剩余 ${gib(d.disk_free_bytes)}`;
    phase.textContent=d.phase_label||d.phase||'—';
    detail.textContent=d.detail||(`状态更新 ${d.updated_at||'—'}`);
    sample.textContent=d.sample_size?d.sample_size.toLocaleString():'—';
    pool.textContent=`${d.sample_pool||''} · shard ${d.shard_size||'—'}`;
    const c=d.funnel_counts||{};
    funnelCards.innerHTML=[
      ['候选 admissions',c.candidate_count],
      ['排除 Stage1',c.excluded_stage1],
      ['排除 Stage2',c.excluded_stage2],
      ['排除 Stage3',c.excluded_stage3],
      ['eligible',c.eligible_count],
      ['开发池 eligible',c.eligible_development_count],
    ].map(([k,v])=>`<div><div class="label">${k}</div><div class="value">${v==null?'—':Number(v).toLocaleString()}</div></div>`).join('');
    steps.innerHTML=(d.pipeline_steps||[]).map(s=>`<span class="step ${s.status}">${s.label}</span>`).join('');
    tableRows.innerHTML=(d.tables||[]).map(x=>`<tr><td>${x.key}</td><td><span class="dot ${x.status}"></span>${x.status_label}</td><td>${gib(x.bytes)}</td><td>${x.modified_at||'—'}</td></tr>`).join('');
    shardRows.innerHTML=(d.shards||[]).map(x=>`<tr><td>${x.id}</td><td><span class="dot ${x.status}"></span>${x.status_label}</td><td>${x.records==null?'—':x.records}</td></tr>`).join('')||'<tr><td colspan="3" class="muted">尚未开始分片</td></tr>';
  }catch(e){
    runStatus.textContent='读取失败'; runStatus.className='badge failed';
  }
}
refresh(); setInterval(refresh,2000);
</script>
</body></html>
"""

ACTIVITY_WINDOW_SECONDS = 180


def _iso(timestamp: float | None) -> str | None:
    return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds") if timestamp else None


def _file_stat(path: Path) -> tuple[int, float | None]:
    try:
        if not path.is_file():
            return 0, None
        stat = path.stat()
    except OSError:
        return 0, None
    return stat.st_size, stat.st_mtime


def _directory_stats(path: Path) -> tuple[int, float | None]:
    total = 0
    latest: float | None = None
    if not path.exists():
        return total, latest
    try:
        items = list(path.rglob("*"))
    except OSError:
        return total, latest
    for item in items:
        try:
            if not item.is_file():
                continue
            stat = item.stat()
        except OSError:
            continue
        total += stat.st_size
        latest = stat.st_mtime if latest is None else max(latest, stat.st_mtime)
    return total, latest


def _memory_status() -> tuple[int, int]:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("memory_load", ctypes.c_ulong),
            ("total_physical", ctypes.c_ulonglong),
            ("available_physical", ctypes.c_ulonglong),
            ("total_page_file", ctypes.c_ulonglong),
            ("available_page_file", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong),
            ("available_virtual", ctypes.c_ulonglong),
            ("available_extended_virtual", ctypes.c_ulonglong),
        ]

    state = MemoryStatus()
    state.length = ctypes.sizeof(MemoryStatus)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
            return 0, 0
    except (AttributeError, OSError, ValueError):
        return 0, 0
    return int(state.total_physical), int(state.available_physical)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _table_row(
    key: str,
    *,
    complete: bool,
    running: bool,
    path: Path,
) -> dict[str, Any]:
    size, modified = _file_stat(path) if path.is_file() else _directory_stats(path)
    if complete:
        status, label = "complete", "完成"
    elif running:
        status, label = "running", "处理中"
    else:
        status, label = "pending", "等待"
    return {
        "key": key,
        "status": status,
        "status_label": label,
        "bytes": size,
        "modified_at": _iso(modified),
    }


def collect_status(output_dir: Path) -> dict[str, Any]:
    output_dir = Path(output_dir)
    manifest = _read_json(output_dir / "manifest.json")
    activity = _read_json(output_dir / ACTIVITY_NAME)
    funnel_counts = _read_json(output_dir / "funnel.json")
    identity = manifest.get("identity") or {}
    sample_size = int(identity.get("sample_size") or 0)
    shard_size = int(identity.get("shard_size") or 1)
    shards_total = (sample_size + shard_size - 1) // shard_size if sample_size else 0

    funnel_state = manifest.get("funnel") or {}
    funnel_steps = [
        ("n1", "人口统计", funnel_state.get("n1", {}).get("status") == "complete"),
        ("n2", "主诊断", funnel_state.get("n2", {}).get("status") == "complete"),
        ("eligible", "出院小结 eligible", funnel_state.get("eligible", {}).get("status") == "complete"),
    ]
    funnel_complete = sum(1 for _, _, done in funnel_steps if done)
    selection_done = (manifest.get("selection") or {}).get("status") == "complete"
    staging_state = manifest.get("staging") or {}
    reference_state = manifest.get("reference_tables") or {}
    shard_state = manifest.get("shards") or {}
    working_done = (manifest.get("working") or {}).get("status") == "complete"
    deliverables = manifest.get("deliverables") or {}
    csv_path = output_dir / "visits.csv"
    json_path = output_dir / "visits.json"
    deliverables_complete = (
        deliverables.get("status") == "complete" and csv_path.is_file() and json_path.is_file()
    )

    current_phase = str(activity.get("phase") or "")
    current_detail = str(activity.get("detail") or "")
    tables = []
    for source in FACT_SOURCES:
        tables.append(
            _table_row(
                source.key,
                complete=staging_state.get(source.key, {}).get("status") == "complete",
                running=current_phase == "staging" and current_detail == source.key,
                path=output_dir / "staging" / f"{source.key}.parquet",
            )
        )
    for key in DICTIONARY_KEYS:
        tables.append(
            _table_row(
                key,
                complete=reference_state.get(key, {}).get("status") == "complete",
                running=current_phase == "reference" and current_detail == key,
                path=output_dir / "reference_tables" / f"{key}.parquet",
            )
        )
    staging_complete = sum(
        1 for row in tables if row["status"] == "complete" and row["key"] not in DICTIONARY_KEYS
    )
    shards = []
    for shard_id in range(shards_total):
        entry = shard_state.get(str(shard_id), {})
        complete = entry.get("status") == "complete"
        running = current_phase == "assemble" and current_detail == str(shard_id)
        if complete:
            status, label = "complete", "完成"
        elif running:
            status, label = "running", "处理中"
        else:
            status, label = "pending", "等待"
        shards.append(
            {
                "id": f"part-{shard_id:05d}",
                "status": status,
                "status_label": label,
                "records": entry.get("records"),
            }
        )
    shards_complete = sum(1 for item in shards if item["status"] == "complete")

    pipeline_steps = [
        {"id": "funnel", "label": "漏斗", "status": "complete" if funnel_complete == 3 else ("running" if current_phase.startswith("funnel") else "pending")},
        {"id": "selection", "label": "抽样", "status": "complete" if selection_done else ("running" if current_phase == "selection" else "pending")},
        {"id": "staging", "label": "staging", "status": "complete" if staging_complete == len(FACT_SOURCES) else ("running" if current_phase in {"staging", "reference"} else "pending")},
        {"id": "assemble", "label": "分片", "status": "complete" if shards_total and shards_complete == shards_total else ("running" if current_phase == "assemble" else "pending")},
        {"id": "publish", "label": "交付", "status": "complete" if deliverables_complete else ("running" if current_phase == "publish" else "pending")},
    ]

    workdir_bytes, workdir_modified = _directory_stats(output_dir)
    csv_bytes, _ = _file_stat(csv_path)
    json_bytes, _ = _file_stat(json_path)
    manifest_path = output_dir / "manifest.json"
    activity_path = output_dir / ACTIVITY_NAME
    started = None
    if manifest_path.exists():
        started = manifest_path.stat().st_ctime
    now = time.time()
    activity_mtime = activity_path.stat().st_mtime if activity_path.is_file() else None
    manifest_mtime = manifest_path.stat().st_mtime if manifest_path.exists() else None
    latest = max(filter(None, [activity_mtime, manifest_mtime, workdir_modified]), default=None)

    if deliverables_complete:
        status, status_label = "complete", "抽取完成"
        phase = "complete"
        phase_label = PHASE_LABELS["complete"]
        end = latest or now
    elif latest and now - latest <= ACTIVITY_WINDOW_SECONDS:
        status, status_label = "running", "正在抽取"
        phase = current_phase or "running"
        phase_label = str(activity.get("phase_label") or PHASE_LABELS.get(phase, "处理中"))
        end = now
    elif manifest_path.exists():
        status, status_label = "stopped", "未完成，可续跑"
        phase = current_phase or "stopped"
        phase_label = "等待续跑"
        end = now
    else:
        status, status_label = "stopped", "尚未启动"
        phase = "stopped"
        phase_label = "等待 manifest"
        end = now

    eta_seconds = None
    elapsed = max(0.0, end - started) if started else 0.0
    if status == "running" and staging_complete and staging_complete < len(FACT_SOURCES) and elapsed:
        eta_seconds = elapsed * (len(FACT_SOURCES) - staging_complete) / max(staging_complete, 1)
    elif status == "running" and shards_complete and shards_total > shards_complete and elapsed:
        eta_seconds = elapsed * (shards_total - shards_complete) / max(shards_complete, 1)

    disk = shutil.disk_usage(output_dir if output_dir.exists() else Path.cwd())
    memory_total, memory_available = _memory_status()

    return {
        "status": status,
        "status_label": status_label,
        "phase": phase,
        "phase_label": phase_label,
        "detail": current_detail,
        "output_dir": str(output_dir),
        "sample_size": sample_size,
        "shard_size": shard_size,
        "sample_pool": identity.get("sample_pool"),
        "funnel_steps_complete": funnel_complete,
        "funnel_steps_total": 3,
        "staging_complete": staging_complete,
        "staging_total": len(FACT_SOURCES),
        "reference_complete": sum(
            1 for key in DICTIONARY_KEYS if reference_state.get(key, {}).get("status") == "complete"
        ),
        "reference_total": len(DICTIONARY_KEYS),
        "shards_complete": shards_complete,
        "shards_total": shards_total,
        "deliverables_complete": deliverables_complete,
        "records": int(deliverables.get("records") or 0),
        "csv_bytes": csv_bytes,
        "json_bytes": json_bytes,
        "workdir_bytes": workdir_bytes,
        "disk_free_bytes": disk.free,
        "memory_total_bytes": memory_total,
        "memory_available_bytes": memory_available,
        "elapsed_seconds": elapsed,
        "eta_seconds": eta_seconds,
        "updated_at": activity.get("updated_at") or _iso(latest),
        "funnel_counts": funnel_counts,
        "pipeline_steps": pipeline_steps,
        "tables": tables,
        "shards": shards,
        "selection_complete": selection_done,
        "working_complete": working_done,
    }


class StatusCache:
    def __init__(self, collector: Any, ttl_seconds: float = 1.5) -> None:
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
            return self._value or {}
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
        try:
            self._value = self.collector()
            self._refreshed_at = time.monotonic()
        except OSError:
            if self._value is None:
                self._value = {
                    "status": "running",
                    "status_label": "进度读取中",
                    "phase": "running",
                    "phase_label": "工作目录正在更新",
                    "tables": [],
                    "shards": [],
                    "pipeline_steps": [],
                    "funnel_counts": {},
                }
                self._refreshed_at = time.monotonic()


def create_handler(output_dir: Path) -> type[BaseHTTPRequestHandler]:
    cache = StatusCache(lambda: collect_status(output_dir))
    cache.get()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/api/status":
                payload = json.dumps(cache.get(), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
            elif self.path in ("/", "/index.html"):
                payload = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
            else:
                self.send_error(404)
                return
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def start_monitor_thread(
    output_dir: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8766,
    open_browser: bool = True,
) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), create_handler(output_dir))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://{host}:{port}/"
    if open_browser:
        webbrowser.open(url)
    return url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve a local visit-extract progress dashboard")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/derived/mcq_visit_extract/random10k_dev20"),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), create_handler(args.output_dir))
    url = f"http://{args.host}:{args.port}/"
    print(url, flush=True)
    if args.open_browser:
        webbrowser.open(url)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
