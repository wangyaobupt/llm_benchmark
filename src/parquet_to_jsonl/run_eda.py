"""Full-dataset EDA: stream 27GB JSONL, aggregate stats, generate plots."""
from __future__ import annotations
import json
import logging
import os
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
PALETTE = ["#2563eb", "#7c3aed", "#059669", "#dc2626", "#d97706", "#0891b2", "#db2777", "#4f46e5"]
def stream_aggregate():
    """Single pass over JSONL: collect all statistics."""
    logger.info("Starting streaming aggregation over %s ...", INPUT_PATH)
    n = 0
    ages = []
    sexes = Counter()
    admission_types = Counter()
    vital_arrays = {k: [] for k in ("temperature", "heartrate", "resprate", "o2sat", "sbp", "dbp", "acuity")}
    has_any_vital = 0
    rhythm_counter = Counter()
    text_len_arrays = {k: [] for k in (
        "chief_complaint", "history_of_present_illness", "past_medical_history",
        "medications_on_admission", "allergies", "physical_exam",
        "discharge_note_full", "brief_hospital_course", "discharge_record",
    )}
    icd_versions = Counter()
    other_dx_counts = []
    primary_dx_names = Counter()
    lab_item_counts = []
    lab_result_counts = []
    lab_labels = Counter()
    micro_counts = []
    spec_types = Counter()
    org_names = Counter()
    rad_counts = []
    exam_types = Counter()
    rx_counts = []
    pharm_counts = []
    emar_counts = []
    proc_counts = []
    hcpcs_counts = []
    drug_names = Counter()
    disc_locations = Counter()
    adm_locations = Counter()
    primary_services = Counter()
    has_drg = 0
    has_icu = 0
    transfer_steps = []
    home_med_counts = []
    fill_track = Counter()
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            v = json.loads(line)
            n += 1
            if n % 50000 == 0:
                logger.info("  ...processed %d records", n)
            demo = v.get("demographics", {})
            age = demo.get("age_at_encounter")
            if age is not None:
                ages.append(age)
            sexes[demo.get("sex", "?")] += 1
            admission_types[demo.get("admission_type") or "UNKNOWN"] += 1
            hm = demo.get("home_medications", [])
            home_med_counts.append(len(hm))
            vit = v.get("vitals", {})
            vit_any = False
            for vk in vital_arrays:
                val = vit.get(vk)
                if val is not None:
                    vital_arrays[vk].append(val)
                    vit_any = True
            if vit_any:
                has_any_vital += 1
            rhythm = vit.get("rhythm")
            if rhythm:
                rhythm_counter[rhythm] += 1
            narr = v.get("narrative", {})
            for tk in text_len_arrays:
                txt = narr.get(tk) or ""
                text_len_arrays[tk].append(len(txt))
            dx = v.get("diagnoses", {})
            pdx = dx.get("primary") or {}
            if pdx.get("icd_version"):
                icd_versions[pdx["icd_version"]] += 1
            if pdx.get("diagnosis_name"):
                primary_dx_names[pdx["diagnosis_name"]] += 1
            other_dx_counts.append(len(dx.get("other", [])))
            inv = v.get("investigations", {})
            labs = inv.get("laboratory", [])
            lab_item_counts.append(len(labs))
            total_results = 0
            for lab in labs:
                lab_labels[lab.get("label", "?")] += 1
                total_results += len(lab.get("results", []))
            lab_result_counts.append(total_results)
            micros = inv.get("microbiology", [])
            micro_counts.append(len(micros))
            for m in micros:
                if m.get("spec_type_desc"):
                    spec_types[m["spec_type_desc"]] += 1
                if m.get("org_name"):
                    org_names[m["org_name"]] += 1
            rads = inv.get("radiology", [])
            rad_counts.append(len(rads))
            for r in rads:
                exam_types[r.get("exam_name", "?")] += 1
            tr = v.get("treatments", {})
            rx_counts.append(len(tr.get("medications", [])))
            pharm_counts.append(len(tr.get("pharmacy_orders", [])))
            emar_counts.append(len(tr.get("medication_administrations", [])))
            proc_counts.append(len(tr.get("procedures", [])))
            hcpcs_counts.append(len(tr.get("hcpcs", [])))
            for rx in tr.get("medications", []):
                if rx.get("drug"):
                    drug_names[rx["drug"]] += 1
            disp = v.get("disposition", {})
            disc_locations[disp.get("discharge_location") or "UNKNOWN"] += 1
            adm_locations[disp.get("admission_location") or "UNKNOWN"] += 1
            svc = disp.get("primary_service")
            if svc:
                primary_services[svc] += 1
            if disp.get("drg"):
                has_drg += 1
            icu = disp.get("icu_stays", [])
            if icu:
                has_icu += 1
            transfer_steps.append(len(disp.get("transfer_path", [])))
            checks = {
                "age": age is not None,
                "any_vital": vit_any,
                "chief_complaint": bool((narr.get("chief_complaint") or "").strip()),
                "HPI": bool((narr.get("history_of_present_illness") or "").strip()),
                "PMH": bool((narr.get("past_medical_history") or "").strip()),
                "meds_on_admission": bool((narr.get("medications_on_admission") or "").strip()),
                "allergies": bool((narr.get("allergies") or "").strip()),
                "physical_exam": bool((narr.get("physical_exam") or "").strip()),
                "lab>0": len(labs) > 0,
                "micro>0": len(micros) > 0,
                "radiology>0": len(rads) > 0,
                "prescriptions>0": len(tr.get("medications", [])) > 0,
                "pharmacy>0": len(tr.get("pharmacy_orders", [])) > 0,
                "emar>0": len(tr.get("medication_administrations", [])) > 0,
                "procedures>0": len(tr.get("procedures", [])) > 0,
                "discharge_record": bool((disp.get("discharge_record") or "").strip()),
                "brief_hospital_course": bool((disp.get("brief_hospital_course") or "").strip()),
                "home_meds>0": len(hm) > 0,
                "DRG": bool(disp.get("drg")),
                "ICU_stays": len(icu) > 0,
            }
            for ck, cv in checks.items():
                if cv:
                    fill_track[ck] += 1
    logger.info("Streaming complete: %d records", n)
    return {
        "n": n,
        "ages": np.array(ages),
        "sexes": sexes,
        "admission_types": admission_types,
        "vital_arrays": {k: np.array(v) for k, v in vital_arrays.items()},
        "has_any_vital": has_any_vital,
        "rhythm_counter": rhythm_counter,
        "text_len_arrays": {k: np.array(v) for k, v in text_len_arrays.items()},
        "icd_versions": icd_versions,
        "other_dx_counts": np.array(other_dx_counts),
        "primary_dx_names": primary_dx_names,
        "lab_item_counts": np.array(lab_item_counts),
        "lab_result_counts": np.array(lab_result_counts),
        "lab_labels": lab_labels,
        "micro_counts": np.array(micro_counts),
        "spec_types": spec_types,
        "org_names": org_names,
        "rad_counts": np.array(rad_counts),
        "exam_types": exam_types,
        "rx_counts": np.array(rx_counts),
        "pharm_counts": np.array(pharm_counts),
        "emar_counts": np.array(emar_counts),
        "proc_counts": np.array(proc_counts),
        "hcpcs_counts": np.array(hcpcs_counts),
        "drug_names": drug_names,
        "disc_locations": disc_locations,
        "adm_locations": adm_locations,
        "primary_services": primary_services,
        "has_drg": has_drg,
        "has_icu": has_icu,
        "transfer_steps": np.array(transfer_steps),
        "home_med_counts": np.array(home_med_counts),
        "fill_track": fill_track,
    }
def _save(fig, name):
    path = OUTPUT_DIR / name
    fig.savefig(path)
    plt.close(fig)
    logger.info("Saved %s", path)
def _top_bar(ax, counter, top_n=15, color=C_PRIMARY, title="", xlabel=""):
    items = counter.most_common(top_n)
    labels = [k[:40] for k, _ in items]
    values = [v for _, v in items]
    bars = ax.barh(range(len(labels)), values, color=color, edgecolor="white", linewidth=0.5)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val:,}", va="center", fontsize=6)
def plot_demographics(d):
    n = d["n"]
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"人口学特征 (N={n:,})", fontsize=14, fontweight="bold", y=0.98)
    ax = axes[0, 0]
    ages = d["ages"]
    ax.hist(ages, bins=range(15, 100, 5), color=C_PRIMARY, edgecolor="white", linewidth=0.5)
    ax.axvline(np.median(ages), color=C_WARN, linestyle="--", linewidth=1.5, label=f"中位数 {np.median(ages):.0f}")
    ax.axvline(np.mean(ages), color=C_ACCENT, linestyle=":", linewidth=1.5, label=f"均值 {np.mean(ages):.1f}")
    ax.set_xlabel("年龄", fontsize=9)
    ax.set_ylabel("人数", fontsize=9)
    ax.set_title("年龄分布", fontsize=11, fontweight="bold")
    ax.legend(fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax = axes[0, 1]
    sex_data = d["sexes"]
    labels = list(sex_data.keys())
    sizes = list(sex_data.values())
    colors_s = [C_PRIMARY, C_SECONDARY, C_NEUTRAL][:len(labels)]
    wedges, texts, autotexts = ax.pie(sizes, labels=labels, autopct="%1.1f%%", colors=colors_s, startangle=90)
    for t in autotexts:
        t.set_fontsize(9)
    ax.set_title("性别分布", fontsize=11, fontweight="bold")
    ax = axes[1, 0]
    _top_bar(ax, d["admission_types"], top_n=10, color=C_SECONDARY, title="入院类型 Top 10", xlabel="人数")
    ax = axes[1, 1]
    brackets = ["18-29", "30-44", "45-59", "60-74", "75+"]
    bracket_vals = [
        np.sum((ages >= 18) & (ages < 30)),
        np.sum((ages >= 30) & (ages < 45)),
        np.sum((ages >= 45) & (ages < 60)),
        np.sum((ages >= 60) & (ages < 75)),
        np.sum(ages >= 75),
    ]
    bars = ax.bar(brackets, bracket_vals, color=PALETTE[:5], edgecolor="white")
    for bar, val in zip(bars, bracket_vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + n * 0.005,
                f"{val/n*100:.1f}%", ha="center", fontsize=8)
    ax.set_xlabel("年龄段", fontsize=9)
    ax.set_ylabel("人数", fontsize=9)
    ax.set_title("年龄段分布", fontsize=11, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    _save(fig, "01_demographics.png")
def plot_vitals(d):
    vital_meta = {
        "temperature": ("体温 (°F)", (90, 108)),
        "heartrate": ("心率 (bpm)", (20, 200)),
        "resprate": ("呼吸频率", (5, 50)),
        "o2sat": ("血氧饱和度 (%)", (80, 100)),
        "sbp": ("收缩压 (mmHg)", (50, 250)),
        "dbp": ("舒张压 (mmHg)", (20, 150)),
        "acuity": ("ESI 分级", (1, 5)),
    }
    n = d["n"]
    has_vital = d["has_any_vital"]
    fig, axes = plt.subplots(3, 3, figsize=(15, 13))
    fig.suptitle(f"生命体征分布 (有 triage 数据: {has_vital:,}/{n:,} = {has_vital/n*100:.1f}%)",
                 fontsize=13, fontweight="bold", y=0.99)
    for i, (vk, (label, (vmin, vmax))) in enumerate(vital_meta.items()):
        row, col = divmod(i, 3)
        ax = axes[row][col]
        arr = d["vital_arrays"][vk]
        arr_clean = arr[(arr >= vmin) & (arr <= vmax)]
        if vk == "acuity":
            acuity_counts = Counter(arr.astype(int))
            x_vals = sorted(acuity_counts.keys())
            y_vals = [acuity_counts[x] for x in x_vals]
            bars = ax.bar(x_vals, y_vals, color=PALETTE[:len(x_vals)], edgecolor="white", width=0.6)
            for bar, val in zip(bars, y_vals):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(y_vals) * 0.01,
                        f"{val:,}", ha="center", fontsize=7)
            ax.set_xticks(x_vals)
        else:
            n_bins = min(50, max(20, int(np.sqrt(len(arr_clean)))))
            ax.hist(arr_clean, bins=n_bins, color=C_PRIMARY, edgecolor="white", linewidth=0.3)
            if len(arr_clean) > 0:
                ax.axvline(np.median(arr_clean), color=C_WARN, linestyle="--", linewidth=1.2)
        fill_pct = len(arr) / n * 100
        ax.set_title(f"{label}\n(n={len(arr):,}, 填充率 {fill_pct:.1f}%)", fontsize=9, fontweight="bold")
        ax.set_xlabel(label, fontsize=8)
        ax.set_ylabel("人数", fontsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    ax = axes[2][1]
    rc = d["rhythm_counter"]
    if rc:
        _top_bar(ax, rc, top_n=8, color=C_ACCENT, title="心律 Top 8", xlabel="人数")
    else:
        ax.text(0.5, 0.5, "无数据", ha="center", va="center", fontsize=12, transform=ax.transAxes)
        ax.set_title("心律", fontsize=9)
    for r, c in [(2, 2)]:
        axes[r][c].axis("off")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    _save(fig, "02_vitals.png")
def plot_narrative(d):
    text_fields = [
        ("chief_complaint", "主诉"),
        ("history_of_present_illness", "现病史 (HPI)"),
        ("past_medical_history", "既往史 (PMH)"),
        ("medications_on_admission", "入院用药"),
        ("allergies", "过敏史"),
        ("physical_exam", "体格检查"),
        ("discharge_note_full", "出院小结全文"),
        ("brief_hospital_course", "住院经过"),
        ("discharge_record", "出院指导"),
    ]
    n = d["n"]
    fig, axes = plt.subplots(3, 3, figsize=(16, 14))
    fig.suptitle("叙事文本长度分布 (字符数)", fontsize=14, fontweight="bold", y=0.99)
    for i, (key, label) in enumerate(text_fields):
        row, col = divmod(i, 3)
        ax = axes[row][col]
        arr = d["text_len_arrays"][key]
        nonzero = arr[arr > 0]
        if len(nonzero) > 0:
            max_val = np.percentile(nonzero, 99)
            ax.hist(nonzero, bins=50, range=(0, max_val), color=C_SECONDARY, edgecolor="white", linewidth=0.3)
            ax.axvline(np.median(nonzero), color=C_WARN, linestyle="--", linewidth=1.2)
        fill = len(nonzero)
        fill_pct = fill / n * 100
        ax.set_title(f"{label}\n(填充 {fill:,}/{n:,} = {fill_pct:.1f}%)", fontsize=9, fontweight="bold")
        ax.set_xlabel("字符数", fontsize=8)
        ax.set_ylabel("visit 数", fontsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    _save(fig, "03_narrative.png")
def plot_diagnoses(d):
    n = d["n"]
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(f"诊断分析 (N={n:,})", fontsize=14, fontweight="bold", y=0.99)
    ax = axes[0, 0]
    iv = d["icd_versions"]
    labels = list(iv.keys())
    sizes = list(iv.values())
    ax.pie(sizes, labels=labels, autopct="%1.1f%%", colors=[C_PRIMARY, C_SECONDARY, C_NEUTRAL][:len(labels)], startangle=90)
    ax.set_title("ICD 版本分布", fontsize=11, fontweight="bold")
    ax = axes[0, 1]
    odc = d["other_dx_counts"]
    ax.hist(odc, bins=range(0, min(50, int(np.max(odc)) + 1)), color=C_ACCENT, edgecolor="white", linewidth=0.3)
    ax.axvline(np.median(odc), color=C_WARN, linestyle="--", linewidth=1.5, label=f"中位数 {np.median(odc):.0f}")
    ax.set_xlabel("其他诊断数", fontsize=9)
    ax.set_ylabel("人数", fontsize=9)
    ax.set_title("合并症数量分布", fontsize=11, fontweight="bold")
    ax.legend(fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax = axes[1, 0]
    _top_bar(ax, d["primary_dx_names"], top_n=20, color=C_PRIMARY, title="主诊断 Top 20", xlabel="人数")
    ax = axes[1, 1]
    top20 = d["primary_dx_names"].most_common(20)
    labels20 = [k[:30] for k, _ in top20]
    values20 = [v / n * 100 for _, v in top20]
    ax.barh(range(len(labels20)), values20, color=C_SECONDARY, edgecolor="white", linewidth=0.5)
    ax.set_yticks(range(len(labels20)))
    ax.set_yticklabels(labels20, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel("占比 (%)", fontsize=9)
    ax.set_title("主诊断 Top 20 (占比)", fontsize=11, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    _save(fig, "04_diagnoses.png")
def plot_investigations(d):
    n = d["n"]
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(f"检查检验分析 (N={n:,})", fontsize=14, fontweight="bold", y=0.99)
    ax = axes[0, 0]
    lic = d["lab_item_counts"]
    ax.hist(lic, bins=50, color=C_PRIMARY, edgecolor="white", linewidth=0.3)
    ax.axvline(np.median(lic), color=C_WARN, linestyle="--", label=f"中位数 {np.median(lic):.0f}")
    ax.set_xlabel("检验项目数/visit", fontsize=9)
    ax.set_ylabel("人数", fontsize=9)
    ax.set_title("实验室检验项目数分布", fontsize=11, fontweight="bold")
    ax.legend(fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax = axes[0, 1]
    _top_bar(ax, d["lab_labels"], top_n=20, color=C_PRIMARY, title="最常见检验项目 Top 20", xlabel="出现次数")
    ax = axes[1, 0]
    mc = d["micro_counts"]
    mc_nz = mc[mc > 0]
    ax.hist(mc_nz, bins=50, range=(0, min(80, np.percentile(mc_nz, 99) if len(mc_nz) > 0 else 80)), color=C_ACCENT, edgecolor="white", linewidth=0.3)
    has_micro = len(mc_nz)
    ax.set_title(f"微生物检验数/visit (有记录: {has_micro:,}/{n:,} = {has_micro/n*100:.1f}%)", fontsize=10, fontweight="bold")
    ax.set_xlabel("微生物检验数", fontsize=9)
    ax.set_ylabel("人数", fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax = axes[1, 1]
    rc = d["rad_counts"]
    rc_nz = rc[rc > 0]
    ax.hist(rc_nz, bins=range(0, min(30, int(np.max(rc_nz)) + 1)), color=C_SECONDARY, edgecolor="white", linewidth=0.3)
    has_rad = len(rc_nz)
    ax.set_title(f"影像报告数/visit (有记录: {has_rad:,}/{n:,} = {has_rad/n*100:.1f}%)", fontsize=10, fontweight="bold")
    ax.set_xlabel("影像报告数", fontsize=9)
    ax.set_ylabel("人数", fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    _save(fig, "05_investigations.png")
def plot_micro_rad(d):
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("微生物与影像分析", fontsize=14, fontweight="bold", y=0.99)
    ax = axes[0, 0]
    _top_bar(ax, d["spec_types"], top_n=15, color=C_ACCENT, title="微生物标本类型 Top 15", xlabel="出现次数")
    ax = axes[0, 1]
    _top_bar(ax, d["org_names"], top_n=15, color=C_WARN, title="检出病原体 Top 15", xlabel="出现次数")
    ax = axes[1, 0]
    _top_bar(ax, d["exam_types"], top_n=15, color=C_SECONDARY, title="影像检查类型 Top 15", xlabel="出现次数")
    axes[1][1].axis("off")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    _save(fig, "06_microbiology_radiology.png")
def plot_treatments(d):
    n = d["n"]
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle(f"治疗处置分析 (N={n:,})", fontsize=14, fontweight="bold", y=0.99)
    panels = [
        ("rx_counts", "处方记录数/visit", C_PRIMARY),
        ("pharm_counts", "药房医嘱数/visit", C_SECONDARY),
        ("emar_counts", "给药记录数/visit", C_ACCENT),
        ("proc_counts", "操作记录数/visit", C_WARN),
        ("hcpcs_counts", "HCPCS 记录数/visit", C_NEUTRAL),
    ]
    for i, (key, label, color) in enumerate(panels):
        row, col = divmod(i, 3)
        ax = axes[row][col]
        arr = d[key]
        nz = arr[arr > 0]
        p99 = np.percentile(nz, 99) if len(nz) > 0 else 1
        ax.hist(nz, bins=50, range=(0, p99), color=color, edgecolor="white", linewidth=0.3)
        nonzero = np.sum(arr > 0)
        ax.set_title(f"{label}\n(有记录: {nonzero:,} = {nonzero/n*100:.1f}%)", fontsize=9, fontweight="bold")
        ax.set_xlabel("记录数", fontsize=8)
        ax.set_ylabel("人数", fontsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    ax = axes[1][2]
    _top_bar(ax, d["drug_names"], top_n=20, color=C_PRIMARY, title="最常处方药物 Top 20", xlabel="处方次数")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    _save(fig, "07_treatments.png")
def plot_disposition(d):
    n = d["n"]
    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.suptitle(f"去向与转科分析 (N={n:,})", fontsize=14, fontweight="bold", y=0.99)
    ax = axes[0, 0]
    _top_bar(ax, d["disc_locations"], top_n=10, color=C_PRIMARY, title="出院去向 Top 10", xlabel="人数")
    ax = axes[0, 1]
    _top_bar(ax, d["adm_locations"], top_n=10, color=C_SECONDARY, title="入院来源 Top 10", xlabel="人数")
    ax = axes[0, 2]
    _top_bar(ax, d["primary_services"], top_n=12, color=C_ACCENT, title="主要负责科室 Top 12", xlabel="人数")
    ax = axes[1, 0]
    drg_labels = ["有 DRG", "无 DRG"]
    drg_vals = [d["has_drg"], n - d["has_drg"]]
    ax.pie(drg_vals, labels=drg_labels, autopct="%1.1f%%", colors=[C_PRIMARY, C_NEUTRAL], startangle=90)
    ax.set_title("DRG 编码覆盖", fontsize=11, fontweight="bold")
    ax = axes[1, 1]
    icu_labels = ["有 ICU", "无 ICU"]
    icu_vals = [d["has_icu"], n - d["has_icu"]]
    ax.pie(icu_vals, labels=icu_labels, autopct="%1.1f%%", colors=[C_WARN, C_NEUTRAL], startangle=90)
    ax.set_title("ICU 入住情况", fontsize=11, fontweight="bold")
    ax = axes[1, 2]
    ts = d["transfer_steps"]
    ax.hist(ts, bins=range(0, min(20, int(np.max(ts)) + 1)), color=C_SECONDARY, edgecolor="white", linewidth=0.3)
    ax.axvline(np.median(ts), color=C_WARN, linestyle="--", label=f"中位数 {np.median(ts):.0f}")
    ax.set_xlabel("转科次数", fontsize=9)
    ax.set_ylabel("人数", fontsize=9)
    ax.set_title("转科路径长度", fontsize=11, fontweight="bold")
    ax.legend(fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    _save(fig, "08_disposition.png")
def plot_completeness(d):
    n = d["n"]
    ft = d["fill_track"]
    fields = sorted(ft.keys(), key=lambda k: ft[k] / n, reverse=True)
    rates = [ft[f] / n * 100 for f in fields]
    fig, ax = plt.subplots(figsize=(12, 8))
    colors_list = [C_ACCENT if r >= 90 else (C_PRIMARY if r >= 50 else C_WARN) for r in rates]
    bars = ax.barh(range(len(fields)), rates, color=colors_list, edgecolor="white", linewidth=0.5)
    ax.set_yticks(range(len(fields)))
    ax.set_yticklabels(fields, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("填充率 (%)", fontsize=10)
    ax.set_title(f"数据完整性矩阵 (N={n:,})", fontsize=13, fontweight="bold")
    ax.axvline(90, color=C_ACCENT, linestyle=":", alpha=0.5, linewidth=1)
    ax.axvline(50, color=C_WARN, linestyle=":", alpha=0.5, linewidth=1)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for bar, val in zip(bars, rates):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2, f"{val:.1f}%", va="center", fontsize=7)
    ax.set_xlim(0, 110)
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=C_ACCENT, label=">=90%"),
        Patch(facecolor=C_PRIMARY, label="50-89%"),
        Patch(facecolor=C_WARN, label="<50%"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=8)
    fig.tight_layout()
    _save(fig, "09_completeness.png")
def plot_correlation(d):
    n = d["n"]
    cols = {
        "age": d["ages"].astype(float),
        "other_dx": d["other_dx_counts"].astype(float),
        "lab_items": d["lab_item_counts"].astype(float),
        "micro": d["micro_counts"].astype(float),
        "radiology": d["rad_counts"].astype(float),
        "rx": d["rx_counts"].astype(float),
        "pharmacy": d["pharm_counts"].astype(float),
        "emar": d["emar_counts"].astype(float),
        "procedures": d["proc_counts"].astype(float),
        "transfers": d["transfer_steps"].astype(float),
        "home_meds": d["home_med_counts"].astype(float),
        "DS_text_len": d["text_len_arrays"]["discharge_note_full"].astype(float),
    }
    labels = list(cols.keys())
    mat = np.column_stack([cols[l] for l in labels])
    corr = np.corrcoef(mat.T)
    fig, ax = plt.subplots(figsize=(12, 10))
    im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=9, rotation=45, ha="right")
    ax.set_yticklabels(labels, fontsize=9)
    for i in range(len(labels)):
        for j in range(len(labels)):
            val = corr[i, j]
            color = "white" if abs(val) > 0.6 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=7, color=color)
    fig.colorbar(im, ax=ax, shrink=0.8, label="Pearson r")
    ax.set_title("Visit-level Metric Correlation Matrix", fontsize=13, fontweight="bold")
    fig.tight_layout()
    _save(fig, "10_correlation.png")
def plot_data_density(d):
    n = d["n"]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    total_events = (d["lab_result_counts"] + d["rx_counts"] + d["emar_counts"] + d["micro_counts"] + d["rad_counts"])
    ax = axes[0]
    p99 = np.percentile(total_events, 99)
    ax.hist(total_events, bins=80, range=(0, p99), color=C_PRIMARY, edgecolor="white", linewidth=0.3)
    ax.axvline(np.median(total_events), color=C_WARN, linestyle="--", label=f"median {np.median(total_events):.0f}")
    ax.set_xlabel("Total events/visit", fontsize=9)
    ax.set_ylabel("Count", fontsize=9)
    ax.set_title("Data Density per Visit", fontsize=11, fontweight="bold")
    ax.legend(fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax = axes[1]
    sample_idx = np.random.choice(n, min(10000, n), replace=False)
    ax.scatter(d["ages"][sample_idx], d["other_dx_counts"][sample_idx], alpha=0.1, s=3, color=C_SECONDARY)
    z = np.polyfit(d["ages"], d["other_dx_counts"], 1)
    x_fit = np.linspace(18, 95, 100)
    ax.plot(x_fit, np.polyval(z, x_fit), color=C_WARN, linewidth=2, label=f"trend: y={z[0]:.2f}x+{z[1]:.1f}")
    ax.set_xlabel("Age", fontsize=9)
    ax.set_ylabel("Other diagnoses count", fontsize=9)
    ax.set_title("Age vs Comorbidity (10K sample)", fontsize=11, fontweight="bold")
    ax.legend(fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.suptitle(f"Data Density & Age Trends (N={n:,})", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    _save(fig, "11_data_density.png")
def main():
    d = stream_aggregate()
    n = d["n"]
    logger.info("Aggregation complete. Starting plot generation...")
    plot_demographics(d)
    plot_vitals(d)
    plot_narrative(d)
    plot_diagnoses(d)
    plot_investigations(d)
    plot_micro_rad(d)
    plot_treatments(d)
    plot_disposition(d)
    plot_completeness(d)
    plot_correlation(d)
    plot_data_density(d)
    logger.info("All plots generated in %s", OUTPUT_DIR)
    print(f"\n{'='*60}")
    print(f"EDA SUMMARY: {n:,} visits")
    print(f"{'='*60}")
    print(f"  Age: mean={np.mean(d['ages']):.1f}, median={np.median(d['ages']):.0f}")
    print(f"  Sex: {dict(d['sexes'])}")
    print(f"  Vitals coverage: {d['has_any_vital']:,}/{n:,} ({d['has_any_vital']/n*100:.1f}%)")
    print(f"  Lab items/visit: mean={np.mean(d['lab_item_counts']):.1f}")
    print(f"  ICU stays: {d['has_icu']:,}/{n:,} ({d['has_icu']/n*100:.1f}%)")
    print(f"  Plots saved to: {OUTPUT_DIR}")
if __name__ == "__main__":
    main()
