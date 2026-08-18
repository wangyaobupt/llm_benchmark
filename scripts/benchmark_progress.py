"""Write and serve the cross-stage benchmark execution progress dashboard."""

from __future__ import annotations

import argparse
import json
import os
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
STATE = DOCS / "benchmark-progress.json"
HTML = DOCS / "benchmark-progress.html"

DEFAULT_STATE: dict[str, Any] = {
    "updated_at": None,
    "current_stage": "W0",
    "overall_status": "running",
    "project_mode": "exploratory-only",
    "official_final_test_enabled": False,
    "rehearsal_mode_enabled": True,
    "stages": {
        f"W{i}": {"status": "pending", "message": "等待开始", "updated_at": None}
        for i in range(11)
    },
    "recent_events": [],
}

HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta http-equiv="refresh" content="5">
<title>Benchmark W0–W10 执行进度</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;max-width:1100px;background:#f5f7fb;color:#172033}}
.card{{background:white;border-radius:12px;padding:1rem 1.2rem;margin:.7rem 0;box-shadow:0 2px 12px #17203318}}
.head{{display:flex;justify-content:space-between;align-items:center}} .stage{{font-weight:700;font-size:1.1rem}}
.status{{padding:.2rem .6rem;border-radius:999px;background:#e7edf7}} .completed{{background:#d9f5df;color:#176b2c}}
.in_progress,.running{{background:#fff0c2;color:#7a5200}} .failed{{background:#ffdcdc;color:#9b2020}}
small{{color:#65718a}} pre{{white-space:pre-wrap}}</style></head>
<body><h1>Benchmark W0–W10 执行进度</h1><div id="app">读取状态中…</div>
<script>
async function render() {{
  const app=document.getElementById('app');
  try {{
    const r=await fetch('benchmark-progress.json?ts='+Date.now(),{{cache:'no-store'}}); const s=await r.json();
    let modeText=s.project_mode||'未声明';
    let gateText=(s.official_final_test_enabled===false?'禁止 official final-test；仅允许 rehearsal':'official final-test 可用');
    let h='<div class="card"><div class="head"><b>当前阶段：'+s.current_stage+'</b><span class="status '+s.overall_status+'">'+s.overall_status+'</span></div><div>项目模式：<strong>'+modeText+'</strong></div><div>'+gateText+'</div><small>更新时间：'+(s.updated_at||'—')+'</small></div>';
    for (const [id,v] of Object.entries(s.stages)) h+='<div class="card"><div class="head"><span class="stage">'+id+'</span><span class="status '+v.status+'">'+v.status+'</span></div><div>'+v.message+'</div><small>'+(v.updated_at||'—')+'</small></div>';
    if(s.recent_events?.length) h+='<div class="card"><b>最近事件</b><pre>'+s.recent_events.map(e=>e.at+'  '+e.message).join('\\n')+'</pre></div>';
    app.innerHTML=h;
  }} catch(e) {{ app.innerHTML='<div class="card">无法读取状态。请在项目根目录运行 <code>python scripts/benchmark_progress.py serve</code> 后打开本页。</div>'; }}
}}
render();
</script></body></html>"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_state(state: dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now()
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, STATE)
    if not HTML.exists():
        HTML.write_text(HTML_TEMPLATE, encoding="utf-8")


def load_state() -> dict[str, Any]:
    if not STATE.is_file():
        return json.loads(json.dumps(DEFAULT_STATE))
    return json.loads(STATE.read_text(encoding="utf-8"))


def update(stage: str, status: str, message: str) -> None:
    state = load_state()
    state.setdefault("project_mode", "exploratory-only")
    state.setdefault("official_final_test_enabled", False)
    state.setdefault("rehearsal_mode_enabled", True)
    timestamp = now()
    state["current_stage"] = stage
    state["stages"].setdefault(stage, {})
    state["stages"][stage].update({"status": status, "message": message, "updated_at": timestamp})
    state["recent_events"] = ([{"at": timestamp, "message": f"{stage}: {message}"}] + state.get("recent_events", []))[:30]
    if status == "failed":
        state["overall_status"] = "failed"
    elif all(item.get("status") == "completed" for item in state["stages"].values()):
        state["overall_status"] = "completed"
    write_state(state)


def serve(port: int) -> None:
    if not STATE.exists():
        write_state(DEFAULT_STATE)
    os.chdir(DOCS)
    server = ThreadingHTTPServer(("127.0.0.1", port), SimpleHTTPRequestHandler)
    print(f"进度面板：http://127.0.0.1:{port}/benchmark-progress.html")
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    p_update = sub.add_parser("update")
    p_update.add_argument("stage")
    p_update.add_argument("status", choices=["pending", "running", "completed", "failed"])
    p_update.add_argument("message")
    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    if args.command == "init":
        write_state(DEFAULT_STATE)
    elif args.command == "update":
        update(args.stage, args.status, args.message)
    else:
        serve(args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
