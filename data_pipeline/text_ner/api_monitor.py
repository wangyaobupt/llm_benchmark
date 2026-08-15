"""Read-only HTML progress monitoring for resumable Text NER API batches."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import html
import json
import math
import os
from pathlib import Path
import time
from typing import Any, Callable


class ApiMonitorError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


@dataclass
class JsonlTracker:
    """Incrementally index request IDs without retaining clinical payloads."""

    path: Path
    collect_usage: bool = False
    byte_offset: int = 0
    pending_bytes: bytes = b""
    line_count: int = 0
    nonempty_line_count: int = 0
    invalid_line_count: int = 0
    duplicate_request_id_count: int = 0
    request_ids: set[str] = field(default_factory=set)
    usage: dict[str, int] = field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    )
    provider: str | None = None
    model_name: str | None = None
    model_version: str | None = None
    file_size: int = 0
    file_modified_at: float | None = None

    def _reset(self) -> None:
        self.byte_offset = 0
        self.pending_bytes = b""
        self.line_count = 0
        self.nonempty_line_count = 0
        self.invalid_line_count = 0
        self.duplicate_request_id_count = 0
        self.request_ids.clear()
        for key in self.usage:
            self.usage[key] = 0
        self.provider = None
        self.model_name = None
        self.model_version = None
        self.file_size = 0
        self.file_modified_at = None

    def refresh(self) -> None:
        path = Path(self.path)
        try:
            stat = path.stat()
        except FileNotFoundError:
            if self.byte_offset or self.request_ids or self.nonempty_line_count:
                self._reset()
            return
        except PermissionError as error:
            raise ApiMonitorError(
                "API_MONITOR_INPUT_PERMISSION_DENIED", str(path)
            ) from error
        if not path.is_file():
            raise ApiMonitorError("API_MONITOR_INPUT_NOT_FILE", str(path))
        if stat.st_size < self.byte_offset:
            self._reset()
        self.file_size = stat.st_size
        self.file_modified_at = stat.st_mtime
        if stat.st_size == self.byte_offset:
            return
        with path.open("rb") as handle:
            handle.seek(self.byte_offset)
            chunk = handle.read()
            self.byte_offset = handle.tell()
        complete = self.pending_bytes + chunk
        parts = complete.split(b"\n")
        self.pending_bytes = parts.pop()
        for raw_line in parts:
            self.line_count += 1
            if not raw_line.strip():
                continue
            self.nonempty_line_count += 1
            try:
                record = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.invalid_line_count += 1
                continue
            if not isinstance(record, dict):
                self.invalid_line_count += 1
                continue
            request_id = record.get("request_id")
            if not isinstance(request_id, str) or not request_id:
                self.invalid_line_count += 1
                continue
            if request_id in self.request_ids:
                self.duplicate_request_id_count += 1
                continue
            self.request_ids.add(request_id)
            if not self.collect_usage:
                continue
            usage = record.get("usage")
            if isinstance(usage, dict):
                for key in self.usage:
                    value = usage.get(key)
                    if isinstance(value, int) and value >= 0:
                        self.usage[key] += value
            for field_name in ("provider", "model_name", "model_version"):
                value = record.get(field_name)
                if isinstance(value, str) and value:
                    setattr(self, field_name, value)


@dataclass
class ApiMonitorSession:
    responses_path: Path
    audit_path: Path
    expected_requests: int
    stage_label: str
    refresh_seconds: int = 10
    stalled_after_seconds: int = 300
    rate_window_seconds: int = 300
    response_tracker: JsonlTracker = field(init=False)
    audit_tracker: JsonlTracker = field(init=False)
    samples: deque[tuple[float, int]] = field(default_factory=deque)

    def __post_init__(self) -> None:
        if self.expected_requests <= 0:
            raise ApiMonitorError(
                "API_MONITOR_EXPECTED_REQUESTS_INVALID", str(self.expected_requests)
            )
        if self.refresh_seconds <= 0:
            raise ApiMonitorError(
                "API_MONITOR_REFRESH_SECONDS_INVALID", str(self.refresh_seconds)
            )
        if self.stalled_after_seconds <= 0:
            raise ApiMonitorError(
                "API_MONITOR_STALLED_SECONDS_INVALID",
                str(self.stalled_after_seconds),
            )
        self.responses_path = Path(self.responses_path)
        self.audit_path = Path(self.audit_path)
        self.response_tracker = JsonlTracker(self.responses_path)
        self.audit_tracker = JsonlTracker(self.audit_path, collect_usage=True)

    def sample(
        self,
        *,
        now_epoch: float | None = None,
        now_monotonic: float | None = None,
    ) -> dict[str, Any]:
        self.response_tracker.refresh()
        self.audit_tracker.refresh()
        current_epoch = time.time() if now_epoch is None else now_epoch
        current_monotonic = (
            time.monotonic() if now_monotonic is None else now_monotonic
        )
        response_ids = self.response_tracker.request_ids
        audit_ids = self.audit_tracker.request_ids
        completed = len(response_ids & audit_ids)
        response_only = len(response_ids - audit_ids)
        audit_only = len(audit_ids - response_ids)
        self.samples.append((current_monotonic, completed))
        while (
            len(self.samples) > 1
            and current_monotonic - self.samples[0][0] > self.rate_window_seconds
        ):
            self.samples.popleft()
        elapsed = current_monotonic - self.samples[0][0]
        completed_delta = completed - self.samples[0][1]
        requests_per_minute = (
            completed_delta / elapsed * 60.0
            if elapsed > 0 and completed_delta > 0
            else 0.0
        )
        remaining = max(0, self.expected_requests - completed)
        eta_seconds = (
            remaining / requests_per_minute * 60.0
            if requests_per_minute > 0
            else None
        )
        update_candidates = [
            value
            for value in (
                self.response_tracker.file_modified_at,
                self.audit_tracker.file_modified_at,
            )
            if value is not None
        ]
        last_result_at = max(update_candidates) if update_candidates else None
        seconds_since_result = (
            max(0.0, current_epoch - last_result_at)
            if last_result_at is not None
            else None
        )
        invalid_lines = (
            self.response_tracker.invalid_line_count
            + self.audit_tracker.invalid_line_count
        )
        duplicate_ids = (
            self.response_tracker.duplicate_request_id_count
            + self.audit_tracker.duplicate_request_id_count
        )
        if invalid_lines or duplicate_ids:
            status_code, status_label = "invalid", "数据异常"
        elif response_only or audit_only:
            status_code, status_label = "mismatch", "写入未同步"
        elif completed >= self.expected_requests:
            status_code, status_label = "complete", "阶段完成"
        elif requests_per_minute > 0:
            status_code, status_label = "running", "运行中"
        elif last_result_at is None:
            status_code, status_label = "waiting", "等待任务启动"
        elif seconds_since_result is not None and (
            seconds_since_result > self.stalled_after_seconds
        ):
            status_code, status_label = "stalled", "可能停滞"
        else:
            status_code, status_label = "waiting", "等待新结果"
        percentage = min(100.0, completed / self.expected_requests * 100.0)
        return {
            "schema_version": "text-ner-api-monitor/1.0.0",
            "stage_label": self.stage_label,
            "status_code": status_code,
            "status_label": status_label,
            "expected_requests": self.expected_requests,
            "completed_requests": completed,
            "remaining_requests": remaining,
            "completion_percentage": percentage,
            "response_rows": self.response_tracker.nonempty_line_count,
            "response_unique_request_ids": len(response_ids),
            "audit_rows": self.audit_tracker.nonempty_line_count,
            "audit_unique_request_ids": len(audit_ids),
            "response_only_request_ids": response_only,
            "audit_only_request_ids": audit_only,
            "invalid_jsonl_rows": invalid_lines,
            "duplicate_request_ids": duplicate_ids,
            "requests_per_minute": requests_per_minute,
            "eta_seconds": eta_seconds,
            "last_result_at": last_result_at,
            "seconds_since_result": seconds_since_result,
            "generated_at": current_epoch,
            "refresh_seconds": self.refresh_seconds,
            "stalled_after_seconds": self.stalled_after_seconds,
            "provider": self.audit_tracker.provider,
            "model_name": self.audit_tracker.model_name,
            "model_version": self.audit_tracker.model_version,
            "usage": dict(self.audit_tracker.usage),
            "responses_path": str(self.responses_path),
            "audit_path": str(self.audit_path),
        }


def _format_timestamp(value: float | None) -> str:
    if value is None:
        return "尚无结果"
    return datetime.fromtimestamp(value).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")


def _format_duration(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "等待速度样本"
    seconds = max(0, int(round(value)))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}小时 {minutes}分钟"
    if minutes:
        return f"{minutes}分钟 {seconds}秒"
    return f"{seconds}秒"


def render_monitor_html(snapshot: dict[str, Any]) -> str:
    """Render a self-contained page that never embeds response payloads."""

    def escape(value: object) -> str:
        return html.escape(str(value), quote=True)
    percentage = float(snapshot["completion_percentage"])
    status_code = escape(snapshot["status_code"])
    refresh_seconds = int(snapshot["refresh_seconds"])
    generated_at_ms = int(float(snapshot["generated_at"]) * 1000)
    model_parts = [
        value
        for value in (
            snapshot.get("provider"),
            snapshot.get("model_name"),
            snapshot.get("model_version"),
        )
        if value
    ]
    model_label = " / ".join(map(str, model_parts)) or "等待首条审计记录"
    warnings: list[str] = []
    if snapshot["response_only_request_ids"]:
        warnings.append(
            f"{snapshot['response_only_request_ids']:,} 条 response 尚无对应 audit。"
        )
    if snapshot["audit_only_request_ids"]:
        warnings.append(
            f"{snapshot['audit_only_request_ids']:,} 条 audit 尚无对应 response。"
        )
    if snapshot["invalid_jsonl_rows"]:
        warnings.append(f"发现 {snapshot['invalid_jsonl_rows']:,} 条无效 JSONL。")
    if snapshot["duplicate_request_ids"]:
        warnings.append(
            f"发现 {snapshot['duplicate_request_ids']:,} 个重复 request ID。"
        )
    if snapshot["status_code"] == "stalled":
        warnings.append(
            f"超过 {snapshot['stalled_after_seconds']:,} 秒没有新结果，请检查 API 执行终端。"
        )
    warning_html = "".join(f"<li>{escape(item)}</li>" for item in warnings)
    if not warning_html:
        warning_html = "<li>未发现 response/audit 一致性异常。</li>"
    usage = snapshot["usage"]
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="{refresh_seconds}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Text NER API 运行监测</title>
  <style>
    :root {{ color-scheme: light; --ink:#17212b; --muted:#66717d; --line:#dfe5ea; --panel:#fff; --bg:#f4f7f9; --accent:#1769aa; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 "Segoe UI","Microsoft YaHei",sans-serif; }}
    main {{ width:min(1120px, calc(100% - 32px)); margin:32px auto; }}
    header {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-start; margin-bottom:20px; }}
    h1 {{ margin:0 0 5px; font-size:27px; }}
    .subtitle,.muted {{ color:var(--muted); }}
    .badge {{ border-radius:999px; padding:7px 13px; font-weight:700; white-space:nowrap; }}
    .badge.running,.badge.complete {{ color:#076b43; background:#dff6eb; }}
    .badge.waiting {{ color:#755500; background:#fff2c7; }}
    .badge.stalled,.badge.mismatch,.badge.invalid {{ color:#9a2c2c; background:#fde6e6; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:20px; box-shadow:0 5px 18px rgba(23,33,43,.05); margin-bottom:18px; }}
    .progress-head {{ display:flex; justify-content:space-between; gap:12px; align-items:end; }}
    .progress-value {{ font-size:38px; font-weight:750; letter-spacing:-1px; }}
    .progress-track {{ height:14px; background:#e8edf1; border-radius:10px; overflow:hidden; margin:14px 0 7px; }}
    .progress-fill {{ height:100%; width:{percentage:.4f}%; background:linear-gradient(90deg,#1769aa,#2aa683); transition:width .3s; }}
    .grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; }}
    .metric {{ border:1px solid var(--line); border-radius:11px; padding:15px; min-height:104px; }}
    .metric .label {{ color:var(--muted); font-size:13px; }}
    .metric .value {{ font-size:24px; font-weight:700; margin-top:6px; word-break:break-word; }}
    h2 {{ font-size:18px; margin:0 0 13px; }}
    table {{ width:100%; border-collapse:collapse; }}
    th,td {{ text-align:left; padding:9px 8px; border-bottom:1px solid var(--line); }}
    th {{ color:var(--muted); font-weight:600; width:44%; }}
    ul {{ margin:0; padding-left:22px; }}
    code {{ font-family:"Cascadia Mono",Consolas,monospace; font-size:12px; word-break:break-all; }}
    .stale {{ display:none; margin-bottom:18px; padding:12px 15px; border-radius:10px; color:#8a2c2c; background:#fde6e6; font-weight:650; }}
    footer {{ color:var(--muted); font-size:13px; padding:3px 2px 24px; }}
    @media (max-width:850px) {{ .grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} header {{ flex-direction:column; gap:9px; }} }}
    @media (max-width:520px) {{ .grid {{ grid-template-columns:1fr; }} main {{ width:min(100% - 20px,1120px); margin:18px auto; }} }}
  </style>
</head>
<body>
<main>
  <div id="monitor-stale" class="stale">监测 HTML 已停止更新；请检查监测命令是否仍在运行。</div>
  <header>
    <div><h1>Text NER API 运行监测</h1><div class="subtitle">{escape(snapshot['stage_label'])} · {escape(model_label)}</div></div>
    <div class="badge {status_code}">{escape(snapshot['status_label'])}</div>
  </header>
  <section class="panel">
    <div class="progress-head"><div><div class="muted">已完成（response 与 audit 交集）</div><div class="progress-value">{snapshot['completed_requests']:,} / {snapshot['expected_requests']:,}</div></div><strong>{percentage:.2f}%</strong></div>
    <div class="progress-track"><div class="progress-fill"></div></div>
    <div class="muted">剩余 {snapshot['remaining_requests']:,} 条</div>
  </section>
  <section class="grid panel">
    <div class="metric"><div class="label">近 5 分钟速度</div><div class="value">{snapshot['requests_per_minute']:.2f}</div><div class="muted">requests / 分钟</div></div>
    <div class="metric"><div class="label">预计剩余时间</div><div class="value">{escape(_format_duration(snapshot['eta_seconds']))}</div></div>
    <div class="metric"><div class="label">最近结果写入</div><div class="value" style="font-size:16px">{escape(_format_timestamp(snapshot['last_result_at']))}</div><div class="muted">距今 {escape(_format_duration(snapshot['seconds_since_result']))}</div></div>
    <div class="metric"><div class="label">页面生成时间</div><div class="value" style="font-size:16px">{escape(_format_timestamp(snapshot['generated_at']))}</div><div class="muted">每 {refresh_seconds} 秒更新</div></div>
  </section>
  <section class="panel"><h2>写入一致性</h2><table>
    <tr><th>Response 行 / 唯一 request ID</th><td>{snapshot['response_rows']:,} / {snapshot['response_unique_request_ids']:,}</td></tr>
    <tr><th>Audit 行 / 唯一 request ID</th><td>{snapshot['audit_rows']:,} / {snapshot['audit_unique_request_ids']:,}</td></tr>
    <tr><th>仅存在于 response / audit</th><td>{snapshot['response_only_request_ids']:,} / {snapshot['audit_only_request_ids']:,}</td></tr>
    <tr><th>无效 JSONL / 重复 request ID</th><td>{snapshot['invalid_jsonl_rows']:,} / {snapshot['duplicate_request_ids']:,}</td></tr>
  </table></section>
  <section class="grid panel">
    <div class="metric"><div class="label">Prompt tokens</div><div class="value">{usage['prompt_tokens']:,}</div></div>
    <div class="metric"><div class="label">Completion tokens</div><div class="value">{usage['completion_tokens']:,}</div></div>
    <div class="metric"><div class="label">Total tokens</div><div class="value">{usage['total_tokens']:,}</div></div>
    <div class="metric"><div class="label">停滞判定阈值</div><div class="value">{snapshot['stalled_after_seconds']:,} 秒</div></div>
  </section>
  <section class="panel"><h2>诊断</h2><ul>{warning_html}</ul></section>
  <section class="panel"><h2>监测来源</h2><table>
    <tr><th>Responses</th><td><code>{escape(snapshot['responses_path'])}</code></td></tr>
    <tr><th>Audit</th><td><code>{escape(snapshot['audit_path'])}</code></td></tr>
  </table></section>
  <footer>页面不包含临床正文、实体内容、API key 或 request ID。状态来自追加写入的 response/audit 文件；“可能停滞”是无新增结果的提示，不等同于进程存活证明。</footer>
</main>
<script>
  const generatedAt = {generated_at_ms};
  const staleAfterMs = Math.max({refresh_seconds} * 3000, 30000);
  function updateMonitorHeartbeat() {{
    document.getElementById('monitor-stale').style.display = Date.now() - generatedAt > staleAfterMs ? 'block' : 'none';
  }}
  updateMonitorHeartbeat();
  setInterval(updateMonitorHeartbeat, 1000);
</script>
</body>
</html>
"""


def _write_html_atomically(path: Path, content: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        f".{output_path.name}.{os.getpid()}.temporary"
    )
    try:
        temporary_path.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary_path, output_path)
    except PermissionError as error:
        raise ApiMonitorError(
            "API_MONITOR_OUTPUT_PERMISSION_DENIED", str(output_path)
        ) from error
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def default_monitor_html_path(audit_path: Path) -> Path:
    """Derive a stable dashboard name from the success-audit path."""

    path = Path(audit_path)
    stem = path.stem
    if stem.endswith("_api_audit"):
        stem = stem[: -len("_api_audit")]
    return path.with_name(f"{stem}_monitor.html")


def format_monitor_console_line(snapshot: dict[str, Any]) -> str:
    """Format one payload-free heartbeat for an interactive terminal."""

    return (
        "[监测器：不发起 API 调用] "
        f"{_format_timestamp(float(snapshot['generated_at']))} | "
        f"{snapshot['stage_label']} | {snapshot['status_label']} | "
        f"完成 {snapshot['completed_requests']:,}/{snapshot['expected_requests']:,} "
        f"({float(snapshot['completion_percentage']):.2f}%) | "
        f"剩余 {snapshot['remaining_requests']:,} | "
        f"速度 {float(snapshot['requests_per_minute']):.2f} requests/分钟 | "
        f"HTML {snapshot['output_html_path']}"
    )


def monitor_api_html(
    responses_path: Path,
    audit_path: Path,
    output_html_path: Path | None = None,
    *,
    expected_requests: int,
    stage_label: str,
    refresh_seconds: int = 10,
    stalled_after_seconds: int = 300,
    watch: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    console_reporter: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Write one dashboard or continuously refresh it until Ctrl+C."""

    resolved_output_html_path = (
        Path(output_html_path)
        if output_html_path is not None
        else default_monitor_html_path(Path(audit_path))
    )
    session = ApiMonitorSession(
        responses_path=responses_path,
        audit_path=audit_path,
        expected_requests=expected_requests,
        stage_label=stage_label,
        refresh_seconds=refresh_seconds,
        stalled_after_seconds=stalled_after_seconds,
    )
    last_snapshot: dict[str, Any] | None = None
    try:
        while True:
            last_snapshot = session.sample()
            last_snapshot["output_html_path"] = str(resolved_output_html_path)
            _write_html_atomically(
                resolved_output_html_path, render_monitor_html(last_snapshot)
            )
            if console_reporter is not None:
                console_reporter(format_monitor_console_line(last_snapshot))
            if not watch:
                return last_snapshot
            sleep(refresh_seconds)
    except KeyboardInterrupt:
        if last_snapshot is None:
            last_snapshot = session.sample()
            last_snapshot["output_html_path"] = str(resolved_output_html_path)
            _write_html_atomically(
                resolved_output_html_path, render_monitor_html(last_snapshot)
            )
        return {**last_snapshot, "watch_stopped_by_user": True}
