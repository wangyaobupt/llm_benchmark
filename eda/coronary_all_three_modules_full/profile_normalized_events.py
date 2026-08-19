# -*- coding: utf-8 -*-
"""Profile normalized_events.parquet (coronary_all_three_modules_full, 27.3M events).

单次批量遍历，产出 EDA 指标 JSON，供 build_normalized_events_eda_html.py 渲染。
聚焦五个领域：检查 / 诊断 / 治疗 T1-T3 / 转诊，外加时间·质量·术语标准化横切面。
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
NORM_MANIFEST = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalization_manifest.json")
WF_MANIFEST = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\workflow_manifest.json")
OUT_DIR = Path(r"D:\Projects\llm_benchmark\eda\coronary_all_three_modules_full")
OUT_JSON = OUT_DIR / "normalized_events_eda_metrics.json"

SEP = "\x1f"

# 事件类型 -> 领域分组（与 tasks/{investigation_selection,clinical_diagnosis,treatment,referral} 的口径一致）
DOMAIN_MAP = {
    # 检查
    "laboratory_resulted": "检查·检验结果",
    "laboratory_ordered": "检查·检验医嘱",
    "imaging_ordered": "检查·影像医嘱",
    "imaging_reported": "检查·影像报告",
    "microbiology_resulted": "检查·微生物",
    # 诊断
    "condition_recorded_post_hoc": "诊断·编码诊断",
    "symptom_reported": "诊断·主诉症状",
    "administrative_group_recorded": "诊断·DRG分组",
    # 治疗 T1（开立医嘱）
    "medication_ordered": "治疗T1·用药医嘱",
    "clinical_ordered": "治疗T1·通用医嘱",
    # 治疗 T2（执行情况）
    "medication_administered": "治疗T2·给药执行",
    "medication_not_administered": "治疗T2·未给药",
    "medication_administration_documented": "治疗T2·给药记录",
    "medication_ingredient_administered": "治疗T2·成分给药",
    "medication_dispensed": "治疗T2·ED发药",
    "medication_reconciled": "治疗T2·ED用药核对",
    "input_administered": "治疗T2·ICU输注",
    "medication_order_status_recorded": "治疗·药房状态跟踪",
    # 治疗 T3（手术/操作）
    "procedure_performed": "治疗T3·ICU床旁操作",
    "procedure_recorded_post_hoc": "治疗T3·编码操作",
    # 转诊/流转
    "service_changed": "转诊·服务团队变更",
    "patient_transferred": "转诊·床位转移",
    # 其他/背景
    "vital_measured": "背景·生命体征",
    "output_measured": "背景·ICU出入量",
    "clinical_datetime_recorded": "背景·ICU时间项",
    "triage_acuity_recorded": "背景·分诊分级",
    "document_recorded": "背景·临床文书",
}

# 需要 Top-N 标签表的事件类型
LABEL_KINDS = {
    "laboratory_resulted", "laboratory_ordered", "imaging_ordered", "imaging_reported",
    "microbiology_resulted", "condition_recorded_post_hoc", "symptom_reported",
    "administrative_group_recorded", "clinical_ordered",
    "medication_ordered", "medication_administered", "medication_not_administered",
    "medication_administration_documented", "input_administered",
    "procedure_performed", "procedure_recorded_post_hoc",
    "service_changed", "patient_transferred",
}
# 需要 json.loads(value_structured_json) 的事件类型
ORDER_KINDS = {"clinical_ordered", "laboratory_ordered", "imaging_ordered", "medication_ordered"}
RESOLUTION_KINDS = {"medication_administered", "medication_not_administered", "medication_administration_documented"}
PARSE_KINDS = ORDER_KINDS | RESOLUTION_KINDS | {"service_changed"}
# 需要单位分布的事件类型
UNIT_KINDS = {"laboratory_resulted", "vital_measured", "input_administered", "output_measured", "medication_ingredient_administered"}
# 需要 source_concept_id 编码系统前缀的事件类型
CODING_KINDS = {"condition_recorded_post_hoc", "procedure_recorded_post_hoc", "administrative_group_recorded"}

COLUMNS = [
    "cleaning_status", "subject_id", "hadm_id", "encounter_id", "event_kind",
    "lifecycle_action", "status", "assertion", "evidence_phase", "entity_type",
    "normalization_status", "unit_normalization_status", "content_specificity",
    "source_concept_id", "concept_id", "preferred_name", "source_label",
    "value_numeric", "value_text", "value_structured_json", "unit", "abnormal_flag",
    "event_time", "source_available_time", "available_time", "recorded_time",
    "time_resolution_status", "time_precision", "time_policy_id",
    "quality_flags", "source_module", "source_table",
]


def pctiles(values: list[float] | np.ndarray) -> dict:
    if len(values) == 0:
        return {"n": 0}
    a = np.asarray(values, dtype=float)
    return {
        "n": int(a.size),
        "mean": float(a.mean()),
        "p50": float(np.percentile(a, 50)),
        "p90": float(np.percentile(a, 90)),
        "p95": float(np.percentile(a, 95)),
        "p99": float(np.percentile(a, 99)),
        "max": float(a.max()),
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # ---- 计数器与累加器 -------------------------------------------------
    n_rows = 0
    subjects: set[str] = set()
    hadms: set[str] = set()
    hadm_subj: dict[str, str] = {}
    hadm_modules: dict[str, set[str]] = defaultdict(set)
    encounter_prefix = Counter()
    c_cleaning = Counter()
    c_module = Counter()
    c_table = Counter()          # module|table
    c_kind = Counter()
    c_kind_module = Counter()    # kind|module
    c_kind_table = Counter()     # kind|table
    c_kind_lifecycle = Counter() # kind|lifecycle
    c_kind_status = Counter()    # kind|status
    c_assertion = Counter()
    c_evidence = Counter()
    c_entity = Counter()
    c_specificity = Counter()
    c_norm = Counter()
    c_kind_norm = Counter()      # kind|status
    c_unitnorm = Counter()
    c_kind_unitnorm = Counter()
    c_trs = Counter()            # time_resolution_status
    c_kind_trs = Counter()
    c_precision = Counter()
    c_policy = Counter()
    c_year = Counter()
    c_qflag = Counter()
    c_kind_qflag = Counter()
    c_kind_abnormal = Counter()
    c_kind_unit = Counter()
    c_kind_coding = Counter()    # kind|code_system_prefix

    kind_hadms: dict[str, set[str]] = defaultdict(set)
    hadm_n: Counter = Counter()
    domain_hadm_n: dict[str, Counter] = defaultdict(Counter)

    kind_label: dict[str, Counter] = defaultdict(Counter)
    kind_label_unres: dict[str, Counter] = defaultdict(Counter)

    # kind -> [n, event_time, source_available, available, recorded]
    kind_time: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0])
    # kind -> presence counts
    kind_value: dict[str, Counter] = defaultdict(Counter)

    json_keys = Counter()
    c_order_type = Counter()     # kind|order_type
    c_order_subtype = Counter()  # kind|subtype
    med_link = Counter()         # medication_ordered 链接状态
    c_resolution = Counter()     # kind|field|value
    service_pairs = Counter()    # prev->curr
    json_errors = 0

    # T1/T2 链接（label 与 concept 两级）
    t1_labels: dict[str, set[str]] = defaultdict(set)
    t2_labels: dict[str, set[str]] = defaultdict(set)
    t1_concepts: dict[str, set[str]] = defaultdict(set)
    t2_concepts: dict[str, set[str]] = defaultdict(set)

    pf = pq.ParquetFile(EVENTS)
    total = pf.metadata.num_rows
    print(f"source: {EVENTS}")
    print(f"rows={total:,} row_groups={pf.metadata.num_row_groups} bytes={EVENTS.stat().st_size:,}")

    batches = pf.iter_batches(batch_size=200_000, columns=COLUMNS)
    n_batch = 0
    for batch in batches:
        d = batch.to_pydict()
        n_batch += 1
        kinds = d["event_kind"]
        modules = d["source_module"]
        tables = d["source_table"]
        hadm_col = d["hadm_id"]
        subj_col = d["subject_id"]
        enc_col = d["encounter_id"]
        life_col = d["lifecycle_action"]
        status_col = d["status"]
        assert_col = d["assertion"]
        evid_col = d["evidence_phase"]
        entity_col = d["entity_type"]
        spec_col = d["content_specificity"]
        norm_col = d["normalization_status"]
        unitnorm_col = d["unit_normalization_status"]
        srccid_col = d["source_concept_id"]
        cid_col = d["concept_id"]
        pref_col = d["preferred_name"]
        label_col = d["source_label"]
        vnum_col = d["value_numeric"]
        vtext_col = d["value_text"]
        vjson_col = d["value_structured_json"]
        unit_col = d["unit"]
        abn_col = d["abnormal_flag"]
        et_col = d["event_time"]
        sat_col = d["source_available_time"]
        at_col = d["available_time"]
        rt_col = d["recorded_time"]
        trs_col = d["time_resolution_status"]
        prec_col = d["time_precision"]
        pol_col = d["time_policy_id"]
        qf_col = d["quality_flags"]
        clean_col = d["cleaning_status"]

        for i in range(len(kinds)):
            kind = kinds[i]
            n_rows += 1
            hadm = hadm_col[i]
            subj = subj_col[i]
            hadms.add(hadm)
            subjects.add(subj)
            if hadm not in hadm_subj:
                hadm_subj[hadm] = subj
            module = modules[i]
            hadm_n[hadm] += 1
            hadm_modules[hadm].add(module)
            kind_hadms[kind].add(hadm)
            enc = enc_col[i]
            if enc:
                encounter_prefix[enc.split(":", 1)[0]] += 1
            c_cleaning[clean_col[i]] += 1
            c_module[module] += 1
            c_table[SEP.join((module, tables[i]))] += 1
            c_kind[kind] += 1
            c_kind_module[SEP.join((kind, module))] += 1
            c_kind_table[SEP.join((kind, tables[i]))] += 1
            domain = DOMAIN_MAP.get(kind)
            if domain is None:
                domain = "未分组"
            domain_hadm_n[domain][hadm] += 1

            la = life_col[i]
            if la:
                c_kind_lifecycle[SEP.join((kind, la))] += 1
            st = status_col[i]
            if st:
                c_kind_status[SEP.join((kind, st))] += 1
            a = assert_col[i]
            if a:
                c_assertion[SEP.join((kind, a))] += 1
            ev = evid_col[i]
            if ev:
                c_evidence[SEP.join((kind, ev))] += 1
            en = entity_col[i]
            if en:
                c_entity[en] += 1
            sp = spec_col[i]
            if sp:
                c_specificity[SEP.join((kind, sp))] += 1

            nst = norm_col[i]
            c_norm[nst] += 1
            c_kind_norm[SEP.join((kind, nst))] += 1
            ust = unitnorm_col[i]
            c_unitnorm[ust] += 1
            c_kind_unitnorm[SEP.join((kind, ust))] += 1

            # 时间
            kt = kind_time[kind]
            kt[0] += 1
            if et_col[i]:
                kt[1] += 1
                s = et_col[i]
                if len(s) >= 4 and s[0] in "12" and s[:4].isdigit():
                    c_year[s[:4]] += 1
            if sat_col[i]:
                kt[2] += 1
            if at_col[i]:
                kt[3] += 1
            if rt_col[i]:
                kt[4] += 1
            trs = trs_col[i]
            c_trs[trs] += 1
            c_kind_trs[SEP.join((kind, trs))] += 1
            pr = prec_col[i]
            if pr:
                c_precision[pr] += 1
            po = pol_col[i]
            if po:
                c_policy[po] += 1

            for f in qf_col[i]:
                c_qflag[f] += 1
                c_kind_qflag[SEP.join((kind, f))] += 1

            # 值存在性
            kv = kind_value[kind]
            kv["n"] += 1
            if vnum_col[i] is not None:
                kv["value_numeric"] += 1
            if vtext_col[i]:
                kv["value_text"] += 1
            if vjson_col[i]:
                kv["value_structured"] += 1
            if unit_col[i]:
                kv["unit"] += 1
                if kind in UNIT_KINDS:
                    c_kind_unit[SEP.join((kind, unit_col[i]))] += 1
            ab = abn_col[i]
            if ab:
                kv["abnormal"] += 1
                c_kind_abnormal[SEP.join((kind, ab))] += 1
            if cid_col[i]:
                kv["concept_id"] += 1
            if pref_col[i]:
                kv["preferred_name"] += 1

            # 编码系统前缀
            if kind in CODING_KINDS:
                scid = srccid_col[i]
                if scid:
                    c_kind_coding[SEP.join((kind, scid.split(":", 1)[0]))] += 1

            # 标签计数（preferred_name 优先）
            if kind in LABEL_KINDS:
                lbl = pref_col[i] or label_col[i] or "(空)"
                kind_label[kind][lbl] += 1
                if nst == "unresolved":
                    kind_label_unres[kind][lbl] += 1

            # 结构化 JSON 解析
            if kind in PARSE_KINDS and vjson_col[i]:
                try:
                    obj = json.loads(vjson_col[i])
                    if isinstance(obj, dict):
                        for k in obj:
                            json_keys[SEP.join((kind, k))] += 1
                        if kind in ORDER_KINDS:
                            ot = obj.get("order_type")
                            if ot:
                                c_order_type[SEP.join((kind, str(ot)))] += 1
                            osu = obj.get("order_subtype")
                            if osu:
                                c_order_subtype[SEP.join((kind, str(osu)))] += 1
                        if kind == "medication_ordered":
                            med_link["n"] += 1
                            if obj.get("poe_id"):
                                med_link["has_poe_id"] += 1
                            if obj.get("pharmacy_id"):
                                med_link["has_pharmacy_id"] += 1
                            pps = obj.get("poe_pair_status")
                            if pps:
                                med_link[SEP.join(("poe_pair_status", str(pps)))] += 1
                            phs = obj.get("pharmacy_id_status")
                            if phs:
                                med_link[SEP.join(("pharmacy_id_status", str(phs)))] += 1
                        if kind in RESOLUTION_KINDS:
                            for fld in ("medication_resolution", "poe_resolution"):
                                v = obj.get(fld)
                                if v:
                                    c_resolution[SEP.join((kind, fld, str(v)))] += 1
                        if kind == "service_changed":
                            prev = obj.get("previous_service") or "(入院首个团队)"
                            curr = label_col[i] or pref_col[i] or "?"
                            service_pairs[f"{prev} → {curr}"] += 1
                except (json.JSONDecodeError, TypeError):
                    json_errors += 1

            # T1/T2 链接集合
            if kind == "medication_ordered":
                key = (pref_col[i] or label_col[i] or "").strip().lower()
                if key:
                    t1_labels[hadm].add(key)
                if nst == "mapped" and cid_col[i]:
                    t1_concepts[hadm].add(cid_col[i])
            elif kind == "medication_administered":
                key = (pref_col[i] or label_col[i] or "").strip().lower()
                if key:
                    t2_labels[hadm].add(key)
                if nst == "mapped" and cid_col[i]:
                    t2_concepts[hadm].add(cid_col[i])

        if n_batch % 25 == 0:
            el = time.time() - t0
            done = n_batch * 200_000
            print(f"batch {n_batch}: {min(done, total):,}/{total:,} rows, {el:.0f}s", flush=True)

    print(f"scan done: {n_rows:,} rows in {time.time() - t0:.0f}s; json_errors={json_errors}")

    # ---- 派生指标 -------------------------------------------------------
    n_hadm_total = len(hadms)
    per_subj = Counter(hadm_subj.values())
    subj_hadm_counts = Counter(per_subj.values())

    epha_vals = list(hadm_n.values())
    hist_bins = [0, 10, 50, 100, 300, 600, 1000, 2000, 5000, 10**9]
    hist = Counter()
    for v in epha_vals:
        for lo, hi in zip(hist_bins[:-1], hist_bins[1:]):
            if lo <= v < hi:
                if hi >= 10**9:
                    hist[f"{lo}+"] += 1
                else:
                    hist[f"{lo}-{hi}"] += 1
                break

    module_order = {"mimic_iv_ed": 0, "mimic_iv_hosp": 1, "mimic_iv_icu": 2, "mimic_iv_note": 3}
    journey = Counter()
    for hadm, mods in hadm_modules.items():
        ordered = sorted(mods, key=lambda m: module_order.get(m, 9))
        journey[" → ".join(x.replace("mimic_iv_", "").upper() for x in ordered)] += 1

    domains_out = {}
    for dom, counter in domain_hadm_n.items():
        n = sum(counter.values())
        domains_out[dom] = {
            "n": n,
            "share": n / n_rows,
            "hadm_cov": len(counter),
            "hadm_cov_rate": len(counter) / n_hadm_total,
            "per_hadm": pctiles(list(counter.values())),
        }

    kinds_out = []
    for kind, n in c_kind.most_common():
        kt = kind_time[kind]
        kv = kind_value[kind]
        mapped = sum(v for k2, v in c_kind_norm.items() if k2.split(SEP)[0] == kind and k2.split(SEP)[1] == "mapped")
        kinds_out.append({
            "kind": kind,
            "domain": DOMAIN_MAP.get(kind, "未分组"),
            "n": n,
            "share": n / n_rows,
            "hadm_cov": len(kind_hadms[kind]),
            "hadm_cov_rate": len(kind_hadms[kind]) / n_hadm_total,
            "mapped_rate": mapped / n,
            "event_time_rate": kt[1] / kt[0] if kt[0] else 0.0,
            "value_numeric_rate": kv["value_numeric"] / n,
            "value_text_rate": kv["value_text"] / n,
            "value_structured_rate": kv["value_structured"] / n,
        })

    # T1/T2 链接统计
    t1_hadms = set(t1_labels) | set(t1_concepts)
    t2_hadms = set(t2_labels) | set(t2_concepts)
    both = t1_hadms & t2_hadms
    label_match_fracs = []
    concept_match_fracs = []
    hadm_t1_no_t2 = 0
    hadm_any_unmatched_t1 = 0
    unmatched_t1_labels = Counter()
    unmatched_t2_labels = Counter()
    unmatched_t1_concepts = Counter()
    n_t1_label_total = 0
    n_t1_label_matched = 0
    n_t1_c_total = 0
    n_t1_c_matched = 0
    for hadm in t1_hadms:
        s1, s2 = t1_labels.get(hadm, set()), t2_labels.get(hadm, set())
        c1, c2 = t1_concepts.get(hadm, set()), t2_concepts.get(hadm, set())
        if not s2 and not c2:
            hadm_t1_no_t2 += 1
        if s1 and s2:
            inter = s1 & s2
            n_t1_label_total += len(s1)
            n_t1_label_matched += len(inter)
            frac = len(inter) / len(s1) if s1 else 0.0
            label_match_fracs.append(frac)
            if len(inter) < len(s1):
                hadm_any_unmatched_t1 += 1
                for x in s1 - s2:
                    unmatched_t1_labels[x] += 1
            for x in s2 - s1:
                unmatched_t2_labels[x] += 1
        if c1 and c2:
            inter = c1 & c2
            n_t1_c_total += len(c1)
            n_t1_c_matched += len(inter)
            concept_match_fracs.append(len(inter) / len(c1))
            for x in c1 - c2:
                unmatched_t1_concepts[x] += 1

    linkage = {
        "hadm_with_t1": len(t1_hadms),
        "hadm_with_t2": len(t2_hadms),
        "hadm_both": len(both),
        "hadm_t1_no_any_t2": hadm_t1_no_t2,
        "label_level": {
            "t1_hadms_compared": len(label_match_fracs),
            "any_unmatched_t1_hadms": hadm_any_unmatched_t1,
            "t1_labels_total": n_t1_label_total,
            "t1_labels_matched": n_t1_label_matched,
            "match_rate_labels": n_t1_label_matched / n_t1_label_total if n_t1_label_total else 0.0,
            "per_hadm_match_frac": pctiles(label_match_fracs),
            "top_ordered_not_administered": unmatched_t1_labels.most_common(30),
            "top_administered_not_ordered": unmatched_t2_labels.most_common(30),
        },
        "concept_level": {
            "t1_hadms_compared": len(concept_match_fracs),
            "t1_concepts_total": n_t1_c_total,
            "t1_concepts_matched": n_t1_c_matched,
            "match_rate_concepts": n_t1_c_matched / n_t1_c_total if n_t1_c_total else 0.0,
            "per_hadm_match_frac": pctiles(concept_match_fracs),
            "top_unmatched_concepts": unmatched_t1_concepts.most_common(20),
        },
    }

    def dump_counter(c: Counter, top: int | None = None) -> dict:
        items = c.most_common(top)
        return {"|".join(str(x) for x in (k if isinstance(k, tuple) else (k,))): v for k, v in items}

    def split_counter(c: Counter, top: int | None = None) -> list[dict]:
        out = []
        for k, v in c.most_common(top):
            parts = k.split(SEP)
            row = {"v": v}
            for j, p in enumerate(parts):
                row[f"f{j}"] = p
            out.append(row)
        return out

    metrics = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "events_path": str(EVENTS),
            "file_bytes": EVENTS.stat().st_size,
            "rows_expected": total,
            "rows_scanned": n_rows,
            "scan_seconds": round(time.time() - t0, 1),
            "domain_map": DOMAIN_MAP,
            "json_parse_errors": json_errors,
        },
        "manifest": {
            "normalization": json.loads(NORM_MANIFEST.read_text(encoding="utf-8")),
            "workflow": json.loads(WF_MANIFEST.read_text(encoding="utf-8")),
        },
        "overview": {
            "rows": n_rows,
            "subjects": len(subjects),
            "hadms": n_hadm_total,
            "admissions_per_subject": pctiles([v for v in subj_hadm_counts.elements()]),
            "multi_admission_subjects": sum(v for k, v in subj_hadm_counts.items() if k > 1),
            "encounter_prefix": dump_counter(encounter_prefix),
            "cleaning_status": dump_counter(c_cleaning),
            "modules": dump_counter(c_module),
            "tables": split_counter(c_table, 80),
            "kind_module": split_counter(c_kind_module, 120),
            "kind_table": split_counter(c_kind_table, 150),
            "kinds": kinds_out,
            "kind_lifecycle": split_counter(c_kind_lifecycle, 80),
            "kind_status": split_counter(c_kind_status, 100),
            "kind_assertion": split_counter(c_assertion, 60),
            "kind_evidence_phase": split_counter(c_evidence, 60),
            "entity_type": dump_counter(c_entity, 40),
            "kind_content_specificity": split_counter(c_specificity, 80),
            "events_per_hadm": {**pctiles(epha_vals), "hist": dump_counter(hist)},
            "module_journey": dump_counter(journey),
        },
        "domains": domains_out,
        "labels": {
            kind: {
                "top": kind_label[kind].most_common(40),
                "top_unresolved": kind_label_unres[kind].most_common(25),
                "n_distinct": len(kind_label[kind]),
            }
            for kind in sorted(LABEL_KINDS & set(kind_label))
        },
        "treatment": {
            "med_order_link": {
                "n": med_link.get("n", 0),
                "has_poe_id": med_link.get("has_poe_id", 0),
                "has_pharmacy_id": med_link.get("has_pharmacy_id", 0),
                "poe_pair_status": {k: v for k, v in med_link.items() if SEP in str(k) and str(k).split(SEP)[0] == "poe_pair_status"},
                "pharmacy_id_status": {k: v for k, v in med_link.items() if SEP in str(k) and str(k).split(SEP)[0] == "pharmacy_id_status"},
            },
            "linkage_t1_t2": linkage,
            "resolution": split_counter(c_resolution, 60),
            "order_type": split_counter(c_order_type, 60),
            "order_subtype": split_counter(c_order_subtype, 60),
            "json_keys": split_counter(json_keys, 80),
        },
        "referral": {
            "service_pairs": service_pairs.most_common(40),
        },
        "coding_systems": split_counter(c_kind_coding, 40),
        "time": {
            "resolution_status": dump_counter(c_trs),
            "kind_resolution": split_counter(c_kind_trs, 120),
            "precision": dump_counter(c_precision),
            "policy": dump_counter(c_policy, 25),
            "year": dump_counter(c_year),
            "kind_time_fields": {
                k: {"n": v[0], "event_time": v[1], "source_available": v[2], "available": v[3], "recorded": v[4]}
                for k, v in kind_time.items()
            },
        },
        "quality": {
            "flags": dump_counter(c_qflag, 30),
            "kind_flags": split_counter(c_kind_qflag, 100),
            "kind_abnormal": split_counter(c_kind_abnormal, 40),
            "kind_unit": split_counter(c_kind_unit, 60),
        },
        "normalization": {
            "status": dump_counter(c_norm),
            "kind_status": split_counter(c_kind_norm, 120),
            "unit_status": dump_counter(c_unitnorm),
            "kind_unit_status": split_counter(c_kind_unitnorm, 120),
        },
    }

    # med_link 过滤后的键已是纯文本
    ml = metrics["treatment"]["med_order_link"]
    ml["poe_pair_status"] = {str(k).split(SEP)[1]: v for k, v in med_link.items() if SEP in str(k) and str(k).split(SEP)[0] == "poe_pair_status"}
    ml["pharmacy_id_status"] = {str(k).split(SEP)[1]: v for k, v in med_link.items() if SEP in str(k) and str(k).split(SEP)[0] == "pharmacy_id_status"}

    OUT_JSON.write_text(json.dumps(metrics, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"metrics written: {OUT_JSON} ({OUT_JSON.stat().st_size:,} bytes)")
    print(f"cross-check -> manifest events: {metrics['manifest']['normalization']['counts']['events']:,} vs scanned {n_rows:,}")
    print(f"cross-check -> mapped/unresolved: {dict(metrics['normalization']['status'])}")


if __name__ == "__main__":
    main()
