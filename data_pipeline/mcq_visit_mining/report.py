"""HTML summary without source notes or hadm lists."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any


def write_family_report(path: Path, summary: dict[str, Any], accepted: list[dict[str, Any]]) -> None:
    rows = []
    for rule in accepted[:50]:
        condition = "; ".join(rule.get("condition_display_names") or [])
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(rule.get('rule_id')))}</td>"
            f"<td>{html.escape(condition)}</td>"
            f"<td>{html.escape(str(rule.get('target_outcome_name')))}</td>"
            f"<td>{rule.get('n_x')}</td>"
            f"<td>{rule.get('n_xy')}</td>"
            f"<td>{rule.get('smoothed_probability')}</td>"
            f"<td>{rule.get('lift')}</td>"
            f"<td>{rule.get('fdr_q')}</td>"
            "</tr>"
        )
    table = "\n".join(rows) or '<tr><td colspan="8">no accepted rules</td></tr>'
    isolation = summary.get("isolation") or {}
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(str(summary.get('family')))} mining</title>
<style>
body {{ font-family: sans-serif; margin: 1.5rem; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #ccc; padding: 0.4rem; text-align: left; }}
.muted {{ color: #555; }}
</style></head><body>
<h1>{html.escape(str(summary.get('family')))}</h1>
<p class="muted">exploratory_unreviewed · gold=0 · profile={html.escape(str(summary.get('profile')))}</p>
<ul>
<li>transactions: {summary.get('transactions')}</li>
<li>tested pairs: {summary.get('tested_pairs')}</li>
<li>accepted: {summary.get('accepted')}</li>
<li>rejected: {summary.get('rejected')}</li>
<li>allowed X: {html.escape(', '.join(isolation.get('allowed_feature_types') or []))}</li>
<li>forbidden X: {html.escape(', '.join(isolation.get('forbidden_feature_types') or []))}</li>
</ul>
<h2>Accepted (up to 50, standard names only)</h2>
<table>
<thead><tr><th>rule</th><th>X</th><th>y</th><th>n_x</th><th>n_xy</th><th>smoothed</th><th>lift</th><th>q</th></tr></thead>
<tbody>
{table}
</tbody></table>
</body></html>
"""
    path.write_text(body, encoding="utf-8")
