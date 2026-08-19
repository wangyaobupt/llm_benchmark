# -*- coding: utf-8 -*-
"""Diagnosis scan: why investigation_selection can only yield simple questions.

量化四个环节：
1) 检验项目级住院覆盖率（平坦顶部 / 长尾）
2) panel 级基线覆盖率 vs 出题阈值带 [0.02, 0.85]（复用任务自己的 LAB_PANEL_MAP）
3) 主诉（symptom_reported）支撑度分布（condition 空间塌缩）
4) 模拟 top 主诉 -> panel 的 share/gap/lift（min_share_gap=0.10 唯一性过滤的杀伤力）
5) 影像模态级 & 临床监护 allowlist 的基线覆盖
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
OUT = Path(r"D:\Projects\llm_benchmark\eda\coronary_all_three_modules_full\investigation_bottleneck_metrics.json")

sys.path.insert(0, r"D:\Projects\llm_benchmark\tasks\investigation_selection\src")
from pipeline import CLINICAL_ORDER_ALLOWLIST, IMAGING_ALLOWLIST, LAB_PANEL_MAP  # noqa: E402

COLUMNS = ["event_kind", "hadm_id", "concept_id", "preferred_name", "source_label", "entity_type"]

t0 = time.time()
sys.stdout.reconfigure(encoding="utf-8")

hadms_all: set[str] = set()
test_hadms: dict[str, set[str]] = defaultdict(set)       # concept_id -> hadms
test_name: dict[str, str] = {}                            # concept_id -> preferred_name
panel_hadms: dict[str, set[str]] = defaultdict(set)       # panel -> hadms
hadm_panels: dict[str, set[str]] = defaultdict(set)       # hadm -> panels (mapped only)
cc_rows: Counter = Counter()                              # symptom label -> rows
hadm_cc: dict[str, str] = {}                              # hadm -> first CC
img_hadms: dict[str, set[str]] = defaultdict(set)         # imaging label -> hadms
clin_hadms: dict[str, set[str]] = defaultdict(set)        # clinical allowlist label -> hadms

pf = pq.ParquetFile(EVENTS)
n = 0
for batch in pf.iter_batches(batch_size=300_000, columns=COLUMNS):
    d = batch.to_pydict()
    for i in range(len(d["event_kind"])):
        kind = d["event_kind"][i]
        hadm = d["hadm_id"][i]
        if kind == "laboratory_resulted":
            hadms_all.add(hadm)
            cid = d["concept_id"][i]
            if cid:
                test_hadms[cid].add(hadm)
                pn = d["preferred_name"][i]
                if pn:
                    test_name[cid] = pn
                panel = LAB_PANEL_MAP.get(cid)
                if panel:
                    panel_hadms[panel].add(hadm)
                    hadm_panels[hadm].add(panel)
        elif kind == "symptom_reported":
            lbl = d["source_label"][i]
            if lbl:
                cc_rows[lbl] += 1
                if hadm not in hadm_cc:
                    hadm_cc[hadm] = lbl
        elif kind == "imaging_ordered" and d["entity_type"][i] == "imaging_study":
            lbl = d["source_label"][i]
            if lbl:
                img_hadms[lbl].add(hadm)
        elif kind == "clinical_ordered" and d["source_label"][i] in CLINICAL_ORDER_ALLOWLIST:
            clin_hadms[d["source_label"][i]].add(hadm)
        elif kind in ("condition_recorded_post_hoc", "medication_ordered", "medication_administered"):
            hadms_all.add(hadm)
    n += batch.num_rows
    if n % 5_000_000 < 300_000:
        print(f"  {n:,} rows, {time.time()-t0:.0f}s", flush=True)

N = len(hadms_all | set(hadm_cc) | set(hadm_panels))
N = max(N, 39036)
print(f"scanned {n:,} rows in {time.time()-t0:.0f}s; hadm universe={N}")

# ---- 1) 项目级覆盖 --------------------------------------------------------
cov = sorted(((len(s) / N, test_name.get(cid, cid), cid, len(s)) for cid, s in test_hadms.items()), reverse=True)
top20 = [(name, cov_, f"{cov_:.3f}") for cov_, name, cid, k in cov[:20]]
n_tests = len(cov)
n_ge50 = sum(1 for c, *_ in cov if c >= 0.50)
n_ge85 = sum(1 for c, *_ in cov if c >= 0.85)
n_band = sum(1 for c, *_ in cov if 0.02 <= c < 0.50)
n_lt2 = sum(1 for c, *_ in cov if c < 0.02)

# BMP 五项联合覆盖（Glucose/K/Na/Cl/Creatinine 同住院全部出现）
want = {"Glucose", "Potassium", "Sodium", "Chloride", "Creatinine"}
sets = [s for cid, s in test_hadms.items() if test_name.get(cid) in want]
joint = set.intersection(*sets) if sets else set()

# ---- 2) panel 级基线 ------------------------------------------------------
panels = []
for p, s in panel_hadms.items():
    c = len(s) / N
    verdict = "excluded: >max_baseline 0.85" if c > 0.85 else ("excluded: <min_baseline 0.02" if c < 0.02 else "in candidate band")
    panels.append({"panel": p, "n_adm": len(s), "baseline": round(c, 4), "verdict": verdict})
panels.sort(key=lambda x: -x["n_adm"])
mapped_tests = sum(len(s) for s in test_hadms.values())
in_band = [p for p in panels if p["verdict"] == "in candidate band"]

# ---- 3) 主诉支撑度 -------------------------------------------------------
cc_support_ge10 = sum(1 for v in cc_rows.values() if v >= 10)
cc_support_ge50 = sum(1 for v in cc_rows.values() if v >= 50)
cc_dist = {
    "distinct_cc": len(cc_rows),
    "support_ge10": cc_support_ge10,
    "support_ge50": cc_support_ge50,
    "top20": cc_rows.most_common(20),
}

# ---- 4) top 主诉 -> panel 的 share / gap / lift --------------------------
sim = []
for cc, sup in cc_rows.most_common(25):
    if sup < 50:
        continue
    cc_hadms = {h for h, c in hadm_cc.items() if c == cc}
    if not cc_hadms:
        continue
    shares = {}
    for p, s in panel_hadms.items():
        inter = len(s & cc_hadms)
        if inter:
            shares[p] = inter / len(cc_hadms)
    if not shares:
        continue
    ranked = sorted(shares.items(), key=lambda x: -x[1])
    p1, s1 = ranked[0]
    p2, s2 = ranked[1] if len(ranked) > 1 else (None, 0.0)
    base1 = len(panel_hadms[p1]) / N
    lift1 = s1 / base1 if base1 > 0 else 0
    gap = s1 - s2
    passes = (gap >= 0.10) and (lift1 >= 1.5) and (s1 >= 0.15) and (0.02 <= base1 <= 0.85)
    sim.append({
        "cc": cc, "support": sup,
        "top1_panel": p1, "top1_share": round(s1, 3), "top1_lift": round(lift1, 2),
        "top2_panel": p2, "top2_share": round(s2, 3), "gap": round(gap, 3),
        "would_pass_filters": passes,
    })
n_pass = sum(1 for r in sim if r["would_pass_filters"])

# ---- 5) 影像 / 临床监护基线 ----------------------------------------------
img = [{"label": k, "n_adm": len(s), "coverage": round(len(s) / N, 4), "first_line": k in IMAGING_ALLOWLIST}
       for k, s in sorted(img_hadms.items(), key=lambda x: -len(x[1]))]
clin = [{"label": k, "n_adm": len(s), "coverage": round(len(s) / N, 4)} for k, s in sorted(clin_hadms.items(), key=lambda x: -len(x[1]))]

out = {
    "meta": {"hadm_universe": N, "rows_scanned": n, "seconds": round(time.time() - t0, 1)},
    "test_level": {
        "n_tests": n_tests, "n_coverage_ge_50pct": n_ge50, "n_coverage_ge_85pct": n_ge85,
        "n_band_2_50pct": n_band, "n_below_2pct": n_lt2,
        "top20": top20,
        "bmp5_joint_coverage": round(len(joint) / N, 4),
    },
    "panel_level": {"panels": panels, "n_in_band": len(in_band), "mapped_tests_rows": mapped_tests},
    "cc_support": cc_dist,
    "cc_panel_simulation": {"results": sim, "n_pass": n_pass, "n_considered": len(sim)},
    "imaging": img, "clinical_allowlist": clin,
}
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"written {OUT}")

print("\n=== TEST-LEVEL coverage ===")
print(f"tests={n_tests}, >=50%: {n_ge50}, >=85%: {n_ge85}, 2-50%: {n_band}, <2%: {n_lt2}")
print("top10:", [(t, f"{c:.1%}") for t, c, _ in top20[:10]])
print(f"BMP5 joint (Glu+K+Na+Cl+Cr same hadm): {len(joint)/N:.1%}")
print("\n=== PANEL baseline ===")
for p in panels:
    print(f"  {p['panel']:<20} {p['n_adm']:>6,}  {p['baseline']:.1%}  {p['verdict']}")
print("\n=== CC support ===")
print(f"distinct={cc_dist['distinct_cc']}, >=10: {cc_support_ge10}, >=50: {cc_support_ge50}")
print("\n=== CC->panel simulation (top CCs) ===")
for r in sim:
    print(f"  {r['cc'][:34]:<34} sup={r['support']:>5}  top1={r['top1_panel']}({r['top1_share']:.2f},lift {r['top1_lift']})  top2={r['top2_panel']}({r['top2_share']:.2f})  gap={r['gap']:.2f}  pass={r['would_pass_filters']}")
print(f"pass {n_pass}/{len(sim)}")
print("\n=== imaging modality ===")
for r in img[:10]:
    print(f"  {r['label']:<28} {r['coverage']:.1%}  first_line={r['first_line']}")
print("=== clinical allowlist ===")
for r in clin:
    print(f"  {r['label']:<28} {r['coverage']:.1%}")
