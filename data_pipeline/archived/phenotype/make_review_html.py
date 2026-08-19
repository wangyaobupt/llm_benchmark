"""Generate an interactive HTML review page (radio buttons + export JSON)."""
from __future__ import annotations

import json
import math
from pathlib import Path

REVIEWED = Path(r"D:\Projects\llm_benchmark\data\phenotype\generation_formal_v2\questions_reviewed.jsonl")
OUT = Path(r"D:\Projects\llm_benchmark\data\phenotype\generation_formal_v2\human_review.html")


def _score(stats: dict) -> float:
    lift = max(0.0, stats.get("lift") or 0.0)
    wilson = stats.get("wilson_lower") or 0.0
    n_xy = stats.get("n_xy") or 0
    stab = stats.get("bootstrap_stability") or 0.0
    log2_lift = math.log2(lift) if lift > 0 else 0.0
    return wilson * log2_lift * math.log1p(n_xy) * stab


def _escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main() -> None:
    qs = [json.loads(l) for l in REVIEWED.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = []
    for q in qs:
        s = q.get("statistics") or {}
        rows.append({
            "qid": q["question_id"],
            "condition": "; ".join(q.get("condition_features") or []),
            "stem": q.get("stem", ""),
            "options": q.get("options", {}),
            "correct_option": q.get("correct_option"),
            "correct_answer": q.get("correct_answer"),
            "lift": round(s.get("lift") or 0.0, 2),
            "n_x": s.get("n_x"),
            "score": round(_score(s), 2),
        })
    rows.sort(key=lambda r: -r["score"])

    cards = []
    for i, r in enumerate(rows, 1):
        opts = r["options"]
        opt_html = "".join(
            f'<div class="opt{" correct" if k == r["correct_option"] else ""}">'
            f'<b>{k}</b>. {_escape(opts.get(k, ""))}'
            f'{" <span class=tag>正确答案</span>" if k == r["correct_option"] else ""}'
            f"</div>"
            for k in "ABCD"
        )
        cards.append(f"""
<article class="card" id="q{i}" data-qid="{_escape(r['qid'])}">
  <header>
    <span class="idx">#{i}</span>
    <span class="ans">答案 <b>{_escape(r['correct_answer'])}</b></span>
    <span class="stat">lift {r['lift']} · n_x {r['n_x']} · score {r['score']}</span>
  </header>
  <div class="cond"><b>条件：</b>{_escape(r['condition'])}</div>
  <div class="stem">{_escape(r['stem'])}</div>
  <div class="opts">{opt_html}</div>
  <div class="decide">
    <label><input type="radio" name="d{i}" value="approved"> approved</label>
    <label><input type="radio" name="d{i}" value="rejected"> rejected</label>
    <label><input type="radio" name="d{i}" value="revise"> revise</label>
    <span class="mark" id="m{i}"></span>
  </div>
</article>""")

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>出题人工审核（formal imaging）</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; margin: 0; background: #f5f6f8; color: #1a1d21; }}
  .bar {{ position: sticky; top: 0; background: #fff; border-bottom: 1px solid #e2e5e9; padding: 12px 20px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; z-index: 10; }}
  .bar h1 {{ font-size: 16px; margin: 0 16px 0 0; }}
  .bar button {{ padding: 8px 14px; border: 1px solid #c9ced6; border-radius: 6px; background: #fff; cursor: pointer; font-size: 13px; }}
  .bar button.primary {{ background: #0a7cff; border-color: #0a7cff; color: #fff; }}
  .bar .count {{ color: #5b6472; font-size: 13px; }}
  .cards {{ padding: 16px 20px; max-width: 980px; margin: 0 auto; }}
  .card {{ background: #fff; border: 1px solid #e2e5e9; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; }}
  .card header {{ display: flex; gap: 12px; align-items: baseline; margin-bottom: 8px; }}
  .idx {{ font-weight: 700; color: #0a7cff; }}
  .ans {{ font-size: 14px; }}
  .stat {{ margin-left: auto; color: #5b6472; font-size: 12px; }}
  .cond {{ font-size: 13px; color: #37414e; margin-bottom: 6px; }}
  .stem {{ font-size: 14px; margin-bottom: 8px; line-height: 1.5; }}
  .opts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 4px 16px; margin-bottom: 10px; }}
  .opt {{ font-size: 13px; padding: 2px 0; }}
  .opt.correct {{ background: #eef6ee; border-radius: 4px; padding: 2px 4px; }}
  .tag {{ color: #0a7cff; font-size: 11px; }}
  .decide {{ display: flex; gap: 18px; align-items: center; font-size: 14px; }}
  .decide label {{ cursor: pointer; }}
  .mark {{ color: #0a7cff; font-size: 12px; }}
  textarea {{ display: block; width: calc(100% - 40px); max-width: 940px; margin: 16px auto; height: 160px; font-family: monospace; font-size: 12px; }}
</style>
</head>
<body>
<div class="bar">
  <h1>出题人工审核（formal imaging · {len(rows)} 条）</h1>
  <button onclick="allApproved()">全选 approved</button>
  <button onclick="clearAll()">清空</button>
  <button class="primary" onclick="exportJson()">导出决策 JSON</button>
  <span class="count" id="cnt">已决定 0 / {len(rows)}</span>
</div>
<div class="cards">{''.join(cards)}</div>
<textarea id="out" placeholder="导出后 JSON 显示在这里，复制发给 agent 即可" readonly></textarea>
<script>
  const N = {len(rows)};
  const qids = {json.dumps([r['qid'] for r in rows], ensure_ascii=False)};
  function decided() {{
    let n = 0;
    for (let i = 1; i <= N; i++) {{
      const el = document.querySelector('input[name="d'+i+'"]:checked');
      if (el) n++;
    }}
    document.getElementById('cnt').textContent = '已决定 ' + n + ' / ' + N;
    return n;
  }}
  document.addEventListener('change', e => {{
    if (e.target.type === 'radio' && e.target.name.startsWith('d')) {{
      const i = e.target.name.slice(1);
      document.getElementById('m'+i).textContent = '✓ ' + e.target.value;
      decided();
    }}
  }});
  function allApproved() {{
    for (let i = 1; i <= N; i++) {{
      const el = document.querySelector('input[name="d'+i+'"][value="approved"]');
      if (el) {{ el.checked = true; document.getElementById('m'+i).textContent = '✓ approved'; }}
    }}
    decided();
  }}
  function clearAll() {{
    for (let i = 1; i <= N; i++) {{
      document.querySelectorAll('input[name="d'+i+'"]').forEach(x => x.checked = false);
      document.getElementById('m'+i).textContent = '';
    }}
    decided();
  }}
  function exportJson() {{
    const out = {{}};
    for (let i = 1; i <= N; i++) {{
      const el = document.querySelector('input[name="d'+i+'"]:checked');
      if (el) out[qids[i-1]] = el.value;
    }}
    const json = JSON.stringify(out, null, 0);
    document.getElementById('out').value = json;
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(json).then(() => alert('已复制到剪贴板')).catch(() => alert('复制失败，请手动复制文本框内容'));
    }} else {{
      document.getElementById('out').select();
      alert('请手动复制文本框内容');
    }}
  }}
</script>
</body>
</html>"""
    OUT.write_text(html, encoding="utf-8")
    print(json.dumps({"n": len(rows), "out": str(OUT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
