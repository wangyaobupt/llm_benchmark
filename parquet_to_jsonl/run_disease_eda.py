"""Disease distribution EDA: ICD chapter grouping, age/sex cross-tab, comorbidity."""
from __future__ import annotations
import json
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.dpi"] = 150
plt.rcParams["savefig.bbox"] = "tight"
INPUT_PATH = Path("G:/Projects/llm_benchmark/data/rwd_benchmark_visits.jsonl")
OUTPUT_DIR = Path("G:/Projects/llm_benchmark/data/eda")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
C_PRIMARY = "#2563eb"
C_SECONDARY = "#7c3aed"
C_ACCENT = "#059669"
C_WARN = "#dc2626"
C_NEUTRAL = "#6b7280"
PALETTE = ["#2563eb", "#7c3aed", "#059669", "#dc2626", "#d97706", "#0891b2", "#db2777", "#4f46e5",
           "#65a30d", "#ea580c", "#0d9488", "#be185d", "#4338ca", "#b45309", "#047857", "#9f1239"]
# ---------------------------------------------------------------------------
# ICD chapter mapping
# ---------------------------------------------------------------------------
ICD9_CHAPTERS = [
    ("感染与寄生虫病", lambda c: 1 <= _icd9_num(c) <= 139),
    ("肿瘤", lambda c: 140 <= _icd9_num(c) <= 239),
    ("内分泌/代谢/免疫", lambda c: 240 <= _icd9_num(c) <= 279),
    ("血液系统疾病", lambda c: 280 <= _icd9_num(c) <= 289),
    ("精神障碍", lambda c: 290 <= _icd9_num(c) <= 319),
    ("神经系统疾病", lambda c: 320 <= _icd9_num(c) <= 389),
    ("循环系统疾病", lambda c: 390 <= _icd9_num(c) <= 459),
    ("呼吸系统疾病", lambda c: 460 <= _icd9_num(c) <= 519),
    ("消化系统疾病", lambda c: 520 <= _icd9_num(c) <= 579),
    ("泌尿生殖系统疾病", lambda c: 580 <= _icd9_num(c) <= 629),
    ("妊娠/分娩/产褥期", lambda c: 630 <= _icd9_num(c) <= 679),
    ("皮肤及皮下组织疾病", lambda c: 680 <= _icd9_num(c) <= 709),
    ("肌肉骨骼系统疾病", lambda c: 710 <= _icd9_num(c) <= 739),
    ("先天异常", lambda c: 740 <= _icd9_num(c) <= 759),
    ("症状/体征/不确定", lambda c: 780 <= _icd9_num(c) <= 799),
    ("损伤与中毒", lambda c: 800 <= _icd9_num(c) <= 999),
    ("外部原因", lambda c: c.upper().startswith("E")),
]
ICD10_CHAPTERS = [
    ("感染与寄生虫病", lambda c: "A" <= c[0] <= "B"),
    ("肿瘤", lambda c: c[0] == "C" or ("D" <= c <= "D49")),
    ("血液系统疾病", lambda c: "D50" <= c <= "D89"),
    ("内分泌/代谢/免疫", lambda c: "E" <= c[0] <= "E"),
    ("精神障碍", lambda c: c[0] == "F"),
    ("神经系统疾病", lambda c: c[0] == "G"),
    ("眼及附器疾病", lambda c: "H00" <= c <= "H59"),
    ("耳及乳突疾病", lambda c: "H60" <= c <= "H95"),
    ("循环系统疾病", lambda c: c[0] == "I"),
    ("呼吸系统疾病", lambda c: c[0] == "J"),
    ("消化系统疾病", lambda c: c[0] == "K"),
    ("皮肤及皮下组织疾病", lambda c: c[0] == "L"),
    ("肌肉骨骼系统疾病", lambda c: c[0] == "M"),
    ("泌尿生殖系统疾病", lambda c: c[0] == "N"),
    ("妊娠/分娩/产褥期", lambda c: c[0] == "O"),
    ("围产期情况", lambda c: c[0] == "P"),
    ("先天异常", lambda c: c[0] == "Q"),
    ("症状/体征/不确定", lambda c: c[0] == "R"),
    ("损伤/中毒/外因后果", lambda c: c[0] in ("S", "T")),
    ("外因致病", lambda c: c[0] in ("V", "W", "X", "Y")),
    ("健康状态影响因素", lambda c: c[0] == "Z"),
]
def _icd9_num(code: str) -> int:
    """Extract first-3-digit numeric prefix from ICD-9 code for chapter lookup."""
    m = re.match(r"^[EV]?(\d{1,3})", code.upper())
    return int(m.group(1)) if m else 0
def classify_chapter(icd_code: str, icd_version: str) -> str:
    """Map an ICD code to a chapter name."""
    code = (icd_code or "").strip().upper()
    if not code:
        return "未分类"
    if "9" in (icd_version or ""):
        for name, fn in ICD9_CHAPTERS:
            if fn(code):
                return name
    else:
        for name, fn in ICD10_CHAPTERS:
            try:
                if fn(code):
                    return name
            except (IndexError, TypeError):
                continue
    return "未分类"
def stream_disease_stats():
    """Single pass: collect disease-related stats."""
    logger.info("Streaming disease stats from %s ...", INPUT_PATH)
    n = 0
    primary_dx_names = Counter()
    primary_chapters = Counter()
    # chapter x age bracket
    chapter_by_age = defaultdict(Counter)  # chapter -> Counter(age_bracket)
    chapter_by_sex = defaultdict(Counter)  # chapter -> Counter(sex)
    # top diagnoses by chapter (for top-N within each chapter)
    dx_in_chapter = defaultdict(Counter)  # chapter -> Counter(dx_name)
    # comorbidity: co-occurring "other" diagnoses (top-level, sampled)
    other_dx_counter = Counter()
    # per-visit chapter set for co-occurrence
    chapter_cooccur = Counter()  # frozenset of 2 chapters -> count
    # comorbidity count (other diagnoses per visit)
    comorbidity_counts = []
    age_sex_primary = []  # (age, sex, chapter) for cross-tab
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            v = json.loads(line)
            n += 1
            if n % 50000 == 0:
                logger.info("  ...processed %d records", n)
            dx = v.get("diagnoses", {})
            pdx = dx.get("primary") or {}
            icd_code = pdx.get("icd_code", "")
            icd_ver = pdx.get("icd_version", "")
            dx_name = pdx.get("diagnosis_name", "")
            chapter = classify_chapter(icd_code, icd_ver)
            primary_dx_names[dx_name] += 1
            primary_chapters[chapter] += 1
            dx_in_chapter[chapter][dx_name] += 1
            # demographics
            demo = v.get("demographics", {})
            age = demo.get("age_at_encounter", 0)
            sex = demo.get("sex", "?")
            if 18 <= age < 30:
                ab = "18-29"
            elif 30 <= age < 45:
                ab = "30-44"
            elif 45 <= age < 60:
                ab = "45-59"
            elif 60 <= age < 75:
                ab = "60-74"
            else:
                ab = "75+"
            chapter_by_age[chapter][ab] += 1
            chapter_by_sex[chapter][sex] += 1
            age_sex_primary.append((age, sex, chapter))
            # other diagnoses
            others = dx.get("other", [])
            comorbidity_counts.append(len(others))
            # collect all chapters for this visit (primary + map others)
            visit_chapters = {chapter}
            for odx in others:
                other_dx_counter[odx] += 1
            # chapter co-occurrence (limit pairs to avoid explosion)
            # We use the primary chapter + sample of others as chapter names
            # Actually we don't have ICD codes for "other" dx (only names), so skip co-occurrence
    logger.info("Streaming complete: %d records", n)
    return {
        "n": n,
        "primary_dx_names": primary_dx_names,
        "primary_chapters": primary_chapters,
        "chapter_by_age": chapter_by_age,
        "chapter_by_sex": chapter_by_sex,
        "dx_in_chapter": dx_in_chapter,
        "other_dx_counter": other_dx_counter,
        "comorbidity_counts": np.array(comorbidity_counts),
        "age_sex_primary": age_sex_primary,
    }
def _save(fig, name):
    path = OUTPUT_DIR / name
    fig.savefig(path)
    plt.close(fig)
    logger.info("Saved %s", path)
def plot_chapter_overview(d):
    """Overall ICD chapter distribution."""
    n = d["n"]
    chapters = d["primary_chapters"]
    sorted_ch = chapters.most_common()
    labels = [k for k, _ in sorted_ch]
    values = [v for _, v in sorted_ch]
    fig, axes = plt.subplots(1, 2, figsize=(18, 9))
    fig.suptitle(f"主诊断 ICD 章节分布 (N={n:,})", fontsize=14, fontweight="bold")
    # Horizontal bar
    ax = axes[0]
    colors_ch = [PALETTE[i % len(PALETTE)] for i in range(len(labels))]
    bars = ax.barh(range(len(labels)), values, color=colors_ch, edgecolor="white", linewidth=0.5)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("人数", fontsize=10)
    ax.set_title("各章节就诊人数", fontsize=12, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val:,} ({val/n*100:.1f}%)", va="center", fontsize=7)
    # Pie chart (top 10 + Other)
    ax = axes[1]
    top10 = sorted_ch[:10]
    pie_labels = [k for k, _ in top10] + ["其他"]
    pie_values = [v for _, v in top10] + [sum(v for _, v in sorted_ch[10:])]
    pie_colors = [PALETTE[i % len(PALETTE)] for i in range(len(pie_labels))]
    wedges, texts, autotexts = ax.pie(pie_values, labels=pie_labels, autopct="%1.1f%%",
                                       colors=pie_colors, startangle=90, textprops={"fontsize": 8})
    for t in autotexts:
        t.set_fontsize(7)
    ax.set_title("章节占比", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    _save(fig, "12_disease_chapters.png")
def plot_chapter_by_age(d):
    """Chapter distribution by age bracket — stacked bar."""
    n = d["n"]
    chapters_sorted = [k for k, _ in d["primary_chapters"].most_common(12)]
    age_brackets = ["18-29", "30-44", "45-59", "60-74", "75+"]
    # Build matrix: chapter x age_bracket
    matrix = np.zeros((len(chapters_sorted), len(age_brackets)))
    for i, ch in enumerate(chapters_sorted):
        for j, ab in enumerate(age_brackets):
            matrix[i, j] = d["chapter_by_age"].get(ch, {}).get(ab, 0)
    # Convert to percentage within each age bracket
    col_sums = matrix.sum(axis=0)
    matrix_pct = matrix / col_sums * 100
    fig, axes = plt.subplots(1, 2, figsize=(18, 9))
    fig.suptitle("各年龄段疾病章节分布", fontsize=14, fontweight="bold")
    # Absolute counts stacked bar
    ax = axes[0]
    bottom = np.zeros(len(age_brackets))
    for i, ch in enumerate(chapters_sorted):
        ax.bar(age_brackets, matrix[i], bottom=bottom, label=ch,
               color=PALETTE[i % len(PALETTE)], edgecolor="white", linewidth=0.3)
        bottom += matrix[i]
    ax.set_xlabel("年龄段", fontsize=10)
    ax.set_ylabel("人数", fontsize=10)
    ax.set_title("各年龄段就诊人数 (绝对值)", fontsize=11, fontweight="bold")
    ax.legend(fontsize=7, loc="upper left", ncol=2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    # Percentage stacked bar
    ax = axes[1]
    bottom = np.zeros(len(age_brackets))
    for i, ch in enumerate(chapters_sorted):
        ax.bar(age_brackets, matrix_pct[i], bottom=bottom, label=ch,
               color=PALETTE[i % len(PALETTE)], edgecolor="white", linewidth=0.3)
        bottom += matrix_pct[i]
    ax.set_xlabel("年龄段", fontsize=10)
    ax.set_ylabel("占比 (%)", fontsize=10)
    ax.set_title("各年龄段疾病构成 (百分比)", fontsize=11, fontweight="bold")
    ax.legend(fontsize=7, loc="upper left", ncol=2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    _save(fig, "13_chapter_by_age.png")
def plot_chapter_by_sex(d):
    """Chapter distribution by sex."""
    chapters_sorted = [k for k, _ in d["primary_chapters"].most_common(12)]
    male_counts = [d["chapter_by_sex"].get(ch, {}).get("M", 0) for ch in chapters_sorted]
    female_counts = [d["chapter_by_sex"].get(ch, {}).get("F", 0) for ch in chapters_sorted]
    # Normalize to percentage
    total_m = sum(male_counts)
    total_f = sum(female_counts)
    male_pct = [v / total_m * 100 for v in male_counts]
    female_pct = [v / total_f * 100 for v in female_counts]
    fig, ax = plt.subplots(figsize=(14, 9))
    y = np.arange(len(chapters_sorted))
    bar_height = 0.35
    bars_f = ax.barh(y - bar_height / 2, female_pct, bar_height, color=C_WARN, label=f"女性 (n={total_f:,})", edgecolor="white", linewidth=0.5)
    bars_m = ax.barh(y + bar_height / 2, male_pct, bar_height, color=C_PRIMARY, label=f"男性 (n={total_m:,})", edgecolor="white", linewidth=0.5)
    ax.set_yticks(y)
    ax.set_yticklabels(chapters_sorted, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("占同性别人群就诊比例 (%)", fontsize=10)
    ax.set_title("各疾病章节性别分布对比", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for bar, val in zip(bars_f, female_pct):
        ax.text(bar.get_width() + 0.2, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}%", va="center", fontsize=7, color=C_WARN)
    for bar, val in zip(bars_m, male_pct):
        ax.text(bar.get_width() + 0.2, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}%", va="center", fontsize=7, color=C_PRIMARY)
    fig.tight_layout()
    _save(fig, "14_chapter_by_sex.png")
def plot_top_dx_per_chapter(d):
    """Top 5 diagnoses within each of the top 6 chapters."""
    top_chapters = [k for k, _ in d["primary_chapters"].most_common(6)]
    fig, axes = plt.subplots(2, 3, figsize=(20, 12))
    fig.suptitle("各主要疾病章节内 Top 5 具体诊断", fontsize=14, fontweight="bold", y=0.98)
    for idx, ch in enumerate(top_chapters):
        row, col = divmod(idx, 3)
        ax = axes[row][col]
        top5 = d["dx_in_chapter"].get(ch, Counter()).most_common(5)
        labels = [k[:45] for k, _ in top5]
        values = [v for _, v in top5]
        bars = ax.barh(range(len(labels)), values, color=PALETTE[idx % len(PALETTE)],
                       edgecolor="white", linewidth=0.5)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=8)
        ax.invert_yaxis()
        ax.set_title(f"{ch}\n(总 {d['primary_chapters'][ch]:,} 例)", fontsize=10, fontweight="bold")
        ax.set_xlabel("人数", fontsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        for bar, val in zip(bars, values):
            ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                    f"{val:,}", va="center", fontsize=7)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    _save(fig, "15_top_dx_per_chapter.png")
def plot_comorbidity(d):
    """Comorbidity count distribution + top 20 other diagnoses."""
    n = d["n"]
    cc = d["comorbidity_counts"]
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    fig.suptitle(f"合并症分析 (N={n:,})", fontsize=14, fontweight="bold")
    # Histogram
    ax = axes[0]
    p99 = int(np.percentile(cc, 99))
    ax.hist(cc, bins=range(0, p99 + 1), color=C_SECONDARY, edgecolor="white", linewidth=0.3)
    ax.axvline(np.median(cc), color=C_WARN, linestyle="--", linewidth=1.5,
               label=f"中位数 {np.median(cc):.0f}")
    ax.axvline(np.mean(cc), color=C_ACCENT, linestyle=":", linewidth=1.5,
               label=f"均值 {np.mean(cc):.1f}")
    ax.set_xlabel("其他诊断数量/visit", fontsize=10)
    ax.set_ylabel("人数", fontsize=10)
    ax.set_title("合并症数量分布", fontsize=11, fontweight="bold")
    ax.legend(fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    # Top 20 other diagnoses
    ax = axes[1]
    top20 = d["other_dx_counter"].most_common(20)
    labels = [k[:40] for k, _ in top20]
    values = [v for _, v in top20]
    bars = ax.barh(range(len(labels)), values, color=C_ACCENT, edgecolor="white", linewidth=0.5)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel("出现次数", fontsize=9)
    ax.set_title("最常见合并症 Top 20", fontsize=11, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val:,}", va="center", fontsize=6)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    _save(fig, "16_comorbidity.png")
def plot_top50_diagnoses(d):
    """Top 50 primary diagnoses as horizontal bar."""
    n = d["n"]
    top50 = d["primary_dx_names"].most_common(50)
    labels = [k[:50] for k, _ in top50]
    values = [v for _, v in top50]
    fig, ax = plt.subplots(figsize=(14, 20))
    colors_bar = [PALETTE[i % len(PALETTE)] for i in range(len(labels))]
    bars = ax.barh(range(len(labels)), values, color=colors_bar, edgecolor="white", linewidth=0.3)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel("人数", fontsize=10)
    ax.set_title(f"主诊断 Top 50 (N={n:,})", fontsize=14, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val:,} ({val/n*100:.2f}%)", va="center", fontsize=6)
    fig.tight_layout()
    _save(fig, "17_top50_diagnoses.png")
def plot_chapter_heatmap(d):
    """Heatmap: ICD chapter x age bracket (percentage within chapter)."""
    chapters_sorted = [k for k, _ in d["primary_chapters"].most_common()]
    age_brackets = ["18-29", "30-44", "45-59", "60-74", "75+"]
    matrix = np.zeros((len(chapters_sorted), len(age_brackets)))
    for i, ch in enumerate(chapters_sorted):
        total_ch = d["primary_chapters"].get(ch, 1)
        for j, ab in enumerate(age_brackets):
            matrix[i, j] = d["chapter_by_age"].get(ch, {}).get(ab, 0) / total_ch * 100
    fig, ax = plt.subplots(figsize=(10, max(8, len(chapters_sorted) * 0.45)))
    im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(len(age_brackets)))
    ax.set_xticklabels(age_brackets, fontsize=10)
    ax.set_yticks(range(len(chapters_sorted)))
    ax.set_yticklabels(chapters_sorted, fontsize=8)
    ax.set_xlabel("年龄段", fontsize=11)
    ax.set_title("各疾病章节内年龄分布 (%)", fontsize=13, fontweight="bold")
    for i in range(len(chapters_sorted)):
        for j in range(len(age_brackets)):
            val = matrix[i, j]
            color = "white" if val > 40 else "black"
            ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=7, color=color)
    fig.colorbar(im, ax=ax, shrink=0.6, label="占该章节 (%)")
    fig.tight_layout()
    _save(fig, "18_chapter_age_heatmap.png")
def main():
    d = stream_disease_stats()
    n = d["n"]
    logger.info("Disease stats complete. Generating plots...")
    plot_chapter_overview(d)
    plot_chapter_by_age(d)
    plot_chapter_by_sex(d)
    plot_top_dx_per_chapter(d)
    plot_comorbidity(d)
    plot_top50_diagnoses(d)
    plot_chapter_heatmap(d)
    logger.info("All disease plots generated in %s", OUTPUT_DIR)
    # Summary
    print(f"\n{'='*60}")
    print(f"疾病分布分析: {n:,} visits")
    print(f"{'='*60}")
    print(f"\nTop 10 疾病章节:")
    for ch, cnt in d["primary_chapters"].most_common(10):
        print(f"  {ch:25s} {cnt:>7,} ({cnt/n*100:5.1f}%)")
    print(f"\nTop 10 主诊断:")
    for name, cnt in d["primary_dx_names"].most_common(10):
        print(f"  {cnt:>5,}x  {name[:60]}")
    print(f"\n合并症: 均值 {np.mean(d['comorbidity_counts']):.1f}, 中位数 {np.median(d['comorbidity_counts']):.0f}")
if __name__ == "__main__":
    main()
