"""Render compiled MCQ visit NER as a local, span-highlighted HTML report."""

from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
from typing import Any, Mapping

from data_pipeline.mcq_visit_extract.atomic import read_jsonl
from data_pipeline.mcq_visit_ner.pipeline import known_surfaces_for_visit, mask_structured_surfaces
from data_pipeline.mcq_visit_standardize.io import iter_json_array


ENTITY_LABELS = {
    "symptom_or_sign": "症状/体征",
    "clinical_problem": "临床问题",
    "imaging_finding": "影像发现",
    "physical_exam_finding": "体格检查",
    "anatomical_site": "解剖部位",
    "procedure_or_test": "操作/检查",
    "device": "设备",
    "medication_or_substance": "药物/物质",
    "measurement": "测量值",
    "temporal_expression": "时间表达",
}
ENTITY_CLASS = {
    key: f"entity-{index}"
    for index, key in enumerate(ENTITY_LABELS)
}


def _read_compiled(path: Path) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in read_jsonl(path):
        hadm_id = str(row.get("hadm_id") or "")
        if hadm_id:
            grouped.setdefault(hadm_id, []).append(row)
    return grouped


def _read_visits(path: Path, target_hadm: set[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for visit in iter_json_array(path):
        hadm_id = str(visit.get("hadm_id") or "")
        if hadm_id in target_hadm:
            result[hadm_id] = dict(visit)
            if len(result) == len(target_hadm):
                break
    return result


def _mention_title(mention: Mapping[str, Any]) -> str:
    entity_type = str(mention.get("entity_type") or "unknown")
    details = [ENTITY_LABELS.get(entity_type, entity_type)]
    for key, label in (
        ("assertion", "断言"),
        ("temporality", "时态"),
        ("experiencer", "体验者"),
        ("laterality", "侧别"),
        ("severity", "严重度"),
        ("trend", "趋势"),
    ):
        value = mention.get(key)
        if value and value not in {"present", "current", "patient", "not_stated"}:
            details.append(f"{label}: {value}")
    return " | ".join(details)


def _span_start(item: Mapping[str, Any]) -> int:
    return int(item.get("field_span_start", item.get("start", -1)))


def _span_end(item: Mapping[str, Any]) -> int:
    return int(item.get("field_span_end", item.get("end", -1)))


def _render_field(
    text: str,
    mentions: list[dict[str, Any]],
    known_spans: list[dict[str, Any]],
) -> str:
    points = {0, len(text)}
    intervals: list[tuple[int, int, str, str]] = []
    for mention in mentions:
        start, end = _span_start(mention), _span_end(mention)
        surface = str(mention.get("surface_text") or "")
        if not (0 <= start < end <= len(text)):
            raise ValueError(f"mention span out of bounds: {start}:{end}")
        if text[start:end] != surface:
            raise ValueError(f"mention surface mismatch at {start}:{end}")
        points.update((start, end))
        intervals.append((start, end, "mention", _mention_title(mention)))
    for known in known_spans:
        start, end = int(known["start"]), int(known["end"])
        if not (0 <= start < end <= len(text)):
            raise ValueError(f"known span out of bounds: {start}:{end}")
        points.update((start, end))
        intervals.append((start, end, "known", "已结构化，跳过本次 NER"))

    ordered = sorted(points)
    pieces: list[str] = []
    for left, right in zip(ordered, ordered[1:]):
        if left == right:
            continue
        active = [item for item in intervals if item[0] <= left and right <= item[1]]
        content = escape(text[left:right])
        if not active:
            pieces.append(content)
            continue
        mentions_active = [item for item in active if item[2] == "mention"]
        selected = mentions_active or active
        classes = []
        if mentions_active:
            for mention in mentions:
                if _span_start(mention) <= left and right <= _span_end(mention):
                    classes.append(ENTITY_CLASS.get(str(mention.get("entity_type")), "entity-unknown"))
        else:
            classes.append("known-structured")
        title = " || ".join(dict.fromkeys(item[3] for item in selected))
        pieces.append(
            f'<span class="highlight {" ".join(dict.fromkeys(classes))}" '
            f'title="{escape(title, quote=True)}">{content}</span>'
        )
    return "".join(pieces)


def _render_visit(hadm_id: str, visit: Mapping[str, Any], rows: list[dict[str, Any]]) -> str:
    mentions_by_field: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for mention in row.get("mentions") or []:
            field = str(mention.get("field") or row.get("field") or "discharge_note_full")
            mentions_by_field.setdefault(field, []).append(mention)
    known_by_field: dict[str, list[dict[str, Any]]] = {}
    for field in mentions_by_field:
        text = visit.get(field)
        if isinstance(text, str):
            _, spans, _ = mask_structured_surfaces(text, known_surfaces_for_visit(visit))
            known_by_field[field] = spans

    counts: dict[str, int] = {}
    for mentions in mentions_by_field.values():
        for mention in mentions:
            key = str(mention.get("entity_type") or "unknown")
            counts[key] = counts.get(key, 0) + 1
    count_text = "、".join(
        f"{ENTITY_LABELS.get(key, key)} {value}" for key, value in sorted(counts.items())
    ) or "无实体"

    fields: list[str] = []
    for field in sorted(mentions_by_field):
        text = visit.get(field)
        if not isinstance(text, str) or not text:
            continue
        fields.append(
            f'<section class="field"><h3>{escape(field)}</h3>'
            f'<div class="note">{_render_field(text, mentions_by_field[field], known_by_field.get(field, []))}</div></section>'
        )
    return (
        f'<article class="visit"><h2>住院号 {escape(hadm_id)}</h2>'
        f'<div class="summary">NER 实体数：{sum(counts.values())}；{escape(count_text)}</div>'
        + "".join(fields)
        + "</article>"
    )


def render(input_path: Path, compiled_path: Path, output_path: Path) -> dict[str, int]:
    compiled = _read_compiled(compiled_path)
    visits = _read_visits(input_path, set(compiled))
    missing = set(compiled) - set(visits)
    if missing:
        raise ValueError(f"source visits missing for {len(missing)} hadm_id(s)")
    articles = [_render_visit(hadm_id, visits[hadm_id], compiled[hadm_id]) for hadm_id in sorted(compiled)]
    legend = "".join(
        f'<span class="legend-item"><i class="highlight {ENTITY_CLASS[key]}"></i>{escape(label)}</span>'
        for key, label in ENTITY_LABELS.items()
    )
    html = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>MCQ Visit NER 高亮结果</title>
<style>
body {{ margin: 0 auto; max-width: 1500px; padding: 24px; color: #202124; font: 15px/1.65 Segoe UI, Microsoft YaHei, sans-serif; background: #f6f7f9; }}
h1 {{ margin-bottom: 6px; }} .meta {{ color: #5f6368; margin-bottom: 18px; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 8px 14px; padding: 12px; background: white; border-radius: 8px; margin-bottom: 18px; }}
.legend-item {{ display: inline-flex; align-items: center; gap: 5px; }}
.highlight {{ border-radius: 3px; padding: 1px 2px; cursor: help; box-shadow: inset 0 -2px 0 rgba(0,0,0,.16); }}
.known-structured {{ background: #e5e7eb; color: #4b5563; }}
.entity-0 {{ background: #ffd6d6; }} .entity-1 {{ background: #ffe7b3; }} .entity-2 {{ background: #d6e8ff; }}
.entity-3 {{ background: #d9f5d0; }} .entity-4 {{ background: #eadcff; }} .entity-5 {{ background: #cceff2; }}
.entity-6 {{ background: #f4d4f4; }} .entity-7 {{ background: #ffe0c2; }} .entity-8 {{ background: #dce7ff; }}
.entity-9 {{ background: #e7e7e7; }} .entity-unknown {{ background: #f0f0f0; }}
.visit {{ background: white; border-radius: 10px; padding: 18px 22px; margin: 18px 0; box-shadow: 0 1px 5px rgba(0,0,0,.08); }}
.visit h2 {{ margin: 0 0 4px; }} .summary {{ color: #5f6368; margin-bottom: 14px; }}
.field {{ margin-top: 14px; }} .field h3 {{ font-size: 15px; color: #374151; margin: 0 0 5px; }}
.note {{ white-space: pre-wrap; overflow-wrap: anywhere; border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px; background: #fff; }}
</style></head><body>
<h1>MCQ Visit NER 高亮结果</h1>
<div class="meta">共 {len(articles)} 例。彩色部分为本次残余 NER 实体；灰色部分为已有结构化字段，本次跳过 NER。鼠标悬停查看属性。</div>
<div class="legend">{legend}<span class="legend-item"><i class="highlight known-structured"></i>已结构化/跳过 NER</span></div>
{"".join(articles)}
</body></html>'''
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return {"visits": len(articles), "mentions": sum(len(row.get("mentions") or []) for rows in compiled.values() for row in rows)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Render MCQ visit NER HTML highlights")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--compiled", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(render(args.input, args.compiled, args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
