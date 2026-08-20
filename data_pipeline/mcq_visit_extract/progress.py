"""Heartbeat file so the HTML monitor can show the live stage without reading visits."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .atomic import atomic_write_json

ACTIVITY_NAME = "monitor_activity.json"

PHASE_LABELS: dict[str, str] = {
    "source_validation": "源表校验",
    "funnel_n1": "漏斗 · 人口统计",
    "funnel_n2": "漏斗 · 主诊断",
    "funnel_ds": "漏斗 · 出院小结",
    "selection": "锁定抽样清单",
    "staging": "源表投影",
    "reference": "字典表",
    "assemble": "Visit 分片组装",
    "publish": "写出 csv / json",
    "complete": "已完成",
    "failed": "失败",
}


def write_progress(
    output_dir: Path,
    *,
    phase: str,
    detail: str = "",
    **extra: Any,
) -> None:
    payload = {
        "phase": phase,
        "phase_label": PHASE_LABELS.get(phase, phase),
        "detail": detail,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    payload.update(extra)
    atomic_write_json(output_dir / ACTIVITY_NAME, payload)
