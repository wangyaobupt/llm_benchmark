#!/usr/bin/env python3
"""生成项目流程图的 draw.io 文件。

输出 docs/项目流程图.drawio，可在 draw.io 桌面版或 app.diagrams.net 打开编辑。
"""

from __future__ import annotations

import html
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "项目流程图.drawio"

# 状态颜色: (fillColor, strokeColor)
C = {
    "data":  ("#d1ecf1", "#17a2b8"),   # 青色 - 数据源
    "done":  ("#d4edda", "#28a745"),   # 绿色 - 已完成
    "block": ("#f8d7da", "#dc3545"),   # 红色 - 阻塞
    "todo":  ("#fff3cd", "#ffc107"),   # 黄色 - 待办
    "group": ("#f8f9fa", "#adb5bd"),   # 灰色 - 容器
    "eval":  ("#e2d9f3", "#6f42c1"),   # 紫色 - 评估
}


def _node(nid: str, label: str, x: float, y: float, w: float, h: float,
          status: str, *, fontsize: int = 11, bold: bool = True) -> str:
    fill, stroke = C[status]
    style = (
        f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
        f"verticalAlign=middle;align=center;fontSize={fontsize};"
        f"fontStyle={1 if bold else 0};fontColor=#212529;"
    )
    safe = html.escape(label).replace("\n", "&#10;")
    return (
        f'<mxCell id="{nid}" value="{safe}" style="{style}" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
        f"</mxCell>"
    )


def _group(gid: str, label: str, x: float, y: float, w: float, h: float) -> str:
    fill, stroke = C["group"]
    style = (
        f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
        f"verticalAlign=top;align=left;fontSize=13;fontStyle=1;"
        f"fontColor=#495057;dashed=1;spacingTop=6;spacingLeft=10;"
        f"container=0;collapsible=0;"
    )
    safe = html.escape(label)
    return (
        f'<mxCell id="{gid}" value="{safe}" style="{style}" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
        f"</mxCell>"
    )


def _edge(eid: str, src: str, tgt: str, *, color: str = "#495057",
          dashed: bool = False, width: int = 2) -> str:
    d = "1" if dashed else "0"
    style = (
        f"edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;html=1;"
        f"strokeColor={color};strokeWidth={width};dashed={d};"
        f"endArrow=classic;endFill=1;"
    )
    return (
        f'<mxCell id="{eid}" style="{style}" edge="1" parent="1" '
        f'source="{src}" target="{tgt}">'
        f'<mxGeometry relative="1" as="geometry"/>'
        f"</mxCell>"
    )


def build() -> str:
    nodes: list[str] = []
    edges: list[str] = []

    # 数据源
    nodes.append(_node(
        "raw",
        "MIMIC 原始数据\nIV 3.1 + Note 2.2 + ED 2.2\nSHA 全通过",
        360, 40, 300, 64, "data", fontsize=12,
    ))

    # 子系统 B
    nodes.append(_group(
        "grpB", "子系统 B · Episode 聚合底座（留作多模态扩展）",
        40, 160, 290, 180,
    ))
    nodes.append(_node(
        "b1", "41 表 → 9 张 parquet\n768K episode / 48.9 GB\n✅ 已完成",
        60, 200, 250, 56, "done", fontsize=11,
    ))
    nodes.append(_node(
        "b2", "删除 154 个负时长 episode\nSQL 已改 / 脚本待运行\n⚠️ 可并行收尾",
        60, 272, 250, 56, "todo", fontsize=11,
    ))

    # 子系统 A 主线
    nodes.append(_group(
        "grpA", "子系统 A · RWD Benchmark 评测数据集（主线）",
        370, 160, 530, 560,
    ))
    main_steps = [
        ("a1", "① 抽取 extraction\nrwd_benchmark_visits.csv  11687×17", "done"),
        ("a2", "② 清洗 cleaning\n4 字段 LLM 实体抽取 → JSON 数组", "done"),
        ("a3", "③ 标准化 standardization  ← P0 阻塞\nrwd_standardization/ 代码缺失，spec+测试就绪", "block"),
        ("t1", "T1  修复 discharge_record 100% 空  ← P0 阻塞\n排查 discharge.py Follow-up 章节正则", "block"),
        ("t4", "T4  补齐维度 4 转诊科室数据来源\n确认 services/transfers 是否需新增抽取", "todo"),
        ("a4", "④ MCQ 题目生成  ← P0 阻塞\n题型1 有 Stage 0-10 设计 | 题型 2-5 仅题型规范", "block"),
    ]
    y = 200
    for nid, label, status in main_steps:
        nodes.append(_node(nid, label, 390, y, 490, 48, status, fontsize=11))
        y += 72

    # 五个维度
    dims = [
        ("d1", "维度 1\n检查检验选择", "✅ 有数据"),
        ("d2", "维度 2\n临床诊断", "✅ 有数据"),
        ("d3", "维度 3\n治疗处置", "⚠️ 部分"),
        ("d4", "维度 4\n转诊科室", "❌ 缺口"),
        ("d5", "维度 5\n离院指导", "❌ 100%空"),
    ]
    dx = 40
    for did, name, tag in dims:
        status = "done" if "✅" in tag else ("block" if "❌" in tag else "todo")
        nodes.append(_node(did, f"{name}\n{tag}", dx, 760, 94, 62,
                           status, fontsize=10))
        dx += 106

    # 评估部分
    nodes.append(_group(
        "grpE", "第二部分 · 五个维度评估 LLM",
        40, 870, 560, 130,
    ))
    nodes.append(_node(
        "e1", "T7  评估框架设计\n脚本+指标+LLM接入\nsubject_id 级划分防泄漏",
        60, 910, 160, 70, "eval", fontsize=10,
    ))
    nodes.append(_node(
        "e2", "T8  五维度逐一评测\n含人工/自动审题门禁",
        240, 910, 160, 70, "eval", fontsize=10,
    ))
    nodes.append(_node(
        "e3", "T9  结果分析与报告",
        420, 910, 160, 70, "eval", fontsize=10,
    ))

    # 边
    edges.append(_edge("e_raw_a", "raw", "a1", color="#17a2b8"))
    edges.append(_edge("e_raw_b", "raw", "b1", color="#17a2b8"))
    edges.append(_edge("e_b1_b2", "b1", "b2", color="#28a745", dashed=True))
    for i in range(len(main_steps) - 1):
        s, t = main_steps[i][0], main_steps[i + 1][0]
        col = "#dc3545" if "block" in (main_steps[i][2], main_steps[i + 1][2]) else "#495057"
        edges.append(_edge(f"e_{s}_{t}", s, t, color=col))
    for did, _, _ in dims:
        edges.append(_edge(f"e_a4_{did}", "a4", did, color="#6c757d", width=1))
    edges.append(_edge("e_dims_eval", "d3", "e2", color="#6f42c1"))
    edges.append(_edge("e_e1_e2", "e1", "e2", color="#6f42c1"))
    edges.append(_edge("e_e2_e3", "e2", "e3", color="#6f42c1"))

    body = "\n".join(nodes + edges)
    return (
        '<mxfile host="app.diagrams.net" type="device">\n'
        '  <diagram id="flow" name="项目流程图">\n'
        '    <mxGraphModel dx="1422" dy="757" grid="1" gridSize="10" '
        'guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
        'page="1" pageScale="1" pageWidth="1169" pageHeight="1654" '
        'math="0" shadow="0">\n'
        '      <root>\n'
        '        <mxCell id="0"/>\n'
        '        <mxCell id="1" parent="0"/>\n'
        f'{body}\n'
        '      </root>\n'
        '    </mxGraphModel>\n'
        '  </diagram>\n'
        '</mxfile>\n'
    )


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"written: {OUT}  ({OUT.stat().st_size} bytes)")
