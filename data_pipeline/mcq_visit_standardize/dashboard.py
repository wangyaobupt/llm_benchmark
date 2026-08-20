"""Aggregate standardize outputs into a local HTML dashboard. No patient text."""

from __future__ import annotations

import argparse
import html
import json
import webbrowser
from collections import Counter
from pathlib import Path
from typing import Any

from .io import iter_json_array
from .synonyms import load_jsonl

AGE_BINS: tuple[tuple[str, int | None, int | None], ...] = (
    ("18–39", 18, 39),
    ("40–49", 40, 49),
    ("50–59", 50, 59),
    ("60–69", 60, 69),
    ("70–79", 70, 79),
    ("80+", 80, None),
)


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 2) if whole else 0.0


def _status_bucket(status: str | None) -> str:
    text = str(status or "")
    if text.startswith("mapped"):
        return "mapped"
    if text in {"not_applicable", "n/a"}:
        return "not_applicable"
    return "unresolved"


def _age_bin(age: Any) -> str:
    try:
        value = int(age)
    except (TypeError, ValueError):
        return "unknown"
    for label, low, high in AGE_BINS:
        if high is None and value >= (low or 0):
            return label
        if low is not None and high is not None and low <= value <= high:
            return label
    return "unknown"


def _top(counter: Counter[str], limit: int = 20) -> list[dict[str, Any]]:
    total = sum(counter.values())
    rows = []
    for name, count in counter.most_common(limit):
        if not name:
            continue
        rows.append({"name": name, "count": int(count), "pct": _pct(int(count), total)})
    return rows


def _mix(counter: Counter[str]) -> list[dict[str, Any]]:
    total = sum(counter.values())
    return [
        {"name": name, "count": int(count), "pct": _pct(int(count), total)}
        for name, count in counter.most_common()
    ]


def _count_status(items: list[dict[str, Any]], status_key: str = "status") -> Counter[str]:
    counter: Counter[str] = Counter()
    for item in items:
        counter[_status_bucket(item.get(status_key))] += 1
    return counter


def compute_stats(
    visits_path: Path,
    *,
    acceptance: dict[str, Any] | None = None,
    synonyms: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sex: Counter[str] = Counter()
    age: Counter[str] = Counter()
    admission: Counter[str] = Counter()
    cc_status: Counter[str] = Counter()
    cc_polarity: Counter[str] = Counter()
    cc_names: Counter[str] = Counter()
    ed_status: Counter[str] = Counter()
    ed_names: Counter[str] = Counter()
    exam_status: Counter[str] = Counter()
    exam_names: Counter[str] = Counter()
    lab_unit_status: Counter[str] = Counter()
    lab_names: Counter[str] = Counter()
    lab_charttime: Counter[str] = Counter()
    lab_tests = 0
    lab_results = 0
    drug_status: Counter[str] = Counter()
    drug_names: Counter[str] = Counter()
    allergy_status: Counter[str] = Counter()
    rhythm_status: Counter[str] = Counter()
    visits = 0
    visits_with_cc = 0
    visits_with_mapped_cc = 0
    temperature_present = 0
    for visit in iter_json_array(visits_path):
        visits += 1
        sex[str(visit.get("sex") or "unknown")] += 1
        age[_age_bin(visit.get("age_at_encounter"))] += 1
        admission[str(visit.get("admission_type") or "unknown")] += 1
        if visit.get("temperature") is not None:
            temperature_present += 1
        cc = visit.get("chief_complaint_concepts") or []
        if cc:
            visits_with_cc += 1
        if any(str(item.get("status") or "").startswith("mapped") for item in cc):
            visits_with_mapped_cc += 1
        for item in cc:
            cc_status[_status_bucket(item.get("status"))] += 1
            cc_polarity[str(item.get("polarity") or "unknown")] += 1
            name = item.get("standard")
            if name:
                cc_names[str(name)] += 1
        for item in visit.get("ed_chief_complaint_concepts") or []:
            ed_status[_status_bucket(item.get("status"))] += 1
            name = item.get("standard")
            if name:
                ed_names[str(name)] += 1
        investigations = visit.get("investigations_normalized") or {}
        for item in investigations.get("radiology") or []:
            exam_status[_status_bucket(item.get("status"))] += 1
            name = item.get("standard_exam_name")
            if name:
                exam_names[str(name)] += 1
        for item in investigations.get("laboratory") or []:
            lab_tests += 1
            name = item.get("standard_test_name") or item.get("source_label") or item.get("label")
            if name:
                lab_names[str(name)] += 1
            for row in item.get("results") or []:
                lab_unit_status[_status_bucket(row.get("unit_status"))] += 1
        source_labs = (visit.get("investigations") or {}).get("laboratory") or []
        if source_labs:
            for item in source_labs:
                for row in item.get("results") or []:
                    lab_results += 1
                    if str(row.get("charttime") or "").strip():
                        lab_charttime["有 charttime"] += 1
                    else:
                        lab_charttime["无 charttime"] += 1
        else:
            for item in investigations.get("laboratory") or []:
                for row in item.get("results") or []:
                    lab_results += 1
                    if str(row.get("charttime") or "").strip():
                        lab_charttime["有 charttime"] += 1
                    else:
                        lab_charttime["无 charttime"] += 1
        for item in visit.get("medications_normalized") or []:
            drug_status[_status_bucket(item.get("status"))] += 1
            for name in item.get("standard_ingredients") or []:
                drug_names[str(name)] += 1
        for item in visit.get("allergy_concepts") or []:
            allergy_status[_status_bucket(item.get("status"))] += 1
        rhythm = visit.get("standard_rhythm") or {}
        if isinstance(rhythm, dict) and (rhythm.get("status") or rhythm.get("standard")):
            rhythm_status[_status_bucket(rhythm.get("status"))] += 1
        elif visit.get("rhythm"):
            rhythm_status["unresolved"] += 1

    synonym_domain = Counter(str(row.get("domain") or "unknown") for row in (synonyms or []))
    synonym_concepts: dict[str, set[str]] = {}
    for row in synonyms or []:
        domain = str(row.get("domain") or "unknown")
        concept = str(row.get("concept_id") or "")
        synonym_concepts.setdefault(domain, set()).add(concept)
    return {
        "visits": visits,
        "acceptance": acceptance or {},
        "cohort": {
            "sex": _mix(sex),
            "age": _mix(age),
            "admission_type": _mix(admission),
        },
        "chief_complaint": {
            "visits_with_concepts": visits_with_cc,
            "visits_with_mapped": visits_with_mapped_cc,
            "concept_status": _mix(cc_status),
            "polarity": _mix(cc_polarity),
            "top_standards": _top(cc_names, 20),
            "unique_standards": len(cc_names),
        },
        "ed_chief_complaint": {
            "concept_status": _mix(ed_status),
            "top_standards": _top(ed_names, 15),
            "unique_standards": len(ed_names),
        },
        "radiology": {
            "status": _mix(exam_status),
            "top_standards": _top(exam_names, 20),
            "unique_standards": len(exam_names),
        },
        "laboratory": {
            "tests": lab_tests,
            "results": lab_results,
            "unique_names": len(lab_names),
            "top_names": _top(lab_names, 20),
            "charttime": _mix(lab_charttime),
            "units": {"status": _mix(lab_unit_status)},
        },
        "medications": {
            "status": _mix(drug_status),
            "top_ingredients": _top(drug_names, 15),
            "unique_ingredients": len(drug_names),
        },
        "allergies": {"status": _mix(allergy_status)},
        "rhythm": {"status": _mix(rhythm_status)},
        "temperature_present": temperature_present,
        "synonyms": {
            "rows": sum(synonym_domain.values()),
            "by_domain": [
                {
                    "name": name,
                    "count": int(count),
                    "concepts": len(synonym_concepts.get(name, set())),
                    "pct": _pct(int(count), sum(synonym_domain.values())),
                }
                for name, count in synonym_domain.most_common()
            ],
        },
    }


def _mix_value(items: list[dict[str, Any]], name: str) -> int:
    for item in items:
        if item.get("name") == name:
            return int(item.get("count") or 0)
    return 0


def _rate(items: list[dict[str, Any]]) -> float:
    mapped = _mix_value(items, "mapped")
    unresolved = _mix_value(items, "unresolved")
    applicable = mapped + unresolved
    return _pct(mapped, applicable)


def _hbar(rows: list[dict[str, Any]], color: str = "#69a7ff") -> str:
    if not rows:
        return '<div class="muted">无数据</div>'
    peak = max(int(row["count"]) for row in rows) or 1
    blocks = []
    for row in rows:
        width = 100.0 * int(row["count"]) / peak
        name = html.escape(str(row["name"]))
        blocks.append(
            "<div class='hbar'>"
            f"<span class='hlab' title='{name}'>{name}</span>"
            f"<span class='track'><i style='width:{width:.2f}%;background:{color}'></i></span>"
            f"<span class='hn'>{int(row['count']):,}</span>"
            "</div>"
        )
    return "".join(blocks)


def _donut(items: list[dict[str, Any]], colors: dict[str, str]) -> str:
    if not items:
        return ""
    stops = []
    cursor = 0.0
    legend = []
    for item in items:
        name = str(item["name"])
        pct = float(item.get("pct") or 0)
        color = colors.get(name, "#8b97b3")
        start = cursor
        cursor += pct
        stops.append(f"{color} {start:.2f}% {cursor:.2f}%")
        legend.append(
            f"<span class='leg'><i style='background:{color}'></i>"
            f"{html.escape(name)} {item['count']:,} ({pct:.1f}%)</span>"
        )
    gradient = ", ".join(stops) if stops else "#25304a 0 100%"
    return (
        f"<div class='donut' style='background:conic-gradient({gradient})'></div>"
        f"<div class='legend'>{''.join(legend)}</div>"
    )


def render_html(stats: dict[str, Any]) -> str:
    acc = stats.get("acceptance") or {}
    cc = stats["chief_complaint"]
    colors = {
        "mapped": "#50d890",
        "unresolved": "#ff718b",
        "not_applicable": "#8b97b3",
        "有 charttime": "#50d890",
        "无 charttime": "#ff718b",
        "M": "#69a7ff",
        "F": "#c3a6ff",
        "unknown": "#8b97b3",
    }
    mapped_rate = acc.get("chief_complaint_mapped_rate")
    mapped_pct = f"{float(mapped_rate) * 100:.1f}%" if mapped_rate is not None else "—"
    exam_rate = _rate(stats["radiology"]["status"])
    drug_rate = _rate(stats["medications"]["status"])
    allergy_rate = _rate(stats["allergies"]["status"])
    labs = stats["laboratory"]
    charttime_have = _mix_value(labs["charttime"], "有 charttime")
    charttime_rate = _pct(charttime_have, int(labs["results"] or 0))
    queue = acc.get("review_queue_rows")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>出题 Visit 标准化结果 · 10,000 例</title>
<style>
:root{{color-scheme:dark;--bg:#0b1020;--card:#151c30;--line:#293553;--text:#edf2ff;--muted:#91a0bf;--ok:#50d890;--run:#69a7ff;--bad:#ff718b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,"Microsoft YaHei",sans-serif}}
main{{max-width:1280px;margin:auto;padding:28px 22px 48px}}
h1{{margin:0 0 6px;font-size:26px}}h2{{margin:0 0 12px;font-size:17px}}
.muted{{color:var(--muted);font-size:13px;line-height:1.55}}
.badge{{display:inline-block;padding:6px 10px;border-radius:999px;background:#263450;margin-left:8px;font-size:12px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}}
.value{{font-size:26px;font-weight:700;margin-top:6px}}.label{{color:var(--muted);font-size:12px}}
.panel{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin-top:14px}}
.two{{display:grid;grid-template-columns:280px 1fr;gap:22px;align-items:center}}
.donut{{width:160px;height:160px;border-radius:50%;margin:8px auto;background:#25304a}}
.legend{{display:flex;flex-direction:column;gap:6px;font-size:13px}}
.leg i{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px}}
.hbar{{display:grid;grid-template-columns:220px 1fr 64px;gap:8px;align-items:center;margin:5px 0;font-size:12px}}
.hlab{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#c9d4ee}}
.track{{height:9px;background:#25304a;border-radius:99px;overflow:hidden}}
.track>i{{display:block;height:100%;border-radius:99px}}
.hn{{text-align:right;color:var(--muted)}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{text-align:left;padding:8px;border-bottom:1px solid var(--line)}}
th{{color:var(--muted)}}
.warn{{color:#e6c07b}}
@media(max-width:900px){{.grid,.two{{grid-template-columns:1fr}}.hbar{{grid-template-columns:1fr 1fr}}}}
</style></head>
<body><main>
<div>
  <h1>出题 Visit 标准化结果<span class="badge">exploratory_unreviewed · gold = 0</span></h1>
  <div class="muted">10,000 例随机住院 · 映射 {html.escape(str(acc.get('mapping_version') or ''))} · 不含病历原文 · 非正式金标准</div>
</div>
<div class="grid">
  <div class="card"><div class="label">住院数 / 唯一住院</div><div class="value">{stats['visits']:,}</div></div>
  <div class="card"><div class="label">主诉概念 mapped</div><div class="value">{mapped_pct}</div><div class="muted">{acc.get('chief_complaint_mapped'):,} / {acc.get('chief_complaint_concepts'):,}</div></div>
  <div class="card"><div class="label">影像检查 mapped</div><div class="value">{exam_rate:.1f}%</div></div>
  <div class="card"><div class="label">审核队列</div><div class="value">{0 if queue is None else int(queue):,}</div></div>
  <div class="card"><div class="label">药物 mapped</div><div class="value">{drug_rate:.1f}%</div></div>
  <div class="card"><div class="label">过敏 mapped</div><div class="value">{allergy_rate:.1f}%</div></div>
  <div class="card"><div class="label">体温 °F→°C 可逆</div><div class="value">{acc.get('temperature_reversible') or 0:,}</div><div class="muted">有体温 {stats['temperature_present']:,}</div></div>
  <div class="card"><div class="label">同义词表面写法</div><div class="value">{stats['synonyms']['rows']:,}</div><div class="muted">已合并同类项</div></div>
  <div class="card"><div class="label">化验结果有 charttime</div><div class="value">{charttime_rate:.1f}%</div><div class="muted">{charttime_have:,} / {labs['results']:,} 条结果</div></div>
  <div class="card"><div class="label">化验项目种类</div><div class="value">{labs['unique_names']:,}</div><div class="muted">{labs['tests']:,} 条项目（按住院计）</div></div>
</div>
<div class="panel">
  <h2>队列构成</h2>
  <div class="two">
    <div>{_donut(stats['cohort']['sex'], colors)}</div>
    <div>
      <div class="muted">年龄</div>{_hbar(stats['cohort']['age'], '#c3a6ff')}
      <div class="muted" style="margin-top:14px">入院类型</div>{_hbar(stats['cohort']['admission_type'][:8], '#e6c07b')}
    </div>
  </div>
</div>
<div class="panel">
  <h2>出院小结主诉概念</h2>
  <div class="two">
    <div>{_donut(cc['concept_status'], colors)}</div>
    <div>
      <div class="muted">有主诉概念的住院 {cc['visits_with_concepts']:,} · 至少一条 mapped {cc['visits_with_mapped']:,} · 不重复标准名 {cc['unique_standards']:,}</div>
      <div style="margin-top:10px">{_hbar(cc['top_standards'], '#50d890')}</div>
    </div>
  </div>
</div>
<div class="panel">
  <h2>急诊主诉概念（独立字段）</h2>
  <div class="muted">不重复标准名 {stats['ed_chief_complaint']['unique_standards']:,}</div>
  {_hbar(stats['ed_chief_complaint']['top_standards'], '#69a7ff')}
</div>
<div class="panel">
  <h2>影像检查标准名</h2>
  <div class="two">
    <div>{_donut(stats['radiology']['status'], colors)}</div>
    <div>
      <div class="muted">不重复标准名 {stats['radiology']['unique_standards']:,} · 保留部位/对比剂/投照体位</div>
      {_hbar(stats['radiology']['top_standards'], '#69a7ff')}
    </div>
  </div>
</div>
<div class="panel">
  <h2>化验名称与结果时间</h2>
  <div class="muted">时间是 labevents.charttime（结果记入时间），不是医嘱开具时间。标准化层不改写原 results。</div>
  <div class="two">
    <div>
      <div class="muted">结果是否带 charttime</div>
      {_donut(labs['charttime'], colors)}
    </div>
    <div>
      <div class="muted">化验标准名 Top 20（{labs['unique_names']:,} 种）</div>
      {_hbar(labs['top_names'], '#7ad7f0')}
    </div>
  </div>
</div>
<div class="panel">
  <h2>药物通用名</h2>
  <div class="two">
    <div>{_donut(stats['medications']['status'], colors)}</div>
    <div>
      <div class="muted">不重复成分 {stats['medications']['unique_ingredients']:,} · 商品名/盐型已合并</div>
      {_hbar(stats['medications']['top_ingredients'], '#e6c07b')}
    </div>
  </div>
</div>
<div class="panel">
  <h2>过敏 / 化验单位 / 心律</h2>
  <div class="grid" style="margin:0">
    <div><div class="muted">过敏</div>{_donut(stats['allergies']['status'], colors)}</div>
    <div><div class="muted">化验单位</div>{_donut(labs['units']['status'], colors)}</div>
    <div><div class="muted">心律</div>{_donut(stats['rhythm']['status'], colors)}</div>
    <div></div>
  </div>
</div>
<div class="panel">
  <h2>同义词表：表面写法 vs 概念</h2>
  <table><thead><tr><th>域</th><th>表面写法</th><th>概念数</th><th>压缩</th></tr></thead><tbody>
  {''.join(
      f"<tr><td>{html.escape(row['name'])}</td><td>{row['count']:,}</td><td>{row['concepts']:,}</td>"
      f"<td>{(row['count'] / row['concepts']):.2f}×</td></tr>"
      if row['concepts'] else
      f"<tr><td>{html.escape(row['name'])}</td><td>{row['count']:,}</td><td>0</td><td>—</td></tr>"
      for row in stats['synonyms']['by_domain']
  )}
  </tbody></table>
</div>
<div class="panel muted">
  原 45 列未改写。本页只含聚合计数，不含住院标识、出院小结或主诉原文。
  状态 <span class="warn">exploratory_unreviewed</span>，gold = 0，不能当标准答案键，也不能直接出题。
</div>
</main></body></html>
"""


def write_outputs(stats: dict[str, Any], html_path: Path, json_path: Path) -> None:
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_html(stats), encoding="utf-8")
    json_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build HTML stats dashboard for standardized visits")
    parser.add_argument(
        "--visits",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/random10k_dev20_v1.0.9/visits_standardized.json"),
    )
    parser.add_argument(
        "--acceptance",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/random10k_dev20_v1.0.9/acceptance.json"),
    )
    parser.add_argument(
        "--synonyms",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/reviewed_synonyms.jsonl"),
    )
    parser.add_argument(
        "--output-html",
        type=Path,
        default=Path("docs/reports/mcq-visit-standardize-random10k-dashboard.html"),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("docs/reports/mcq-visit-standardize-random10k-dashboard.json"),
    )
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args(argv)
    acceptance = json.loads(args.acceptance.read_text(encoding="utf-8")) if args.acceptance.is_file() else {}
    synonyms = load_jsonl(args.synonyms) if args.synonyms.is_file() else []
    stats = compute_stats(args.visits, acceptance=acceptance, synonyms=synonyms)
    write_outputs(stats, args.output_html, args.output_json)
    print(f"html={args.output_html} json={args.output_json} visits={stats['visits']}")
    if args.open_browser:
        webbrowser.open(args.output_html.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
