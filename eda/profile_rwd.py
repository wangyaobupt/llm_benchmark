"""
RWD Benchmark 数据画像 (EDA)
============================
对 data/ 下两个 CSV（原始抽取版 + 清洗版）做探索性数据分析，
产出 Markdown 统计报告 + PNG 分布图表。

用法：
    python eda/profile_rwd.py

输出：
    eda/EDA_REPORT.md
    eda/figures/*.png
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ── 路径 ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
FIG_DIR = PROJECT_ROOT / "eda" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

RAW_CSV = DATA_DIR / "rwd_benchmark_visits.csv"
CLEAN_CSV = DATA_DIR / "rwd_benchmark_visits_cleaned.csv"
REPORT_PATH = PROJECT_ROOT / "eda" / "EDA_REPORT.md"

# 清洗变更的 4 个文本字段
CLEANED_TEXT_FIELDS = [
    "chief_complaint",
    "history_of_present_illness",
    "past_medical_history",
    "medications_on_admission",
]
# 始终为自由文本的字段
FREE_TEXT_FIELDS = CLEANED_TEXT_FIELDS + ["discharge_record"]
# 结构化 JSON 字段
JSON_FIELDS = [
    "investigation_orders",
    "investigation_reports",
    "other_diagnoses",
    "medication_prescriptions",
    "procedures",
]

plt.rcParams.update({
    "figure.dpi": 150,
    "font.size": 10,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "figure.autolayout": True,
})


# ── 工具函数 ─────────────────────────────────────────────
def safe_json_loads(val):
    """安全解析 JSON 字符串，失败返回 None"""
    if pd.isna(val) or str(val).strip() in ("", "nan", "None"):
        return None
    try:
        return json.loads(str(val))
    except (json.JSONDecodeError, TypeError):
        return None


def json_array_len(val):
    """JSON 数组的长度，非数组或解析失败返回 NaN"""
    parsed = safe_json_loads(val)
    if isinstance(parsed, list):
        return len(parsed)
    return np.nan


def inv_report_count(val):
    """investigation_reports nested dict: return lab+rad item count"""
    parsed = safe_json_loads(val)
    if isinstance(parsed, dict):
        return len(parsed.get("laboratory", [])) + len(parsed.get("radiology", []))
    return np.nan


def str_len(val):
    """字符串字符长度，空值返回 0"""
    if pd.isna(val) or str(val).strip() in ("", "nan", "None"):
        return 0
    return len(str(val))


def non_null_count(series):
    """非空计数：排除 NaN、空字符串、字面 'nan'"""
    mask = series.notna() & (series.astype(str).str.strip() != "") & \
           (~series.astype(str).str.strip().isin(["nan", "None", "[]", "{}"]))
    return int(mask.sum())


def fmt_pct(n, total):
    return f"{n} ({n / total * 100:.1f}%)" if total else "0 (0.0%)"


def save_fig(name):
    path = FIG_DIR / f"{name}.png"
    plt.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()
    return path.name


# ── 加载数据 ─────────────────────────────────────────────
print(">>> 加载数据 …")
raw = pd.read_csv(RAW_CSV, dtype=str, low_memory=False)
clean = pd.read_csv(CLEAN_CSV, dtype=str, low_memory=False)

# 数值列转换
for df in (raw, clean):
    df["age_at_encounter"] = pd.to_numeric(df["age_at_encounter"], errors="coerce")

N = len(clean)
report_lines: list[str] = []
report_lines.append("# RWD Benchmark 数据画像报告 (EDA)\n")
report_lines.append(f"> 生成时间：{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} ｜ 数据来源：MIMIC-IV v3.1\n")


# ── 0. 总览 ──────────────────────────────────────────────
print("[0/6] 总览 …")
report_lines.append("\n## 0. 数据总览\n")
report_lines.append(f"| 指标 | 原始版 (raw) | 清洗版 (cleaned) |")
report_lines.append(f"|---|---|---|")
report_lines.append(f"| 行数 | {len(raw)} | {len(clean)} |")
report_lines.append(f"| 列数 | {len(raw.columns)} | {len(clean.columns)} |")
report_lines.append(f"| 文件大小 | {RAW_CSV.stat().st_size / 1e6:.1f} MB | {CLEAN_CSV.stat().st_size / 1e6:.1f} MB |")

# 列级缺失
report_lines.append("\n### 各列非空率\n")
report_lines.append("| # | 字段 | 类型 | 非空数 | 缺失数 | 缺失率 |")
report_lines.append("|---:|---|---|---:|---:|---:|")
for i, col in enumerate(clean.columns, 1):
    nn = non_null_count(clean[col])
    miss = N - nn
    ftype = "JSON" if col in JSON_FIELDS else ("Text" if col in FREE_TEXT_FIELDS else "Scalar")
    report_lines.append(f"| {i} | `{col}` | {ftype} | {nn} | {miss} | {miss / N * 100:.1f}% |")


# ── 1. 人口学 ────────────────────────────────────────────
print("[1/6] 人口学 …")
report_lines.append("\n## 1. 人口学画像\n")
age = clean["age_at_encounter"].dropna()
report_lines.append("### 年龄\n")
report_lines.append(f"| 统计量 | 值 |")
report_lines.append(f"|---|---|")
for label, val in [("样本数", len(age)), ("均值", f"{age.mean():.1f}"),
                    ("标准差", f"{age.std():.1f}"), ("最小值", f"{age.min():.0f}"),
                    ("P25", f"{age.quantile(.25):.0f}"), ("中位数", f"{age.median():.0f}"),
                    ("P75", f"{age.quantile(.75):.0f}"), ("最大值", f"{age.max():.0f}"),
                    ("<18 异常", int((age < 18).sum()))]:
    report_lines.append(f"| {label} | {val} |")

fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
axes[0].hist(age, bins=40, color="#4C72B0", edgecolor="white", linewidth=.5)
axes[0].set_xlabel("Age")
axes[0].set_ylabel("Count")
axes[0].set_title("Age Distribution")
axes[0].axvline(age.median(), color="red", ls="--", lw=1, label=f"Median={age.median():.0f}")
axes[0].legend()

sex_counts = clean["sex"].value_counts()
axes[1].bar(sex_counts.index, sex_counts.values, color=["#4C72B0", "#DD8452"], edgecolor="white")
axes[1].set_title("Sex Distribution")
axes[1].set_ylabel("Count")
for idx, val in zip(sex_counts.index, sex_counts.values):
    axes[1].text(idx, val + 50, f"{val}\n({val/N*100:.1f}%)", ha="center", fontsize=9)
save_fig("01_age_sex")

report_lines.append("\n### 性别\n")
for sx, cnt in sex_counts.items():
    report_lines.append(f"- **{sx}**: {fmt_pct(cnt, N)}")

# 就诊次数
visits_per_pt = clean.groupby("subject_id")["hadm_id"].nunique()
report_lines.append("\n### 患者与就诊次数\n")
report_lines.append(f"| 指标 | 值 |")
report_lines.append(f"|---|---|")
report_lines.append(f"| 独立患者数 | {clean['subject_id'].nunique()} |")
report_lines.append(f"| 人均就诊次数 (均值) | {visits_per_pt.mean():.2f} |")
report_lines.append(f"| 就诊1次的患者 | {fmt_pct((visits_per_pt == 1).sum(), len(visits_per_pt))} |")
report_lines.append(f"| 就诊≥2次的患者 | {fmt_pct((visits_per_pt >= 2).sum(), len(visits_per_pt))} |")
report_lines.append(f"| 最多就诊次数 | {visits_per_pt.max()} |")

fig, ax = plt.subplots(figsize=(8, 4))
vpp = visits_per_pt.value_counts().sort_index()
ax.bar(vpp.index.astype(str), vpp.values, color="#55A868", edgecolor="white")
ax.set_xlabel("Visits per Patient")
ax.set_ylabel("Patient Count")
ax.set_title("Visits per Patient Distribution")
for i, (idx, val) in enumerate(vpp.items()):
    if val > 50:
        ax.text(i, val + 20, str(val), ha="center", fontsize=8)
save_fig("02_visits_per_patient")


# ── 2. 诊断 ──────────────────────────────────────────────
print("[2/6] 诊断 …")
report_lines.append("\n## 2. 诊断分布\n")

icd_ver = clean["primary_icd_version"].value_counts()
report_lines.append("### ICD 版本\n")
for ver, cnt in icd_ver.items():
    report_lines.append(f"- **ICD-{ver}**: {fmt_pct(cnt, N)}")

top_diag = clean["primary_diagnosis_name"].value_counts().head(25)
report_lines.append("\n### Top 25 主诊断\n")
report_lines.append("| # | 诊断名称 | 数量 | 占比 |")
report_lines.append("|---:|---|---:|---:|")
for i, (name, cnt) in enumerate(top_diag.items(), 1):
    short = (name[:60] + "…") if len(str(name)) > 60 else name
    report_lines.append(f"| {i} | {short} | {cnt} | {cnt / N * 100:.1f}% |")

total_unique_diag = clean["primary_diagnosis_name"].nunique()
report_lines.append(f"\n> 独立主诊断名称共 **{total_unique_diag}** 种\n")

fig, ax = plt.subplots(figsize=(12, 7))
top20 = clean["primary_diagnosis_name"].value_counts().head(20)
short_labels = [str(x)[:35] + ("…" if len(str(x)) > 35 else "") for x in top20.index]
ax.barh(range(len(top20)), top20.values[::-1], color="#4C72B0", edgecolor="white")
ax.set_yticks(range(len(top20)))
ax.set_yticklabels(short_labels[::-1], fontsize=8)
ax.set_xlabel("Count")
ax.set_title("Top 20 Primary Diagnoses")
save_fig("03_top_diagnoses")

# other_diagnoses 数量分布
oth_counts = clean["other_diagnoses"].apply(json_array_len)
report_lines.append("\n### 其他诊断 (other_diagnoses) 数量分布\n")
report_lines.append(f"| 统计量 | 值 |")
report_lines.append(f"|---|---|")
report_lines.append(f"| 有其他诊断的就诊 | {fmt_pct(oth_counts.notna().sum() & (oth_counts > 0).sum(), N)} |")
report_lines.append(f"| 平均数量 | {oth_counts.mean():.1f} |")
report_lines.append(f"| 中位数 | {oth_counts.median():.0f} |")
report_lines.append(f"| 最大值 | {oth_counts.max():.0f} |")


# ── 3. 文本字段（raw vs cleaned 对比）────────────────────
print("[3/6] 文本字段对比 …")
report_lines.append("\n## 3. 文本字段：原始 vs 清洗\n")

report_lines.append("### 非空率对比\n")
report_lines.append("| 字段 | 原始非空 | 原始非空率 | 清洗非空 | 清洗非空率 |")
report_lines.append("|---|---:|---:|---:|---:|")
for fld in FREE_TEXT_FIELDS:
    raw_nn = non_null_count(raw[fld])
    cl_nn = non_null_count(clean[fld])
    report_lines.append(f"| `{fld}` | {raw_nn} | {raw_nn/N*100:.1f}% | {cl_nn} | {cl_nn/N*100:.1f}% |")

# 字符长度分布（raw）
report_lines.append("\n### 原始字符长度分布\n")
report_lines.append("| 字段 | 均值 | 中位数 | P90 | 最大值 |")
report_lines.append("|---|---:|---:|---:|---:|")
raw_lens = {}
for fld in FREE_TEXT_FIELDS:
    lens = raw[fld].apply(str_len)
    raw_lens[fld] = lens[lens > 0]
    if len(raw_lens[fld]) > 0:
        report_lines.append(
            f"| `{fld}` | {raw_lens[fld].mean():.0f} | {raw_lens[fld].median():.0f} | "
            f"{raw_lens[fld].quantile(.9):.0f} | {raw_lens[fld].max()} |"
        )
    else:
        report_lines.append(f"| `{fld}` | - | - | - | - |")

fig, axes = plt.subplots(2, 3, figsize=(15, 8))
for idx, fld in enumerate(FREE_TEXT_FIELDS):
    ax = axes[idx // 3][idx % 3]
    lens = raw_lens.get(fld, pd.Series(dtype=float))
    if len(lens) > 0:
        clipped = lens.clip(upper=lens.quantile(.99))
        ax.hist(clipped, bins=40, color="#4C72B0", edgecolor="white", linewidth=.3)
    ax.set_title(fld.replace("_", " ").title(), fontsize=9)
    ax.set_xlabel("Character Length", fontsize=8)
    ax.set_ylabel("Count", fontsize=8)
axes[1][2].axis("off")
save_fig("04_text_length_raw")

# 清洗版 JSON 实体数量
report_lines.append("\n### 清洗后 JSON 实体数量分布\n")
report_lines.append("| 字段 | 有实体的就诊 | 平均实体数 | 中位数 | 最大值 |")
report_lines.append("|---|---:|---:|---:|---:|")
cl_entity_lens = {}
for fld in CLEANED_TEXT_FIELDS:
    lens = clean[fld].apply(json_array_len)
    cl_entity_lens[fld] = lens
    has_entity = int((lens > 0).sum())
    report_lines.append(
        f"| `{fld}` | {fmt_pct(has_entity, N)} | {lens.mean():.1f} | "
        f"{lens.median():.0f} | {lens.max():.0f} |"
    )

fig, axes = plt.subplots(1, 4, figsize=(16, 4))
for idx, fld in enumerate(CLEANED_TEXT_FIELDS):
    ax = axes[idx]
    lens = cl_entity_lens[fld].dropna()
    lens = lens[lens > 0].clip(upper=lens.quantile(.99) if len(lens) > 0 else 0)
    if len(lens) > 0:
        ax.hist(lens, bins=30, color="#55A868", edgecolor="white", linewidth=.3)
    ax.set_title(f"{fld.replace('_', ' ').title()}\n(entities/visit)", fontsize=8)
    ax.set_xlabel("Entity Count", fontsize=8)
save_fig("05_entity_count_cleaned")


# ── 4. 结构化 JSON 字段 ──────────────────────────────────
print("[4/6] 结构化 JSON …")
report_lines.append("\n## 4. 结构化 JSON 字段\n")

report_lines.append("### 项数分布\n")
report_lines.append("| 字段 | 有数据的就诊 | 平均项数 | 中位数 | P90 | 最大值 |")
report_lines.append("|---|---:|---:|---:|---:|---:|")
json_lens = {}
for fld in JSON_FIELDS:
    if fld == "investigation_reports":
        lens = clean[fld].apply(inv_report_count)
    else:
        lens = clean[fld].apply(json_array_len)
    json_lens[fld] = lens
    has_data = int((lens > 0).sum())
    report_lines.append(
        f"| `{fld}` | {fmt_pct(has_data, N)} | {lens.mean():.1f} | "
        f"{lens.median():.0f} | {lens.quantile(.9):.0f} | {lens.max():.0f} |"
    )

fig, axes = plt.subplots(2, 3, figsize=(15, 8))
for idx, fld in enumerate(JSON_FIELDS):
    ax = axes[idx // 3][idx % 3]
    lens = json_lens[fld].dropna()
    lens = lens[lens > 0].clip(upper=lens.quantile(.95) if len(lens) > 0 else 0)
    if len(lens) > 0:
        ax.hist(lens, bins=40, color="#C44E52", edgecolor="white", linewidth=.3)
    ax.set_title(fld.replace("_", " ").title(), fontsize=9)
    ax.set_xlabel("Item Count", fontsize=8)
    ax.set_ylabel("Visits", fontsize=8)
axes[1][2].axis("off")
save_fig("06_json_item_counts")

# investigation_orders Top 类型
report_lines.append("\n### 检查医嘱 (investigation_orders) Top 15 类型\n")
order_types = Counter()
for val in clean["investigation_orders"]:
    parsed = safe_json_loads(val)
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict) and "order_type" in item:
                order_types[item["order_type"]] += 1
            elif isinstance(item, dict) and "type" in item:
                order_types[item["type"]] += 1
report_lines.append("| # | 类型 | 数量 |")
report_lines.append("|---:|---|---:|")
for i, (tp, cnt) in enumerate(order_types.most_common(15), 1):
    report_lines.append(f"| {i} | {tp} | {cnt} |")

# investigation_reports lab/radiology breakdown
report_lines.append("\n### investigation_reports lab/radiology breakdown\n")
lab_counts, rad_counts = [], []
for val in clean["investigation_reports"]:
    parsed = safe_json_loads(val)
    if isinstance(parsed, dict):
        lab_counts.append(len(parsed.get("laboratory", [])))
        rad_counts.append(len(parsed.get("radiology", [])))
    else:
        lab_counts.append(0)
        rad_counts.append(0)
lab_s, rad_s = pd.Series(lab_counts), pd.Series(rad_counts)
report_lines.append("| metric | laboratory | radiology |")
report_lines.append("|---|---:|---:|")
report_lines.append(f"| visits with data | {fmt_pct(int((lab_s>0).sum()), N)} | {fmt_pct(int((rad_s>0).sum()), N)} |")
report_lines.append(f"| mean items | {lab_s.mean():.1f} | {rad_s.mean():.1f} |")
report_lines.append(f"| median | {lab_s.median():.0f} | {rad_s.median():.0f} |")
report_lines.append(f"| max | {lab_s.max()} | {rad_s.max()} |")

# investigation_orders poe_detail emptiness
poe_nn = 0
for val in clean["investigation_orders"]:
    parsed = safe_json_loads(val)
    if isinstance(parsed, list) and any(isinstance(e, dict) and len(e.get("poe_detail", []))>0 for e in parsed):
        poe_nn += 1
report_lines.append(f"\n> WARNING: investigation_orders.poe_detail non-empty in only {poe_nn}/{N} ({poe_nn/N*100:.2f}%) visits.\n")

# medication_prescriptions Top 药物
report_lines.append("\n### 处方 (medication_prescriptions) Top 15 药物\n")
med_names = Counter()
for val in clean["medication_prescriptions"]:
    parsed = safe_json_loads(val)
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                name = item.get("drug") or item.get("medication") or item.get("name")
                if name:
                    med_names[str(name).lower().strip()] += 1
report_lines.append("| # | 药物 | 出现次数 | 就诊占比 |")
report_lines.append("|---:|---|---:|---:|")
for i, (name, cnt) in enumerate(med_names.most_common(15), 1):
    report_lines.append(f"| {i} | {name} | {cnt} | {cnt / N * 100:.1f}% |")

# procedures Top
report_lines.append("\n### 手术/操作 (procedures) Top 15\n")
proc_names = Counter()
for val in clean["procedures"]:
    parsed = safe_json_loads(val)
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                name = item.get("name") or item.get("procedure_name") or item.get("description")
                if name:
                    proc_names[str(name).strip()] += 1
report_lines.append("| # | 操作名称 | 数量 |")
report_lines.append("|---:|---|---:|")
for i, (name, cnt) in enumerate(proc_names.most_common(15), 1):
    short = (name[:55] + "…") if len(name) > 55 else name
    report_lines.append(f"| {i} | {short} | {cnt} |")


# ── 5. 离院记录 ──────────────────────────────────────────
print("[5/6] 离院记录 …")
report_lines.append("\n## 5. 离院记录 (discharge_record)\n")
dr_lens = clean["discharge_record"].apply(str_len)
dr_lens_nz = dr_lens[dr_lens > 0]
report_lines.append(f"| 指标 | 值 |")
report_lines.append(f"|---|---|")
report_lines.append(f"| 非空就诊数 | {fmt_pct(len(dr_lens_nz), N)} |")
report_lines.append(f"| 平均字符长度 | {dr_lens_nz.mean():.0f} |")
report_lines.append(f"| 中位数 | {dr_lens_nz.median():.0f} |")
report_lines.append(f"| P90 | {dr_lens_nz.quantile(.9):.0f} |")
report_lines.append(f"| 最大值 | {dr_lens_nz.max()} |")

fig, ax = plt.subplots(figsize=(8, 4))
clipped = dr_lens_nz.clip(upper=dr_lens_nz.quantile(.99))
ax.hist(clipped, bins=50, color="#8172B3", edgecolor="white", linewidth=.3)
ax.set_xlabel("Character Length")
ax.set_ylabel("Count")
ax.set_title("Discharge Record Length Distribution")
save_fig("07_discharge_length")


# ── 6. 数据质量 ──────────────────────────────────────────
print("[6/6] 数据质量 …")
report_lines.append("\n## 6. 数据质量检查\n")

# 重复 hadm_id
dup_hadm = clean["hadm_id"].duplicated().sum()
report_lines.append(f"| 检查项 | 结果 |")
report_lines.append(f"|---|---|")
report_lines.append(f"| 重复 `hadm_id` | {dup_hadm} |")

# age 异常
age_invalid = clean["age_at_encounter"].isna().sum()
age_minor = (clean["age_at_encounter"] < 18).sum()
report_lines.append(f"| `age` 缺失 | {age_invalid} |")
report_lines.append(f"| `age` < 18 | {age_minor} |")

# 必需字段违规
for fld in ["sex", "chief_complaint", "primary_icd_code", "primary_diagnosis_name"]:
    empty = N - non_null_count(clean[fld])
    report_lines.append(f"| `{fld}` 空值 | {empty} |")

# raw ↔ cleaned 一致性（13 个非清洗列应逐字节相同）
non_cleaned_cols = [c for c in clean.columns if c not in CLEANED_TEXT_FIELDS]
mismatches = {}
for col in non_cleaned_cols:
    diff = (raw[col].fillna("__NA__") != clean[col].fillna("__NA__")).sum()
    if diff > 0:
        mismatches[col] = int(diff)
report_lines.append(f"| 非清洗列不一致行（应=0）| {sum(mismatches.values())} |")
if mismatches:
    report_lines.append(f"\n> ⚠️ 不一致列：{mismatches}\n")
else:
    report_lines.append(f"\n> ✅ 13 个非清洗列 raw↔cleaned 完全一致\n")

# 行数 & ID 顺序一致性
id_match = (raw["hadm_id"].values == clean["hadm_id"].values).all()
report_lines.append(f"| 行顺序 (hadm_id) 一致 | {'✅ 是' if id_match else '❌ 否'} |")

# 清洗失败的行（cleaned JSON 解析失败）
parse_fail = {}
for fld in CLEANED_TEXT_FIELDS:
    nn_raw = non_null_count(raw[fld])
    fail = 0
    for val in clean[fld]:
        if pd.notna(val) and str(val).strip() not in ("", "nan", "None"):
            if safe_json_loads(val) is None:
                fail += 1
    if fail > 0:
        parse_fail[fld] = fail
report_lines.append(f"| 清洗字段 JSON 解析失败 | {sum(parse_fail.values()) if parse_fail else 0} |")
if parse_fail:
    report_lines.append(f"\n> ⚠️ 解析失败明细：{parse_fail}\n")

# 空值最多的列 Top 5
report_lines.append("\n### 缺失率 Top 5\n")
miss_rates = {col: (N - non_null_count(clean[col])) / N * 100 for col in clean.columns}
report_lines.append("| 字段 | 缺失率 |")
report_lines.append("|---|---:|")
for col, rate in sorted(miss_rates.items(), key=lambda x: -x[1])[:5]:
    report_lines.append(f"| `{col}` | {rate:.1f}% |")


# ── 写报告 ───────────────────────────────────────────────
report_lines.append("\n## 7. \u5173\u952e\u53d1\u73b0\u4e0e\u98ce\u9669\n")
report_lines.append("| \u7ea7\u522b | \u53d1\u73b0 | \u5f71\u54cd |")
report_lines.append("|---|---|---|")
report_lines.append("| P0 | `discharge_record` \u5728 raw \u548c cleaned \u4e2d\u5747\u4e3a 100% \u7a7a | \u9898\u578b 5\uff08\u79bb\u9662\u6307\u5bfc\uff09\u5b8c\u5168\u65e0\u6570\u636e\u6765\u6e90\uff1b\u62bd\u53d6\u9636\u6bb5 DS \u7ae0\u8282\u89e3\u6790\u672a\u63d0\u53d6\u5230 Follow-up Instructions |")
report_lines.append("| P1 | `investigation_orders.poe_detail` 99.99% \u4e3a\u7a7a | \u68c0\u67e5\u533b\u5631\u4ec5\u6709\u5206\u7c7b\u6807\u7b7e\uff08\u5982 Lab\uff09\u65e0\u660e\u7ec6\uff1b\u9898\u578b 1 \u987b\u4f9d\u8d56 `investigation_reports` |")
report_lines.append("| P1 | 157 \u6761\u5c31\u8bca `chief_complaint` \u4e3a\u7a7a | \u6570\u636e\u5951\u7ea6\u89c4\u5b9a\u4e3b\u8bc9\u7f3a\u5931\u5e94\u6392\u9664\uff0c\u4f46\u6e05\u6d17\u4ea7\u7269\u4e2d\u4ecd\u4fdd\u7559 |")
report_lines.append("| P2 | `procedures` \u7f3a\u5931\u7387 41.0% | 41% \u5c31\u8bca\u65e0\u624b\u672f/\u64cd\u4f5c\u8bb0\u5f55\uff0c\u5f71\u54cd\u9898\u578b 3 \u64cd\u4f5c\u7c7b\u9898\u76ee |")
report_lines.append("| P2 | ICD-9 \u5360 63%\u3001ICD-10 \u5360 37% | \u4e24\u7248\u7f16\u7801\u4f53\u7cfb\u6df7\u7528\uff0c\u6807\u51c6\u5316\u9700\u6ce8\u610f\u7f16\u7801\u6620\u5c04\u5dee\u5f02 |")
report_lines.append("| P3 | 1 \u4f4d\u60a3\u8005\u6700\u591a\u5c31\u8bca 51 \u6b21 | \u957f\u5c3e\u5206\u5e03\uff0c\u8bc4\u4f30 LLM \u65f6\u9700\u6ce8\u610f\u6570\u636e\u6cc4\u6f0f\u98ce\u9669 |")

report_lines.append("\n---\n")
report_lines.append("## 附：图表清单\n")
for fig_name in sorted(FIG_DIR.glob("*.png")):
    report_lines.append(f"- `eda/figures/{fig_name.name}`")

REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")
print(f"\n>>> 报告已写入: {REPORT_PATH}")
print(f">>> 图表目录: {FIG_DIR}")
print(f">>> 共 {len(list(FIG_DIR.glob('*.png')))} 张图")
