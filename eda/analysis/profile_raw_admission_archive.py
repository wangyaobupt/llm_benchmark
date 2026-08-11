"""Stream a raw admission JSONL and write reproducible EDA metrics and Markdown."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from data_pipeline.mimic_raw_archive.catalog import ARCHIVE_SOURCES, MODULE_TABLES
from data_pipeline.mimic_raw_archive.cohort import CAD_CRITERIA, is_cad_code
from data_pipeline.mimic_raw_archive.schema import (
    TOP_LEVEL_FIELDS,
    RawArchiveValidationError,
    validate_record,
)


def percentile(values: list[int], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def histogram_percentile(histogram: Counter[int], probability: float) -> float:
    total = sum(histogram.values())
    if not total:
        return 0.0
    target = (total - 1) * probability
    cumulative = 0
    for value in sorted(histogram):
        cumulative += histogram[value]
        if cumulative > target:
            return float(value)
    return float(max(histogram))


def cad_group(code: object, version: object) -> str | None:
    value = str(code or "").upper().replace(".", "")
    version_value = str(version or "")
    prefix = value[:3]
    if (version_value == "9" and prefix == "410") or (
        version_value == "10" and prefix in {"I21", "I22"}
    ):
        return "acute_myocardial_infarction"
    if (version_value == "9" and prefix == "411") or (
        version_value == "10" and prefix == "I24"
    ):
        return "other_acute_ischemia"
    if (version_value == "9" and prefix == "413") or (
        version_value == "10" and prefix == "I20"
    ):
        return "angina"
    if (version_value == "9" and prefix == "412") or (
        version_value == "10" and value.startswith("I252")
    ):
        return "old_myocardial_infarction"
    if (version_value == "9" and prefix == "414") or (
        version_value == "10" and prefix == "I25"
    ):
        return "chronic_ischemic_or_coronary_atherosclerosis"
    return None


def _time_fields() -> dict[str, tuple[str, ...]]:
    result = {}
    for source in ARCHIVE_SOURCES:
        result[source.key] = tuple(
            field for field in source.source.header
            if "time" in field or field.endswith("date") or field == "dod"
        )
    return result


def profile(
    input_path: Path,
    manifest_path: Path,
    selection_path: Path | None = None,
) -> dict[str, Any]:
    table_rows: Counter[str] = Counter()
    table_coverage: Counter[str] = Counter()
    table_histograms: dict[str, Counter[int]] = defaultdict(Counter)
    module_coverage: Counter[str] = Counter()
    time_present: Counter[str] = Counter()
    time_missing: Counter[str] = Counter()
    line_sizes: list[int] = []
    cad_line_sizes: list[int] = []
    subjects: set[str] = set()
    cad_subjects: set[str] = set()
    admissions_per_subject: Counter[str] = Counter()
    patient_demographics: dict[str, tuple[str | None, int | None]] = {}
    demographic_conflicts = 0
    admission_types: Counter[str] = Counter()
    discharge_locations: Counter[str] = Counter()
    hospital_expire: Counter[str] = Counter()
    length_of_stay_days: list[float] = []
    cad_code_rows: Counter[str] = Counter()
    cad_code_admissions: dict[str, set[str]] = defaultdict(set)
    cad_group_rows: Counter[str] = Counter()
    cad_group_admissions: dict[str, set[str]] = defaultdict(set)
    primary_cad_admissions: set[str] = set()
    secondary_cad_admissions: set[str] = set()
    relevant_codes_per_admission: Counter[int] = Counter()
    readiness: Counter[str] = Counter()
    record_partitions: Counter[str] = Counter()
    invalid_records = 0
    forbidden_chartevents = 0
    unexpected_top_fields: Counter[str] = Counter()
    orphan_counts: Counter[str] = Counter()
    largest: list[tuple[int, str, str]] = []
    time_fields = _time_fields()
    selection_by_hadm: dict[str, str] = {}
    subject_partitions: dict[str, str] = {}
    partition_conflicts = 0
    if selection_path is not None:
        with selection_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                selected = json.loads(line)
                hadm = str(selected["hadm_id"])
                subject = str(selected["subject_id"])
                partition = str(selected.get("partition", "unassigned"))
                selection_by_hadm[hadm] = partition
                prior = subject_partitions.setdefault(subject, partition)
                if prior != partition:
                    partition_conflicts += 1

    with input_path.open("rb") as handle:
        for raw_line in handle:
            if not raw_line.strip():
                continue
            size = len(raw_line)
            record = json.loads(raw_line)
            line_sizes.append(size)
            subject_id = str(record.get("subject_id", ""))
            hadm_id = str(record.get("hadm_id", ""))
            subjects.add(subject_id)
            admissions_per_subject[subject_id] += 1
            if selection_path is not None:
                record_partitions[selection_by_hadm.get(hadm_id, "missing_from_selection")] += 1
            unexpected_top_fields.update(set(record) - set(TOP_LEVEL_FIELDS))
            if "chartevents" in record.get("mimic_iv_icu", {}):
                forbidden_chartevents += 1
            try:
                validate_record(record)
            except RawArchiveValidationError:
                invalid_records += 1

            hosp = record["mimic_iv_hosp"]
            patient_row = hosp["patients"][0] if hosp["patients"] else {}
            gender = patient_row.get("gender")
            try:
                anchor_age = int(patient_row["anchor_age"]) if patient_row.get("anchor_age") else None
            except ValueError:
                anchor_age = None
            demographic = (gender, anchor_age)
            prior_demographic = patient_demographics.setdefault(subject_id, demographic)
            if prior_demographic != demographic:
                demographic_conflicts += 1

            admission_row = hosp["admissions"][0] if hosp["admissions"] else {}
            admission_types[str(admission_row.get("admission_type") or "missing")] += 1
            discharge_locations[str(admission_row.get("discharge_location") or "missing")] += 1
            hospital_expire[str(admission_row.get("hospital_expire_flag") or "missing")] += 1
            try:
                admitted = datetime.fromisoformat(str(admission_row["admittime"]))
                discharged = datetime.fromisoformat(str(admission_row["dischtime"]))
                length_of_stay_days.append((discharged - admitted).total_seconds() / 86400)
            except (KeyError, TypeError, ValueError):
                pass

            cad_rows = [
                row for row in hosp["diagnoses_icd"]
                if is_cad_code(row.get("icd_code"), row.get("icd_version"))
            ]
            cad = bool(cad_rows)
            if cad:
                cad_line_sizes.append(size)
                cad_subjects.add(subject_id)
                relevant_codes_per_admission[len(cad_rows)] += 1
                for row in cad_rows:
                    code = str(row.get("icd_code") or "").upper().replace(".", "")
                    version = str(row.get("icd_version") or "")
                    code_key = f"ICD-{version}:{code[:3]}"
                    cad_code_rows[code_key] += 1
                    cad_code_admissions[code_key].add(hadm_id)
                    group = cad_group(code, version)
                    if group:
                        cad_group_rows[group] += 1
                        cad_group_admissions[group].add(hadm_id)
                    try:
                        primary = int(row.get("seq_num") or 0) == 1
                    except ValueError:
                        primary = False
                    (primary_cad_admissions if primary else secondary_cad_admissions).add(hadm_id)

            largest.append((size, subject_id, hadm_id))
            largest.sort(reverse=True)
            del largest[20:]

            for module, sources in MODULE_TABLES.items():
                module_has_rows = False
                for source in sources:
                    rows = record[module][source.output_key]
                    path = f"{module}.{source.output_key}"
                    table_rows[path] += len(rows)
                    table_histograms[path][len(rows)] += 1
                    if rows:
                        table_coverage[path] += 1
                        module_has_rows = True
                    for row in rows:
                        for field in time_fields[source.key]:
                            key = f"{path}.{field}"
                            if row.get(field) in (None, ""):
                                time_missing[key] += 1
                            else:
                                time_present[key] += 1
                if module_has_rows:
                    module_coverage[module] += 1

            ed = record["mimic_iv_ed"]
            note = record["mimic_iv_note"]
            if ed["triage"] and (hosp["labevents"] or hosp["poe"]):
                readiness["investigation_selection"] += 1
            if ed["triage"] and hosp["diagnoses_icd"]:
                readiness["clinical_diagnosis"] += 1
            if hosp["poe"] and (hosp["prescriptions"] or hosp["emar"]):
                readiness["treatment_disposition"] += 1
            if hosp["services"] or len(hosp["transfers"]) > 1:
                readiness["referral_service"] += 1
            if note["discharge"]:
                readiness["discharge_followup"] += 1

            poe_parents = {(r["subject_id"], r["poe_id"], r["poe_seq"]) for r in hosp["poe"]}
            orphan_counts["poe_detail"] += sum(
                (r["subject_id"], r["poe_id"], r["poe_seq"]) not in poe_parents
                for r in hosp["poe_detail"]
            )
            emar_parents = {(r["subject_id"], r["emar_id"], r["emar_seq"]) for r in hosp["emar"]}
            orphan_counts["emar_detail"] += sum(
                (r["subject_id"], r["emar_id"], r["emar_seq"]) not in emar_parents
                for r in hosp["emar_detail"]
            )
            ed_parents = {(r["subject_id"], r["stay_id"]) for r in ed["edstays"]}
            for child in ("triage", "vitalsign", "diagnosis", "medrecon", "pyxis"):
                orphan_counts[f"ed.{child}"] += sum(
                    (r["subject_id"], r["stay_id"]) not in ed_parents for r in ed[child]
                )
            for child, parent in (("discharge_detail", "discharge"), ("radiology_detail", "radiology")):
                parents = {(r["subject_id"], r["note_id"]) for r in note[parent]}
                orphan_counts[child] += sum(
                    (r["subject_id"], r["note_id"]) not in parents for r in note[child]
                )

    records = len(line_sizes)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shards = []
    for shard_id, state in sorted(manifest["shards"].items(), key=lambda item: int(item[0])):
        shards.append({
            "shard_id": int(shard_id), "records": int(state["records"]),
            "bytes": int(state["bytes"]), "sha256": state["sha256"],
        })
    time_quality = []
    for key in sorted(set(time_present) | set(time_missing)):
        present, missing = time_present[key], time_missing[key]
        total = present + missing
        time_quality.append({
            "field": key, "present": present, "missing": missing,
            "missing_rate": missing / total if total else 0.0,
        })
    table_metrics = []
    for module, sources in MODULE_TABLES.items():
        for source in sources:
            key = f"{module}.{source.output_key}"
            table_metrics.append({
                "table": key, "rows": table_rows[key],
                "nonempty_admissions": table_coverage[key],
                "coverage": table_coverage[key] / records if records else 0.0,
                "rows_per_admission": table_rows[key] / records if records else 0.0,
                "rows_p50": histogram_percentile(table_histograms[key], .50),
                "rows_p95": histogram_percentile(table_histograms[key], .95),
                "rows_p99": histogram_percentile(table_histograms[key], .99),
            })
    admission_counts = list(admissions_per_subject.values())
    genders = Counter(value[0] or "missing" for value in patient_demographics.values())
    ages = [value[1] for value in patient_demographics.values() if value[1] is not None]
    los_nonnegative = [value for value in length_of_stay_days if value >= 0]
    disease_codes = [
        {
            "code": key,
            "rows": count,
            "admissions": len(cad_code_admissions[key]),
        }
        for key, count in sorted(cad_code_rows.items())
    ]
    disease_groups = [
        {
            "group": key,
            "rows": count,
            "admissions": len(cad_group_admissions[key]),
        }
        for key, count in sorted(cad_group_rows.items())
    ]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input": str(input_path), "input_bytes": input_path.stat().st_size,
        "records": records, "subjects": len(subjects),
        "schema": {"invalid_records": invalid_records, "forbidden_chartevents": forbidden_chartevents,
                   "unexpected_top_fields": dict(unexpected_top_fields)},
        "line_bytes": {
            "mean": sum(line_sizes) / records if records else 0.0,
            "p50": percentile(line_sizes, .50), "p90": percentile(line_sizes, .90),
            "p95": percentile(line_sizes, .95), "p99": percentile(line_sizes, .99),
            "max": max(line_sizes, default=0),
        },
        "cad": {
            "criteria": CAD_CRITERIA, "admissions": len(cad_line_sizes), "subjects": len(cad_subjects),
            "mean_line_bytes": sum(cad_line_sizes) / len(cad_line_sizes) if cad_line_sizes else 0.0,
            "p50_line_bytes": percentile(cad_line_sizes, .50),
            "p95_line_bytes": percentile(cad_line_sizes, .95),
        },
        "patient_level": {
            "admissions_per_subject_mean": records / len(subjects) if subjects else 0.0,
            "admissions_per_subject_p50": percentile(admission_counts, .50),
            "admissions_per_subject_p95": percentile(admission_counts, .95),
            "admissions_per_subject_max": max(admission_counts, default=0),
            "subjects_with_multiple_admissions": sum(value > 1 for value in admission_counts),
            "gender": dict(genders),
            "anchor_age": {
                "nonmissing": len(ages),
                "mean": sum(ages) / len(ages) if ages else 0.0,
                "p50": percentile(ages, .50),
                "p95": percentile(ages, .95),
            },
            "demographic_conflicts": demographic_conflicts,
            "partitions": dict(record_partitions),
            "partition_subject_conflicts": partition_conflicts,
        },
        "admission_level": {
            "admission_type": dict(admission_types),
            "discharge_location": dict(discharge_locations),
            "hospital_expire_flag": dict(hospital_expire),
            "length_of_stay_days": {
                "nonmissing": len(los_nonnegative),
                "mean": sum(los_nonnegative) / len(los_nonnegative) if los_nonnegative else 0.0,
                "p50": percentile(los_nonnegative, .50),
                "p95": percentile(los_nonnegative, .95),
                "p99": percentile(los_nonnegative, .99),
            },
        },
        "disease_spectrum": {
            "code3": disease_codes,
            "clinical_groups": disease_groups,
            "primary_cad_admissions": len(primary_cad_admissions),
            "secondary_cad_admissions": len(secondary_cad_admissions),
            "relevant_codes_per_admission": {
                str(key): value for key, value in sorted(relevant_codes_per_admission.items())
            },
        },
        "benchmark_source_readiness": {
            key: {"admissions": readiness[key], "coverage": readiness[key] / records}
            for key in (
                "investigation_selection",
                "clinical_diagnosis",
                "treatment_disposition",
                "referral_service",
                "discharge_followup",
            )
        },
        "module_coverage": {key: value / records for key, value in module_coverage.items()},
        "tables": table_metrics, "time_quality": time_quality,
        "orphan_child_rows": dict(orphan_counts),
        "largest_admissions": [
            {"bytes": size, "subject_id": subject, "hadm_id": hadm}
            for size, subject, hadm in largest
        ],
        "shards": shards,
    }


def write_markdown(metrics: dict[str, Any], output_path: Path) -> None:
    b = metrics["line_bytes"]
    cad = metrics["cad"]
    patient = metrics["patient_level"]
    admission = metrics["admission_level"]
    lines = [
        f"# MIMIC 原始住院归档 {metrics['records']:,}例 EDA", "",
        f"> 生成时间：{metrics['generated_at']}", "",
        "## 核心规模", "",
        "| 指标 | 数值 |", "|---|---:|",
        f"| 住院记录 | {metrics['records']:,} |",
        f"| 唯一患者 | {metrics['subjects']:,} |",
        f"| JSONL体积 | {metrics['input_bytes'] / 1024**3:.3f} GiB |",
        f"| 平均每次住院 | {b['mean'] / 1024:.1f} KiB |",
        f"| P50 / P95 / P99 | {b['p50']/1024:.1f} / {b['p95']/1024:.1f} / {b['p99']/1024:.1f} KiB |",
        f"| 最大单次住院 | {b['max']/1024**2:.2f} MiB |", "",
        "## 冠状动脉疾病谱样本", "",
        f"筛选定义：{cad['criteria']}。编码仅用于离线队列识别。", "",
        "| 指标 | 数值 |", "|---|---:|",
        f"| 样本内相关住院 | {cad['admissions']:,} |",
        f"| 样本内相关患者 | {cad['subjects']:,} |",
        f"| 平均每次住院 | {cad['mean_line_bytes']/1024:.1f} KiB |",
        f"| P50 / P95 | {cad['p50_line_bytes']/1024:.1f} / {cad['p95_line_bytes']/1024:.1f} KiB |", "",
        "## 患者与住院", "",
        "| 指标 | 数值 |", "|---|---:|",
        f"| 平均相关住院/患者 | {patient['admissions_per_subject_mean']:.2f} |",
        f"| 住院次数P50 / P95 / 最大 | {patient['admissions_per_subject_p50']:.0f} / {patient['admissions_per_subject_p95']:.0f} / {patient['admissions_per_subject_max']} |",
        f"| 有多次相关住院的患者 | {patient['subjects_with_multiple_admissions']:,} |",
        f"| 锚定年龄均值 / P50 / P95 | {patient['anchor_age']['mean']:.1f} / {patient['anchor_age']['p50']:.0f} / {patient['anchor_age']['p95']:.0f} |",
        f"| 住院时长均值 / P50 / P95 | {admission['length_of_stay_days']['mean']:.2f} / {admission['length_of_stay_days']['p50']:.2f} / {admission['length_of_stay_days']['p95']:.2f} 天 |", "",
        "### 患者分区", "", "| 分区 | 住院数 |", "|---|---:|",
    ]
    lines.extend(f"| `{key}` | {value:,} |" for key, value in patient["partitions"].items())
    lines.extend(["", f"患者跨分区冲突：**{patient['partition_subject_conflicts']:,}**。", "",
        "### 性别", "", "| 原始值 | 患者数 |", "|---|---:|"])
    lines.extend(f"| `{key}` | {value:,} |" for key, value in patient["gender"].items())
    lines.extend(["", "### 入院类型", "", "| 原始值 | 住院数 |", "|---|---:|"])
    lines.extend(
        f"| `{key}` | {value:,} |"
        for key, value in sorted(admission["admission_type"].items(), key=lambda item: item[1], reverse=True)
    )
    lines.extend(["", "## 疾病谱编码", "",
                  "编码组可重叠；它们用于描述队列，不代表决策时点可见标签。", "",
                  "| ICD三位组 | 诊断行 | 住院数 |", "|---|---:|---:|"])
    for item in metrics["disease_spectrum"]["code3"]:
        lines.append(f"| `{item['code']}` | {item['rows']:,} | {item['admissions']:,} |")
    lines.extend(["", "### 临床编码组", "", "| 编码组 | 诊断行 | 住院数 |", "|---|---:|---:|"])
    for item in metrics["disease_spectrum"]["clinical_groups"]:
        lines.append(f"| `{item['group']}` | {item['rows']:,} | {item['admissions']:,} |")
    lines.extend(["", "## 五维度数据源可用性代理", "",
                  "以下只表示相关原始表同时存在，不等于题目候选数；正式候选仍须通过决策时点和未来信息泄漏测试。", "",
                  "| 维度 | 住院数 | 覆盖率 |", "|---|---:|---:|"])
    for key, item in metrics["benchmark_source_readiness"].items():
        lines.append(f"| `{key}` | {item['admissions']:,} | {item['coverage']:.2%} |")
    lines.extend(["",
        "## 模块覆盖", "", "| 模块 | 非空住院比例 |", "|---|---:|",
    ])
    lines.extend(f"| `{key}` | {value:.2%} |" for key, value in metrics["module_coverage"].items())
    lines.extend(["", "## 逐表统计", "", "| 表 | 总行数 | 非空住院 | 覆盖率 | 平均 | P50 | P95 |", "|---|---:|---:|---:|---:|---:|---:|"])
    for item in metrics["tables"]:
        lines.append(f"| `{item['table']}` | {item['rows']:,} | {item['nonempty_admissions']:,} | {item['coverage']:.2%} | {item['rows_per_admission']:.2f} | {item['rows_p50']:.0f} | {item['rows_p95']:.0f} |")
    lines.extend(["", "## 原始时间字段完整性", "", "| 字段 | 非空 | 空值 | 空值率 |", "|---|---:|---:|---:|"])
    for item in metrics["time_quality"]:
        lines.append(
            f"| `{item['field']}` | {item['present']:,} | {item['missing']:,} | {item['missing_rate']:.2%} |"
        )
    lines.extend(["", "## 最大单次住院记录", "", "| subject_id | hadm_id | 体积 MiB |", "|---|---|---:|"])
    for item in metrics["largest_admissions"]:
        lines.append(
            f"| `{item['subject_id']}` | `{item['hadm_id']}` | {item['bytes']/1024**2:.2f} |"
        )
    lines.extend(["", "## 完整性", "", f"- Schema失败记录：{metrics['schema']['invalid_records']:,}",
                  f"- 出现 `chartevents` 的记录：{metrics['schema']['forbidden_chartevents']:,}",
                  f"- 未知顶层字段：{json.dumps(metrics['schema']['unexpected_top_fields'], ensure_ascii=False)}",
                  f"- 父子孤立行：{json.dumps(metrics['orphan_child_rows'], ensure_ascii=False)}", "",
                  "## 分片", "", "| 分片 | 记录数 | 体积 GiB |", "|---:|---:|---:|"])
    for shard in metrics["shards"]:
        lines.append(f"| {shard['shard_id']} | {shard['records']:,} | {shard['bytes']/1024**3:.3f} |")
    comparison = metrics.get("comparison_to_reference")
    if comparison:
        lines.extend(["", "## 与10K随机开发样本比较", "",
                      "| 指标 | 当前队列 | 10K样本 | 比值/差值 |", "|---|---:|---:|---:|",
                      f"| 平均每次住院 KiB | {comparison['current_mean_kib']:.1f} | {comparison['reference_mean_kib']:.1f} | {comparison['mean_size_ratio']:.3f}× |"])
        for key, item in comparison["module_coverage"].items():
            lines.append(f"| `{key}`覆盖率 | {item['current']:.2%} | {item['reference']:.2%} | {item['delta']:+.2%} |")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def add_reference_comparison(
    metrics: dict[str, Any],
    reference: dict[str, Any],
) -> None:
    current_mean = float(metrics["line_bytes"]["mean"]) / 1024
    reference_mean = float(reference["line_bytes"]["mean"]) / 1024
    modules = {}
    for key, current in metrics["module_coverage"].items():
        reference_value = float(reference["module_coverage"].get(key, 0.0))
        modules[key] = {
            "current": current,
            "reference": reference_value,
            "delta": current - reference_value,
        }
    metrics["comparison_to_reference"] = {
        "reference_input": reference.get("input"),
        "reference_records": int(reference["records"]),
        "current_mean_kib": current_mean,
        "reference_mean_kib": reference_mean,
        "mean_size_ratio": current_mean / reference_mean if reference_mean else 0.0,
        "module_coverage": modules,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile a raw admission JSONL without loading it into memory")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--reference-metrics", type=Path)
    parser.add_argument("--metrics-output", type=Path, required=True)
    parser.add_argument("--metrics-copy", type=Path)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()
    metrics = profile(args.input, args.manifest, args.selection)
    if args.reference_metrics is not None:
        reference = json.loads(args.reference_metrics.read_text(encoding="utf-8"))
        add_reference_comparison(metrics, reference)
    args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
    metrics_json = json.dumps(metrics, ensure_ascii=False, indent=2)
    args.metrics_output.write_text(metrics_json, encoding="utf-8")
    if args.metrics_copy is not None:
        args.metrics_copy.parent.mkdir(parents=True, exist_ok=True)
        args.metrics_copy.write_text(metrics_json, encoding="utf-8")
    write_markdown(metrics, args.report_output)
    print(json.dumps({"records": metrics["records"], "cad": metrics["cad"], "input_bytes": metrics["input_bytes"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
