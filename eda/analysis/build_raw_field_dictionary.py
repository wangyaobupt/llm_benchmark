from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from data_pipeline.mimic_raw_archive.field_dictionary import (
    build_field_dictionary,
    validate_dictionary,
)


def md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(rows: list[dict[str, Any]]) -> str:
    validate_dictionary(rows)
    counts = Counter(row["scope"] for row in rows)
    modules = Counter(row["module"] for row in rows if row["scope"] == "archive")
    lines = [
        "# MIMIC 单次住院原始归档逐字段数据字典",
        "",
        "> 本文档由实际归档契约与本地 MIMIC 表结构自动生成。归档表头是覆盖范围的唯一事实源；参考文档负责原始类型和中文释义。任一字段缺少说明时生成过程直接失败。",
        "",
        "## 统计与使用边界",
        "",
        f"- 顶层字段：{counts['top_level']} 个。",
        f"- JSONL 内32张源表字段：{counts['archive']} 个。",
        f"- 外置7张公共字典字段：{counts['external_reference']} 个。",
        f"- JSONL 内模块字段数：HOSP {modules['mimic_iv_hosp']}、ICU {modules['mimic_iv_icu']}、ED {modules['mimic_iv_ed']}、NOTE {modules['mimic_iv_note']}。",
        "- 原始CSV单元格在JSONL中保存为字符串；空单元格写为`null`。`source_type`表示MIMIC源表的逻辑类型，不代表JSON中已经转成数值或日期对象。",
        "- `post_hoc`和`administrative_end`字段不得进入前瞻性决策题干；其他事件仍须同时通过决策时点和可用时点检查。",
        "",
        "## 时间与信息阶段定义",
        "",
        "| 标记 | 定义 |",
        "|---|---|",
        "| `event time` | 事件发生、开始、结束或临床标记时间。 |",
        "| `recorded/available time` | 系统存储、录入或核验时间，用于判断该信息何时真正可见。 |",
        "| `post_hoc` | 出院文书、住院ICD、DRG等住院后验资料。 |",
        "| `administrative_end` | 出院、死亡、出院去向等住院结局。 |",
        "| `identifier` | 只用于连接、去重和审计，不作为临床证据。 |",
        "",
    ]
    for scope, heading in (
        ("top_level", "顶层字段"),
        ("archive", "JSONL内32张源表字段"),
        ("external_reference", "外置7张公共字典字段"),
    ):
        lines.extend([
            f"## {heading}", "",
            "| JSON路径 | JSON存储类型 | 源类型 | 源约束 | 中文说明 | 键角色 | 时间语义 | 信息阶段 | Benchmark使用限制 |",
            "|---|---|---|---|---|---|---|---|---|",
        ])
        for row in rows:
            if row["scope"] != scope:
                continue
            lines.append("| " + " | ".join(md(row[key]) for key in (
                "json_path", "archive_type", "source_type", "source_constraint",
                "description_zh", "key_role", "time_semantics", "information_phase",
                "benchmark_restriction",
            )) + " |")
        lines.append("")
    lines.extend([
        "## 明确不进入JSONL的表", "",
        "- `mimic_iv_icu.chartevents`：高频床旁监护、护理观察与设备参数，按当前数据边界整表排除。",
        "- `mimic_iv_hosp.omr`：没有原生`hadm_id`，禁止依赖时间窗口推断归属住院。",
        "",
    ])
    return "\n".join(lines)


def build_outputs(reference_root: Path, markdown_output: Path, json_output: Path) -> None:
    rows = build_field_dictionary(reference_root)
    validate_dictionary(rows)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(render_markdown(rows), encoding="utf-8")
    json_output.write_text(
        json.dumps({"schema": "mimic_raw_field_dictionary", "version": "1.0.0", "fields": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成原始住院归档逐字段数据字典")
    parser.add_argument("--reference-root", type=Path, default=Path("docs/reference/mimic_reference"))
    parser.add_argument("--markdown-output", type=Path, default=Path("docs/design/MIMIC 单次住院原始归档逐字段数据字典.md"))
    parser.add_argument("--json-output", type=Path, default=Path("docs/reports/mimic-admission-raw-field-dictionary.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_outputs(args.reference_root, args.markdown_output, args.json_output)
    print(args.markdown_output.resolve())
    print(args.json_output.resolve())


if __name__ == "__main__":
    main()
