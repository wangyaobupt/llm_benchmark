"""Build a self-contained HTML comparison for complete MCQ mining runs."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .catalog import load_yaml
from .families import FAMILY_IDS


PROFILE_ORDER = (
    "strict",
    "compare_likelihood",
    "compare_psr",
    "compare_tfidf",
    "compare_idf",
)

PROFILE_LABELS = {
    "strict": "Strict",
    "compare_likelihood": "Likelihood",
    "compare_psr": "PSR",
    "compare_tfidf": "TF-IDF",
    "compare_idf": "IDF",
}

METHOD_COPY = {
    "strict": {
        "definition": "以平滑条件概率选出每个条件组合 X 下的首位结果 y，再通过 8 道质量门禁。它是保守基准，不是单独的第五种相关性公式。",
        "formula": "rank = (n_xy + 1) / (n_x + 2)；score = Wilson × max(0, log₂ lift) × ln(1+n_xy) × stability",
        "why": "目标是得到高概率、相对基线有增益、统计可信、重采样稳定且与第二名拉开距离的唯一答案。",
        "emphasis": "确定性、显著性、稳定性、唯一答案",
        "strength": "结果最保守，误把偶然关联或模糊首位当规则的风险较低。",
        "limitation": "多重门禁会大量压低召回率；accepted 少不等于挖掘失败。",
        "use_case": "需要形成高置信候选规则池，优先控制假阳性时。",
    },
    "compare_likelihood": {
        "definition": "直接按平滑后的 P(y|X) 排序，在同一 X 下选择观察概率最高的 y。",
        "formula": "Likelihood = (n_xy + 1) / (n_x + 2)",
        "why": "加一平滑避免小样本出现 0 或 1 的极端概率，同时保留‘这个条件下最常发生什么’的直观解释。",
        "emphasis": "条件内发生概率",
        "strength": "最直观，容易解释为给定表现后最常见的后续结果。",
        "limitation": "不主动惩罚全局常见结果，可能偏向所有患者都常见的检查、诊断或处置。",
        "use_case": "回答‘给定 X，最可能出现什么 y’，作为概率基线。",
    },
    "compare_psr": {
        "definition": "Probability–Specificity–Reliability，将条件概率、相对基线特异性和共同出现次数的可靠性相乘。",
        "formula": "PSR = P(y|X) × raw_lift × [log₁₀(max(1, 1+n_xy−10)) + 1]",
        "why": "单看概率会偏爱常见 y，单看 lift 会放大小样本；三项相乘用于平衡常见度、区分度和证据量。",
        "emphasis": "概率 × 特异性 × 支持可靠性",
        "strength": "比纯概率更重视 X 对 y 的区分作用，又比纯 lift 更抑制低支持偶然性。",
        "limitation": "乘法会放大任一项的尺度选择；当前可靠性常数 nco_min=10、r=1 属于设计参数。",
        "use_case": "寻找既常发生、又相对总体更特异、且有足够共同支持的规则。",
    },
    "compare_tfidf": {
        "definition": "借用信息检索 TF-IDF：以 P(y|X) 表示条件内强度，以 IDF 惩罚全局普遍结果。",
        "formula": "TF-IDF = P(y|X) × [ln((N+1)/(n_y+1)) + 1]",
        "why": "希望保留条件内高概率，同时降低‘无论 X 是什么都很常见’的 y 的排名。",
        "emphasis": "条件概率 × 全局稀有度",
        "strength": "能突出对特定 X 更有辨识度、但并非全局泛滥的结果。",
        "limitation": "IDF 只看 y 的总体频率，不等于临床特异性；稀有结果仍可能因样本偶然性上升。",
        "use_case": "从高频通用行为中寻找更具条件辨识度的结果。",
    },
    "compare_idf": {
        "definition": "只按结果 y 的逆频率排序；在某个 X 的候选结果中优先选择全局更少见的 y。",
        "formula": "IDF = ln((N+1)/(n_y+1)) + 1",
        "why": "作为稀有度极端基线，用来观察完全强调结果稀缺性时，规则选择会发生什么变化。",
        "emphasis": "全局稀有度",
        "strength": "最直接暴露通用高频结果对其他方法的遮蔽程度。",
        "limitation": "不衡量 P(y|X) 或相对关联强度；较高 IDF 不能单独证明 X 能预测 y。",
        "use_case": "方法学敏感性分析和稀有结果探索，不适合作为独立的高置信规则标准。",
    },
}

FAMILY_LABELS = {
    "type1_investigation": "① 检查检验",
    "type2_diagnosis": "② 诊断",
    "type3_medication": "③ 用药",
    "type3_procedure": "③ 操作",
    "type4_service": "④ 服务",
    "type5_disposition": "⑤ 去向",
}

METRICS = (
    "conditional_probability",
    "smoothed_probability",
    "lift",
    "psr",
    "tfidf",
    "idf",
    "wilson_lower",
    "fdr_q",
    "bootstrap_stability",
)


class ComparisonError(ValueError):
    pass


@dataclass(frozen=True)
class RunInfo:
    profile: str
    directory: Path
    summaries: dict[str, dict[str, Any]]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ComparisonError(f"expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ComparisonError(f"expected JSON object at {path}:{line_number}")
            rows.append(payload)
    return rows


def discover_complete_runs(input_root: Path) -> tuple[list[RunInfo], list[dict[str, Any]]]:
    """Return one complete six-family run per supported profile and exclusions."""
    input_root = input_root.resolve()
    runs_by_profile: dict[str, RunInfo] = {}
    excluded: list[dict[str, Any]] = []
    if not input_root.is_dir():
        raise FileNotFoundError(f"mining root not found: {input_root}")

    for directory in sorted(path for path in input_root.iterdir() if path.is_dir()):
        if directory.name == "comparison":
            continue
        summaries: dict[str, dict[str, Any]] = {}
        profiles: set[str] = set()
        missing: list[str] = []
        incomplete: list[str] = []
        for family in FAMILY_IDS:
            family_dir = directory / family
            summary_path = family_dir / "summary.json"
            manifest_path = family_dir / "mining_manifest.json"
            rules_path = family_dir / "conditional_rules.jsonl"
            if not summary_path.is_file() or not manifest_path.is_file() or not rules_path.is_file():
                missing.append(family)
                continue
            summary = _read_json(summary_path)
            manifest = _read_json(manifest_path)
            if manifest.get("status") != "complete":
                incomplete.append(family)
                continue
            profile = str(summary.get("profile") or (manifest.get("identity") or {}).get("profile") or "")
            if not profile:
                incomplete.append(family)
                continue
            profiles.add(profile)
            summaries[family] = summary
        reason = None
        if missing:
            reason = f"缺少家族或核心文件：{', '.join(missing)}"
        elif incomplete:
            reason = f"manifest 未完成：{', '.join(incomplete)}"
        elif len(profiles) != 1:
            reason = f"profile 不一致：{', '.join(sorted(profiles)) or 'unknown'}"
        profile = next(iter(profiles), "unknown")
        if reason is None and profile not in PROFILE_ORDER:
            reason = f"不属于预设比较 profile：{profile}"
        if reason is not None:
            excluded.append({"directory": directory.name, "reason": reason})
            continue
        if profile in runs_by_profile:
            raise ComparisonError(
                f"duplicate complete profile {profile}: "
                f"{runs_by_profile[profile].directory.name}, {directory.name}"
            )
        runs_by_profile[profile] = RunInfo(profile=profile, directory=directory, summaries=summaries)

    runs = [runs_by_profile[profile] for profile in PROFILE_ORDER if profile in runs_by_profile]
    if len(runs) < 2:
        raise ComparisonError("need at least two complete six-family runs")
    return runs, excluded


def canonical_rule_key(rule: dict[str, Any]) -> str:
    family = str(rule.get("family") or "")
    features = sorted(str(value) for value in rule.get("condition_feature_ids") or [])
    outcome = str(rule.get("target_outcome_id") or "")
    return "\x1f".join((family, "\x1e".join(features), outcome))


def _numeric(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _metric_summary(rules: Iterable[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    rows = list(rules)
    result: dict[str, dict[str, float | None]] = {}
    for metric in METRICS:
        values = [number for row in rows if (number := _numeric(row.get(metric))) is not None]
        result[metric] = {
            "mean": round(statistics.fmean(values), 6) if values else None,
            "median": round(statistics.median(values), 6) if values else None,
        }
    return result


def _compact_rule(rule: dict[str, Any], *, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "family": str(rule.get("family") or ""),
        "condition": " + ".join(str(value) for value in rule.get("condition_display_names") or []),
        "outcome": str(rule.get("target_outcome_name") or rule.get("target_outcome_id") or ""),
        "rule_key": canonical_rule_key(rule),
        "n_x": rule.get("n_x"),
        "n_xy": rule.get("n_xy"),
        "conditional_probability": rule.get("conditional_probability"),
        "smoothed_probability": rule.get("smoothed_probability"),
        "lift": rule.get("lift"),
        "psr": rule.get("psr"),
        "tfidf": rule.get("tfidf"),
        "idf": rule.get("idf"),
        "wilson_lower": rule.get("wilson_lower"),
        "fdr_q": rule.get("fdr_q"),
        "bootstrap_stability": rule.get("bootstrap_stability"),
        "score": rule.get("score"),
    }


def _method_definitions(threshold_profiles: dict[str, Any]) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for profile in PROFILE_ORDER:
        copy = METHOD_COPY[profile]
        thresholds = threshold_profiles.get(profile) or {}
        definitions.append(
            {
                "profile": profile,
                "label": PROFILE_LABELS[profile],
                **copy,
                "rank_key": thresholds.get("rank_key"),
                "min_x_support": thresholds.get("min_x_support"),
                "min_xy_support": thresholds.get("min_xy_support"),
                "min_smoothed_probability": thresholds.get("min_smoothed_probability"),
                "min_lift": thresholds.get("min_lift"),
                "min_wilson_lower": thresholds.get("min_wilson_lower"),
                "max_fdr_q": thresholds.get("max_fdr_q"),
                "min_bootstrap_stability": thresholds.get("min_bootstrap_stability"),
                "min_probability_gap": thresholds.get("min_probability_gap"),
                "min_score_ratio": thresholds.get("min_score_ratio"),
                "bootstrap_iterations": thresholds.get("bootstrap_iterations"),
            }
        )
    return definitions


def build_comparison(
    runs: list[RunInfo],
    excluded: list[dict[str, Any]],
    *,
    top_n: int = 40,
    threshold_profiles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if top_n < 1:
        raise ComparisonError("top_n must be positive")
    run_rules: dict[str, dict[str, list[dict[str, Any]]]] = {}
    accepted_keys: dict[tuple[str, str], set[str]] = {}
    method_rows: list[dict[str, Any]] = []
    family_rows: list[dict[str, Any]] = []
    top_rules: list[dict[str, Any]] = []

    for family in FAMILY_IDS:
        fingerprints = {
            str(run.summaries[family].get("transactions_sha256") or "") for run in runs
        }
        if "" in fingerprints:
            raise ComparisonError(f"missing transactions_sha256 for {family}")
        if len(fingerprints) != 1:
            raise ComparisonError(f"transactions differ across profiles for {family}")

    for run in runs:
        run_rules[run.profile] = {}
        total_accepted = 0
        total_rejected = 0
        total_tested = 0
        for family in FAMILY_IDS:
            summary = run.summaries[family]
            rules = _read_jsonl(run.directory / family / "conditional_rules.jsonl")
            run_rules[run.profile][family] = rules
            keys = {canonical_rule_key(rule) for rule in rules}
            accepted_keys[(run.profile, family)] = keys
            accepted = int(summary.get("accepted") or len(rules))
            if accepted != len(rules):
                raise ComparisonError(
                    f"accepted count mismatch for {run.directory.name}/{family}: "
                    f"summary={accepted}, rows={len(rules)}"
                )
            rejected = int(summary.get("rejected") or 0)
            tested = int(summary.get("tested_pairs") or 0)
            total_accepted += accepted
            total_rejected += rejected
            total_tested += tested
            family_rows.append(
                {
                    "profile": run.profile,
                    "family": family,
                    "transactions": int(summary.get("transactions") or 0),
                    "tested": tested,
                    "accepted": accepted,
                    "rejected": rejected,
                    "acceptance_rate": round(accepted / (accepted + rejected), 6)
                    if accepted + rejected
                    else 0.0,
                    "metrics": _metric_summary(rules),
                }
            )
            rank_key = str(summary.get("rank_key") or "smoothed_probability")
            ranked = sorted(
                rules,
                key=lambda rule: (
                    -(_numeric(rule.get(rank_key)) or 0.0),
                    -(_numeric(rule.get("n_xy")) or 0.0),
                    canonical_rule_key(rule),
                ),
            )
            for rank, rule in enumerate(ranked[:top_n], start=1):
                top_rules.append({"profile": run.profile, "rank_key": rank_key, **_compact_rule(rule, rank=rank)})
        method_rows.append(
            {
                "profile": run.profile,
                "label": PROFILE_LABELS.get(run.profile, run.profile),
                "directory": run.directory.name,
                "accepted": total_accepted,
                "rejected": total_rejected,
                "tested": total_tested,
                "acceptance_rate": round(total_accepted / (total_accepted + total_rejected), 6)
                if total_accepted + total_rejected
                else 0.0,
            }
        )

    pairwise: list[dict[str, Any]] = []
    for index, left in enumerate(runs):
        for right in runs[index + 1 :]:
            for family in ("all", *FAMILY_IDS):
                if family == "all":
                    left_keys = set().union(*(accepted_keys[(left.profile, item)] for item in FAMILY_IDS))
                    right_keys = set().union(*(accepted_keys[(right.profile, item)] for item in FAMILY_IDS))
                else:
                    left_keys = accepted_keys[(left.profile, family)]
                    right_keys = accepted_keys[(right.profile, family)]
                intersection = len(left_keys & right_keys)
                union = len(left_keys | right_keys)
                pairwise.append(
                    {
                        "family": family,
                        "left": left.profile,
                        "right": right.profile,
                        "intersection": intersection,
                        "union": union,
                        "left_only": len(left_keys - right_keys),
                        "right_only": len(right_keys - left_keys),
                        "jaccard": round(intersection / union, 6) if union else 1.0,
                    }
                )

    top_key_profiles: dict[str, set[str]] = {}
    for row in top_rules:
        top_key_profiles.setdefault(row["rule_key"], set()).add(row["profile"])
    for row in top_rules:
        row["method_count"] = len(top_key_profiles[row["rule_key"]])

    return {
        "schema_version": "mcq-visit-mining-comparison/1.0.0",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "exploratory_unreviewed",
        "gold": 0,
        "families": [{"id": family, "label": FAMILY_LABELS[family]} for family in FAMILY_IDS],
        "methods": method_rows,
        "method_definitions": _method_definitions(threshold_profiles or {}),
        "family_rows": family_rows,
        "pairwise": pairwise,
        "top_rules": top_rules,
        "excluded_runs": excluded,
        "notes": [
            "仅比较六个家族均完整且 mining_manifest.status=complete 的跑次。",
            "规则交集按 family + 排序后的 condition_feature_ids + target_outcome_id 对齐；rule_id 因包含 profile 不用于跨方法对齐。",
            "不同 profile 的筛选门槛并不相同，因此 accepted 数量和 Jaccard 反映的是“排序策略 + 门槛”的联合差异。",
            "接受率 = accepted / (accepted + rejected)，不是 accepted / tested_pairs。",
            "所有结果均为 exploratory_unreviewed，gold=0，不可直接进入出题或正式评测。",
        ],
    }


def _json_for_script(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def render_html(payload: dict[str, Any]) -> str:
    data = _json_for_script(payload)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MCQ Visit 挖掘规则比较</title>
<style>
:root{{--bg:#09111f;--panel:#111d30;--panel2:#16243a;--line:#2a3b55;--text:#edf4ff;--muted:#9fb1c9;--accent:#5bd6c7;--accent2:#ffb65c;--danger:#ff7383}}
*{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at 15% 0,#18304a 0,#09111f 42%);color:var(--text);font:14px/1.5 Inter,"Segoe UI",sans-serif}}
.wrap{{max-width:1480px;margin:auto;padding:32px}} h1{{margin:0;font-size:32px;letter-spacing:-.5px}} h2{{margin:0 0 14px;font-size:18px}} .sub{{color:var(--muted);margin:8px 0 24px}}
.controls{{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0 22px}} select{{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:9px 12px}}
.grid{{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:12px}} .card,.panel{{background:linear-gradient(145deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:14px;box-shadow:0 12px 30px #0004}}
.card{{padding:16px}} .card .name{{color:var(--muted)}} .card .big{{font-size:28px;font-weight:750;margin-top:6px}} .card .small{{color:var(--accent);font-variant-numeric:tabular-nums}}
.panel{{padding:18px;margin-top:16px}} .two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}} .bars{{display:grid;gap:10px}} .barrow{{display:grid;grid-template-columns:105px 1fr 75px;gap:10px;align-items:center}} .track{{height:13px;background:#07101d;border-radius:20px;overflow:hidden}} .fill{{height:100%;background:linear-gradient(90deg,var(--accent),#6fa7ff);border-radius:20px}}
.method-defs{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}} .method-card{{background:#0d1929;border:1px solid var(--line);border-radius:12px;padding:15px}} .method-card h3{{margin:0 0 8px;font-size:16px}} .method-card p{{margin:7px 0}} .formula{{display:block;background:#07101d;border-left:3px solid var(--accent);border-radius:5px;padding:9px;color:#cce7ff;white-space:normal}} .why{{color:#c7d7e9}} .comparison-table td:first-child{{min-width:105px}}
table{{width:100%;border-collapse:collapse;font-size:13px}} th{{position:sticky;top:0;background:#15233a;color:#bcd0e8;text-align:left}} th,td{{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}} tr:hover td{{background:#ffffff07}} .scroll{{max-height:560px;overflow:auto;border:1px solid var(--line);border-radius:10px}}
.pill{{display:inline-block;border:1px solid #44617f;border-radius:20px;padding:2px 8px;color:#cce2f7;white-space:nowrap}} .num{{font-variant-numeric:tabular-nums;text-align:right}} .muted{{color:var(--muted)}}
.matrix{{display:grid;grid-template-columns:150px repeat(5,1fr);gap:4px}} .cell{{padding:10px;border-radius:7px;background:#101c2d;text-align:center}} .cell.head{{color:var(--muted);font-size:12px}}
.notes{{margin:0;padding-left:20px;color:var(--muted)}} .warn{{color:var(--accent2)}} @media(max-width:1000px){{.grid{{grid-template-columns:repeat(2,1fr)}}.two{{grid-template-columns:1fr}}.matrix{{grid-template-columns:120px repeat(5,90px);min-width:620px}}}} @media(max-width:620px){{.wrap{{padding:18px}}.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body><main class="wrap">
<h1>MCQ Visit 挖掘规则比较</h1>
<p class="sub">五种规则选择策略 × 六个题型家族 · <span id="generated"></span> · exploratory_unreviewed / gold=0</p>
<div class="controls"><label>家族 <select id="family"></select></label><label>规则方法 <select id="method"></select></label></div>
<section id="cards" class="grid"></section>
<section class="panel"><h2>Accepted 规模</h2><div id="bars" class="bars"></div></section>
<section class="panel"><h2>五种方法分别是什么</h2><p class="muted">定义来自当前评分实现；门槛来自当前 <code>config/mcq_visit_mining/thresholds.yaml</code>。Strict 是保守质量基准，其余四项是排序策略对照。</p><div id="methodDefs" class="method-defs"></div></section>
<section class="panel"><h2>为什么这样定义：横向比较</h2><div class="scroll"><table class="comparison-table"><thead><tr><th>方法</th><th>核心强调</th><th>为什么这样设计</th><th>优势</th><th>局限</th><th>适合回答</th></tr></thead><tbody id="methodComparisonRows"></tbody></table></div></section>
<section class="panel"><h2>当前 profile 门槛横向表</h2><p class="muted">0 或 1 通常表示该门禁在对照 profile 中关闭。所有方法仍要求每个 X 至少有两个达到 n_xy 门槛的候选 y，否则以 insufficient_outcomes 拒绝。</p><div class="scroll"><table><thead><tr><th>方法</th><th>rank_key</th><th>n_x≥</th><th>n_xy≥</th><th>P平滑≥</th><th>lift≥</th><th>Wilson≥</th><th>FDR q≤</th><th>稳定性≥</th><th>首二差≥</th><th>score ratio≥</th><th>bootstrap</th></tr></thead><tbody id="thresholdRows"></tbody></table></div></section>
<div class="two">
  <section class="panel"><h2>方法汇总</h2><div class="scroll"><table><thead><tr><th>方法</th><th>tested</th><th>accepted</th><th>rejected</th><th>接受率</th></tr></thead><tbody id="summaryRows"></tbody></table></div></section>
  <section class="panel"><h2>Accepted 规则 Jaccard</h2><div class="scroll"><div id="matrix" class="matrix"></div></div></section>
</div>
<section class="panel"><h2>Top 规则</h2><p class="muted">按各 profile 自身 rank_key 排名；“覆盖方法数”只统计进入各方法 Top 列表的重复规则。</p><div class="scroll"><table><thead><tr><th>方法</th><th>#</th><th>条件 X</th><th>结果 y</th><th>rank key</th><th>n_xy</th><th>P(y|X)</th><th>lift</th><th>PSR</th><th>TF-IDF</th><th>覆盖方法数</th></tr></thead><tbody id="ruleRows"></tbody></table></div></section>
<section class="panel"><h2>读数边界</h2><ul id="notes" class="notes"></ul><div id="excluded"></div></section>
</main>
<script>const DATA={data};
const $=id=>document.getElementById(id); const fmt=n=>n==null?'—':Number(n).toLocaleString('zh-CN',{{maximumFractionDigits:4}}); const pct=n=>n==null?'—':(Number(n)*100).toFixed(2)+'%';
const family=$('family'),method=$('method'); family.innerHTML='<option value="all">全部家族</option>'+DATA.families.map(x=>`<option value="${{x.id}}">${{x.label}}</option>`).join(''); method.innerHTML='<option value="all">全部方法</option>'+DATA.methods.map(x=>`<option value="${{x.profile}}">${{x.label}}</option>`).join(''); $('generated').textContent=DATA.generated_at;
const methodMap=Object.fromEntries(DATA.methods.map(x=>[x.profile,x])); const label=p=>methodMap[p]?.label||p; const familyLabel=f=>DATA.families.find(x=>x.id===f)?.label||f;
function renderDefinitions(){{$('methodDefs').innerHTML=DATA.method_definitions.map(x=>`<article class="method-card"><h3>${{x.label}}</h3><p>${{x.definition}}</p><code class="formula">${{x.formula}}</code><p class="why"><strong>设计原因：</strong>${{x.why}}</p></article>`).join(''); $('methodComparisonRows').innerHTML=DATA.method_definitions.map(x=>`<tr><td><span class="pill">${{x.label}}</span></td><td>${{x.emphasis}}</td><td>${{x.why}}</td><td>${{x.strength}}</td><td>${{x.limitation}}</td><td>${{x.use_case}}</td></tr>`).join(''); $('thresholdRows').innerHTML=DATA.method_definitions.map(x=>`<tr><td><span class="pill">${{x.label}}</span></td><td>${{x.rank_key??'—'}}</td><td class="num">${{fmt(x.min_x_support)}}</td><td class="num">${{fmt(x.min_xy_support)}}</td><td class="num">${{fmt(x.min_smoothed_probability)}}</td><td class="num">${{fmt(x.min_lift)}}</td><td class="num">${{fmt(x.min_wilson_lower)}}</td><td class="num">${{fmt(x.max_fdr_q)}}</td><td class="num">${{fmt(x.min_bootstrap_stability)}}</td><td class="num">${{fmt(x.min_probability_gap)}}</td><td class="num">${{fmt(x.min_score_ratio)}}</td><td class="num">${{fmt(x.bootstrap_iterations)}}</td></tr>`).join('');}}
function rowsForFamily(){{if(family.value==='all')return DATA.methods; return DATA.family_rows.filter(x=>x.family===family.value).map(x=>({{...x,label:label(x.profile)}}));}}
function render(){{const rows=rowsForFamily(); const max=Math.max(...rows.map(x=>x.accepted),1); $('cards').innerHTML=rows.map(x=>`<article class="card"><div class="name">${{x.label}}</div><div class="big">${{fmt(x.accepted)}}</div><div class="small">accepted · ${{pct(x.acceptance_rate)}}</div></article>`).join(''); $('bars').innerHTML=rows.map(x=>`<div class="barrow"><span>${{x.label}}</span><div class="track"><div class="fill" style="width:${{x.accepted/max*100}}%"></div></div><strong class="num">${{fmt(x.accepted)}}</strong></div>`).join(''); $('summaryRows').innerHTML=rows.map(x=>`<tr><td><span class="pill">${{x.label}}</span></td><td class="num">${{fmt(x.tested)}}</td><td class="num">${{fmt(x.accepted)}}</td><td class="num">${{fmt(x.rejected)}}</td><td class="num">${{pct(x.acceptance_rate)}}</td></tr>`).join(''); renderMatrix(); renderRules();}}
function heat(v){{return `background:rgba(91,214,199,${{(0.10+v*0.72).toFixed(3)}})`}} function renderMatrix(){{const profiles=DATA.methods.map(x=>x.profile), fam=family.value; let html='<div class="cell head">方法</div>'+profiles.map(p=>`<div class="cell head">${{label(p)}}</div>`).join(''); for(const left of profiles){{html+=`<div class="cell head">${{label(left)}}</div>`;for(const right of profiles){{if(left===right){{html+=`<div class="cell" style="${{heat(1)}}">1.000</div>`;continue}}const p=DATA.pairwise.find(x=>x.family===fam&&((x.left===left&&x.right===right)||(x.left===right&&x.right===left))),v=p?.jaccard||0;html+=`<div class="cell" style="${{heat(v)}}" title="交集 ${{fmt(p?.intersection)}} / 并集 ${{fmt(p?.union)}}">${{v.toFixed(3)}}</div>`;}}}}$('matrix').innerHTML=html;}}
function renderRules(){{let rows=DATA.top_rules.filter(x=>(family.value==='all'||x.family===family.value)&&(method.value==='all'||x.profile===method.value)); rows.sort((a,b)=>a.profile.localeCompare(b.profile)||a.family.localeCompare(b.family)||a.rank-b.rank); $('ruleRows').innerHTML=rows.map(x=>`<tr><td><span class="pill">${{label(x.profile)}}</span><br><span class="muted">${{familyLabel(x.family)}}</span></td><td class="num">${{x.rank}}</td><td>${{x.condition}}</td><td>${{x.outcome}}</td><td>${{x.rank_key}}</td><td class="num">${{fmt(x.n_xy)}}</td><td class="num">${{pct(x.conditional_probability)}}</td><td class="num">${{fmt(x.lift)}}</td><td class="num">${{fmt(x.psr)}}</td><td class="num">${{fmt(x.tfidf)}}</td><td class="num">${{x.method_count}}</td></tr>`).join('')||'<tr><td colspan="11">没有符合筛选条件的规则</td></tr>';}}
family.addEventListener('change',render); method.addEventListener('change',renderRules); $('notes').innerHTML=DATA.notes.map(x=>`<li>${{x}}</li>`).join(''); $('excluded').innerHTML=DATA.excluded_runs.length?'<p class="warn">排除的不完整跑次：</p><ul class="notes">'+DATA.excluded_runs.map(x=>`<li>${{x.directory}}：${{x.reason}}</li>`).join('')+'</ul>':''; renderDefinitions(); render();
</script></body></html>"""


def render_readme(payload: dict[str, Any], *, input_root: Path, output_dir: Path) -> str:
    methods = "\n".join(
        f"- `{row['label']}`：`{row['directory']}`，accepted={row['accepted']:,}"
        for row in payload["methods"]
    )
    excluded = "\n".join(
        f"- `{row['directory']}`：{row['reason']}" for row in payload["excluded_runs"]
    ) or "- 无"
    return f"""# MCQ Visit 挖掘规则比较说明

本目录由 `python -m data_pipeline.mcq_visit_mining.comparison` 自动生成，用于比较完整的六家族挖掘跑次。

## 文件

- `index.html`：自包含交互式可视化页面，直接用浏览器打开。
- `comparison_summary.json`：页面使用的结构化汇总数据，不包含患者级记录。
- `说明文档.md`：本说明。

## 本次输入

输入根目录：`{input_root.resolve()}`

{methods}

排除的跑次：

{excluded}

## 比较口径

- 只纳入六个 family 核心文件齐全、且每个 `mining_manifest.json` 均为 `status=complete` 的跑次。
- 跨方法规则键为 `family + 排序后的 condition_feature_ids + target_outcome_id`。不能直接比较 `rule_id`，因为它包含 profile。
- Jaccard = accepted 规则交集 / accepted 规则并集。
- Top 规则按各方法自己的 `rank_key` 排序，因此反映该方法的目标函数。
- 不同 profile 同时改变排序方式和筛选门槛，accepted 数量差异不能解释为单一评分函数的纯效果。

## 重新生成

```powershell
.\\.venv\\Scripts\\python.exe -m data_pipeline.mcq_visit_mining.comparison `
  --input-root data\\derived\\mcq_visit_mining `
  --output-dir data\\derived\\mcq_visit_mining\\comparison
```

当前输出目录：`{output_dir.resolve()}`

所有结果均为 `exploratory_unreviewed`，`gold=0`，不能直接用于出题或正式评测。
"""


def write_outputs(payload: dict[str, Any], *, input_root: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "index.html").write_text(render_html(payload), encoding="utf-8")
    (output_dir / "说明文档.md").write_text(
        render_readme(payload, input_root=input_root, output_dir=output_dir), encoding="utf-8"
    )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare complete MCQ visit mining runs in a self-contained HTML report")
    parser.add_argument("--input-root", type=Path, default=Path("data/derived/mcq_visit_mining"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/derived/mcq_visit_mining/comparison"))
    parser.add_argument(
        "--thresholds-config",
        type=Path,
        default=Path("config/mcq_visit_mining/thresholds.yaml"),
        help="profile thresholds shown in the method comparison table",
    )
    parser.add_argument("--top-n", type=int, default=40, help="top accepted rules retained per family and profile")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        input_root = args.input_root.resolve()
        output_dir = args.output_dir.resolve()
        if output_dir == input_root:
            raise ComparisonError("output-dir must be a child directory, not the mining root itself")
        runs, excluded = discover_complete_runs(input_root)
        threshold_config = load_yaml(args.thresholds_config)
        threshold_profiles = threshold_config.get("profiles") or {}
        payload = build_comparison(
            runs,
            excluded,
            top_n=args.top_n,
            threshold_profiles=threshold_profiles,
        )
        write_outputs(payload, input_root=input_root, output_dir=output_dir)
    except (ComparisonError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"mcq_visit_mining comparison failed: {exc}")
        return 1
    print(
        f"comparison complete methods={len(payload['methods'])} "
        f"families={len(payload['families'])} output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
