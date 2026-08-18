"""Fail-closed feasibility audit for exploratory method comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


METHODS = ("frequency", "lift", "shrunk_log_rr", "binary_tfidf", "bm25")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(e2_path: Path, e3_path: Path) -> dict[str, Any]:
    e2 = json.loads(e2_path.read_text(encoding="utf-8"))
    e3 = json.loads(e3_path.read_text(encoding="utf-8"))
    imaging_concepts = len(e2.get("top_concepts", {}).get("imaging_ordered", []))
    definitions = e3["definitions"]
    candidates = []
    for name, metric in definitions.items():
        degenerate = name == "mapped_imaging_order" and imaging_concepts <= 1
        unique_rate = metric["unique_candidate_rate_among_eligible"]
        suitable = (not degenerate and unique_rate >= 0.5 and metric["coverage_rate"] >= 0.5 and metric["missing_candidate_key_rows"] == 0 and metric["time_leakage_rows"] == 0)
        candidates.append({"definition": name, "gold_suitable_under_preregistered_gate": suitable, "degenerate_candidate_space": degenerate, "coverage_rate": metric["coverage_rate"], "unique_candidate_rate": unique_rate, "missing_candidate_key_rows": metric["missing_candidate_key_rows"], "unknown_available_time_rows": metric["unknown_available_time_rows"], "time_leakage_rows": metric["time_leakage_rows"], "reason": "PASS" if suitable else "NO_UNIQUE_NON_DEGENERATE_GOLD"})
    methods = []
    for method in METHODS:
        methods.append({"method": method, "candidate_generation_allowed": True, "final_answer_ranking_allowed": False, "recall_mrr_ndcg_estimable": False, "reason": "NO_VALID_UNIQUE_EHR_GOLD"})
    return {
        "audit_schema": "exploratory-method-feasibility-audit/1.0.0",
        "inputs": {"e2_sha256": sha256(e2_path), "e3_sha256": sha256(e3_path), "source_root": e3.get("source_root")},
        "gold_gate": {"coverage_minimum": 0.5, "unique_answer_minimum": 0.5, "missing_candidate_key_allowed": False, "time_leakage_allowed": False, "formal_final_test": False},
        "gold_candidates": candidates,
        "method_status": methods,
        "conclusion": "NO_CURRENT_EHR_GOLD_MEETS_GATE",
        "next_data_requirements": ["freeze source-specific order concept mapping or reviewed source labels", "define valid lifecycle semantics for order target", "retain zero/multi-candidate refusals", "re-run decision-level target/evidence audit on replacement RWD"],
    }


def write_report(result: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# E4 探索性方法可评估性审计",
        "",
        "> 由于当前 EHR 候选没有形成合适的唯一 Gold，本阶段不伪造 Recall/MRR/NDCG 或 validation 结论。",
        "",
        "## Gold 门禁",
        "",
        "本次探索性门禁采用：覆盖率 ≥ 50%、唯一答案率 ≥ 50%、无候选 key 缺失、无 target availability 泄漏。该门禁用于方法学筛查，不是临床有效性阈值。",
        "",
        "| 候选定义 | 覆盖率 | 唯一答案率 | 结论 |",
        "|---|---:|---:|---|",
    ]
    for item in result["gold_candidates"]:
        lines.append(f"| `{item['definition']}` | {item['coverage_rate']:.3%} | {item['unique_candidate_rate']:.3%} | `{item['reason']}` |")
    lines += [
        "",
        "## 方法职责边界",
        "",
        "| 方法 | 当前允许 | 当前禁止 |",
        "|---|---|---|",
    ]
    for item in result["method_status"]:
        lines.append(f"| `{item['method']}` | 候选生成 | 最终答案排名、Recall/MRR/NDCG 声称 |")
    lines += [
        "",
        "## 结论",
        "",
        "当前数据不能提供足够可靠的 EHR-observable Gold。最主要问题不是算法，而是订单概念 unresolved、订单生命周期大量 Inactive、结果/订单语义不同以及候选多答案。换用香港 RWD 时应先迁移 Gold 定义与门禁，再重新计算 coverage/uniqueness/leakage，不能迁移当前样本标签。",
        "",
        "详细输入 hash 和门禁见同目录 JSON。",
    ]
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--e2", type=Path, required=True)
    parser.add_argument("--e3", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.e2, args.e3)
    write_report(result, args.json_output, args.markdown_output)
    print(json.dumps({"conclusion": result["conclusion"], "gold_candidates": result["gold_candidates"], "json_output": str(args.json_output), "markdown_output": str(args.markdown_output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
