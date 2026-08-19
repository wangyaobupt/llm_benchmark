"""Generate a human-review Markdown checklist from questions_reviewed.jsonl."""
from __future__ import annotations

import json
import math
from pathlib import Path

REVIEWED = Path(r"D:\Projects\llm_benchmark\data\phenotype\generation_formal_v2\questions_reviewed.jsonl")
OUT = Path(r"D:\Projects\llm_benchmark\data\phenotype\generation_formal_v2\human_review_checklist.md")


def _score(stats: dict) -> float:
    lift = max(0.0, stats.get("lift") or 0.0)
    wilson = stats.get("wilson_lower") or 0.0
    n_xy = stats.get("n_xy") or 0
    stab = stats.get("bootstrap_stability") or 0.0
    log2_lift = math.log2(lift) if lift > 0 else 0.0
    return wilson * log2_lift * math.log1p(n_xy) * stab


def main() -> None:
    qs = [json.loads(l) for l in REVIEWED.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = []
    for q in qs:
        s = q.get("statistics") or {}
        rows.append({
            "question_id": q["question_id"],
            "condition": "; ".join(q.get("condition_features") or []),
            "stem": q.get("stem", ""),
            "options": q.get("options", {}),
            "correct_option": q.get("correct_option"),
            "correct_answer": q.get("correct_answer"),
            "lift": s.get("lift"),
            "n_x": s.get("n_x"),
            "wilson": s.get("wilson_lower"),
            "stability": s.get("bootstrap_stability"),
            "score": _score(s),
        })
    rows.sort(key=lambda r: -r["score"])

    lines: list[str] = []
    lines.append("# 出题人工审核清单（formal imaging）\n")
    lines.append(f"> 共 {len(rows)} 条 candidate_passed，按 score 降序。逐条在「决策」勾选 approved / rejected / revise。\n")
    lines.append("| # | 决策 | 答案 | 条件 | 题干 | 选项 | lift | n_x | score |")
    lines.append("|---|---|---|---|---|---|---:|---:|---:|")

    for i, r in enumerate(rows, 1):
        opts = r["options"]
        abcd = " / ".join(f"{k}. {opts.get(k)}" for k in "ABCD")
        # mark the correct option bold
        stem = r["stem"].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {i} | ☐ approved ☐ rejected ☐ revise | **{r['correct_answer']}** "
            f"| {r['condition']} | {stem} | {abcd} "
            f"| {r['lift']:.2f} | {r['n_x']} | {r['score']:.2f} |"
        )

    # Also emit a per-question detailed section for easy reading.
    lines.append("\n---\n\n## 逐题详情\n")
    for i, r in enumerate(rows, 1):
        opts = r["options"]
        abcd = "\n".join(
            f"  - **{k}** {opts.get(k)}{' ← 正确答案' if k == r['correct_option'] else ''}"
            for k in "ABCD"
        )
        lines.append(
            f"### {i}. {r['question_id']}\n\n"
            f"- 条件：{r['condition']}\n"
            f"- 题干：{r['stem']}\n"
            f"- 选项：\n{abcd}\n"
            f"- 统计：lift {r['lift']:.2f} | n_x {r['n_x']} | wilson {r['wilson']:.2f} | "
            f"stability {r['stability']:.2f} | score {r['score']:.2f}\n"
            f"- 决策：☐ approved　☐ rejected　☐ revise\n"
        )

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"n": len(rows), "out": str(OUT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
