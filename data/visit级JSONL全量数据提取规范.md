# visit 级 JSONL 全量数据提取规范

> **生成日期**: 2026-08-07
> **数据版本**: MIMIC-IV v3.1 (hosp/icu) + MIMIC-IV-ED v2.2 (ed) + MIMIC-IV-Note v2.2 (note)
> **定位**: 单患者单次住院（visit）全量临床资料提取规范。在 37 字段基础上纳入全部非 ICU 连续监测源表。
> **排除**: ICU 连续监测 6 表（chartevents / inputevents / outputevents / datetimeevents / ingredientevents / procedureevents）
> **icustays 保留**: 作为元数据（ICU 时长、科室），不排除。

---

## 一、与 G 盘 episodes 对比

G 盘路径: G:/Projects/医疗数据集评测-MIMIC/outputs/episodes

| 文件 | 行数 | 大小 |
|---|---|---|
| episode_index | 767,971 | 24MB |
| care_contacts | 3,069,421 | 71MB |
| timeline_events | 238,203,827 | 13.9GB |
| event_items | 892,073,791 | 28.5GB |
| evidence_links | 900,934,117 | 7.8GB |
| documents | 2,652,892 | 1.8GB |
| episode_coverage | 767,971 | 17MB |
| patient_history_refs | 767,971 | 9.6MB |
| unresolved_events | 13,067,505 | 368MB |
| **合计** | **~2.07B** | **~58GB** |

### 架构差异

| 维度 | G 盘 episodes | 本规范 JSONL |
|---|---|---|
| 数据模型 | Event-sourced 星型架构（规范化关系表） | Document-oriented（反规范化，每行一个 visit） |
| 粒度 | episode（含 ED-only，无 hadm_id） | visit（hadm_id 级，有纳入过滤） |
| 过滤 | 不过滤（全部 767,971 episode） | 过滤（age>=18 + 有效主诊断 + 有效 DS） |
| ICU 数据 | 全部纳入（chartevents 4.33 亿行） | **排除**连续监测 6 表，仅保留 icustays 元数据 |
| 源表覆盖 | 全部 41 张 | 35 张 |
| 总大小 | ~58GB | ~26GB 原始 / ~5-7GB gzip |
| 查询方式 | SQL (DuckDB/Spark) | Python json 逐行 / jq |
| 适用场景 | 全量关系查询、复杂时序分析 | 文本训练输入、出题引擎读取 |

### 信息等价性

排除 ICU 连续监测后，两端在**非 ICU 数据**上信息等价。本规范独有：纳入过滤、DS 章节解析、investigation 合并、结构化分组。G 盘独有：ED-only episode、全局时序轴 timeline_events、evidence_links、patient_history_refs。

---

## 二、源表清单

### 使用表（35 张）

hosp 模块（22 张）: admissions, patients, diagnoses_icd, d_icd_diagnoses, procedures_icd, d_icd_procedures, poe, poe_detail, labevents, d_labitems, microbiologyevents, prescriptions, pharmacy, emar, emar_detail, services, transfers, hcpcsevents, d_hcpcs, drgcodes, omr, icustays

ed 模块（5 张）: edstays, triage, vitalsign, diagnosis, medrecon

note 模块（4 张）: discharge, radiology, radiology_detail, discharge_detail

字典（3 张）: d_items, provider, caregiver

### 排除表（6 张 ICU 连续监测）

| 表 | 行数 | 排除原因 |
|---|---|---|
| chartevents | 432,997,491 | ICU 连续监测（生命体征/GCS/呼吸机参数） |
| inputevents | 10,953,713 | ICU 静脉输液/药物泵注 |
| outputevents | 5,359,395 | ICU 出量（尿量/引流液） |
| datetimeevents | 9,979,761 | ICU 时间型事件 |
| ingredientevents | 14,253,480 | ICU 药物成分明细 |
| procedureevents | 808,706 | ICU 操作记录（插管/拔管/CRRT） |

排除依据：ICU 连续监测仅覆盖 15.6% 住院，但 chartevents 单表 4.33 亿行占 G 盘 event_items 的 48.5%。icustays 元数据（94,458 行）保留。

---

## 三、JSONL 文档结构

每行是一个完整 JSON 对象，8 个顶层分组（NEW 标注新增子字段）：

```json
{
  "identifiers": {"subject_id": "...", "hadm_id": "..."},
  "demographics": {
    "age_at_encounter": 65, "sex": "M", "admission_type": "EW EMER.",
    "baseline": {"blood_pressure": [...], "weight_lbs": [...], "bmi": [...], "height_inches": [...], "egfr": [...]},
    "home_medications": [{"name": "Metoprolol", "gsn": "...", "ndc": "...", "etcdescription": "..."}]
  },
  "vitals": {"source": "triage", "temperature": 98.6, "heartrate": 88, "resprate": 18, "o2sat": 97, "sbp": 130, "dbp": 80, "acuity": 3, "rhythm": "Sinus Rhythm"},
  "narrative": {"chief_complaint": "...", "history_of_present_illness": "...", "past_medical_history": "...", "social_history": "...", "medications_on_admission": "...", "allergies": "...", "physical_exam": "...", "discharge_note_full": "..."},
  "investigations": {
    "laboratory": [{"itemid": 50912, "label": "Creatinine", "fluid": "Blood", "category": "Chemistry", "results": [...]}],
    "microbiology": [{"spec_type_desc": "BLOOD CULTURE", "test_name": "...", "charttime": "...", "org_name": "STAPH AUREUS", "isolate_num": 1, "antibiotics": [{"ab_name": "Vancomycin", "interpretation": "S", "dilution_value": 1.0}]}],
    "radiology": [{"exam_name": "CT HEAD W/O CONTRAST", "charttime": "...", "text": "...", "details": [...]}],
    "cardiology": [{"order_subtype": "ECG", "ordertime": "...", "poe_detail": [...]}],
    "respiratory": [{"order_subtype": "ABG", "ordertime": "...", "poe_detail": [...]}]
  },
  "diagnoses": {
    "primary": {"icd_code": "...", "diagnosis_name": "...", "icd_version": "..."},
    "other": ["...", "..."],
    "ed_diagnoses": [{"seq_num": 1, "icd_code": "...", "icd_version": 10, "icd_title": "..."}]
  },
  "treatments": {
    "medications": [{"drug": "Vancomycin", "dose_val_rx": "1000", "dose_unit_rx": "mg", "route": "IV", "starttime": "..."}],
    "pharmacy_orders": [{"medication": "Vancomycin", "starttime": "...", "stoptime": "...", "route": "IV", "frequency": "q12h", "status": "Active"}],
    "medication_administrations": [{"medication": "Vancomycin", "charttime": "...", "event_txt": "Administered", "detail": {"dose_given": "1000", "dose_given_unit": "mg", "route": "IV"}}],
    "procedures": [{"procedure_name": "...", "icd_code": "...", "icd_version": 9}],
    "hcpcs": [{"hcpcs_cd": "...", "short_description": "...", "chartdate": "..."}]
  },
  "disposition": {
    "primary_service": "MED", "admission_location": "...", "discharge_location": "...", "ed_disposition": "...",
    "brief_hospital_course": "...", "discharge_medications": "...", "discharge_condition": "...", "discharge_record": "...",
    "transfer_path": [{"eventtype": "ED", "careunit": "...", "intime": "...", "outtime": "..."}],
    "icu_stays": [{"first_careunit": "MICU", "last_careunit": "MICU", "intime": "...", "outtime": "...", "los": 3.2}],
    "drg": {"drg_type": "APR", "drg_code": "...", "description": "...", "drg_severity": 3, "drg_mortality": 2}
  }
}
```

---

## 四、新增字段定义（10 个）

原有 37 字段定义不变（见 出题数据抽取字段规范.md），此处仅定义新增部分。

### 38. demographics.baseline（omr）

- 来源: omr.csv 按 subject_id 关联（门诊记录，非 hadm_id 级）
- 语义: 患者基线生理指标（日常血压、体重、BMI、身高、eGFR）
- 提取: 按 result_name 分组，每组保留最近 3 次（chartdate 降序）
- 格式: ```{"blood_pressure": [{"chartdate":"...", "value":"130/80"}], "weight_lbs": [...], ...}```

### 39. demographics.home_medications（ed/medrecon）

- 来源: ed/medrecon.csv 经 edstays.hadm_id -> stay_id -> medrecon.stay_id
- 语义: 急诊入院前用药核对，比 DS Medications on Admission 更结构化
- 覆盖率: 46.8%（仅 ED 就诊有）

### 40. investigations.microbiology（microbiologyevents）

- 来源: microbiologyevents.csv 按 hadm_id 关联
- 语义: 培养结果 + 药敏试验。与 labevents 不同：labevents 是定量值，microbiology 是"什么标本长出了什么菌、对什么药敏感"
- 聚合: 按 micro_specimen_id + org_name 分组，抗生素结果归入 antibiotics 数组
- 覆盖率: ~37%

### 41. diagnoses.ed_diagnoses（ed/diagnosis）

- 来源: ed/diagnosis.csv 经 edstays 关联
- 语义: 急诊工作诊断，区别于住院最终诊断
- 覆盖率: 46.8%

### 42. treatments.pharmacy_orders（pharmacy）

- 来源: pharmacy.csv 按 hadm_id 关联
- 语义: 药房层级的处方管理（频率、输注速率、验证状态、停药时间）

### 43. treatments.medication_administrations（emar + emar_detail）

- 来源: emar.csv + emar_detail.csv 按 hadm_id 关联
- 语义: 药物实际执行记录（护士实际给药时间、剂量、途径）
- 关联: emar_id + emar_seq -> emar_detail.emar_id + emar_seq
- 覆盖率: ~49%

### 44. treatments.hcpcs（hcpcsevents + d_hcpcs）

- 来源: hcpcsevents.csv + d_hcpcs.csv 按 hadm_id 关联
- 语义: HCPCS 计费操作记录，补充 procedures_icd
- 覆盖率: 低（全库 186K 行）

### 45. disposition.transfer_path（transfers）

- 来源: transfers.csv 按 hadm_id 关联
- 语义: 科室间转运全路径（急诊 -> 病房 -> ICU -> 出院）

### 46. disposition.icu_stays（icustays 元数据）

- 来源: icustays.csv 按 hadm_id 关联
- 语义: ICU 时长和科室，不含连续监测数据
- 覆盖率: 15.6%

### 47. disposition.drg（drgcodes）

- 来源: drgcodes.csv 按 hadm_id 关联
- 语义: DRG 分组 + 严重度/死亡率分级
- 选择: drg_type 优先级 APR > HCFA > ALL，取第一条

---

## 五、完整字段总表

原有 37 字段全部保留。新增 10 字段：

| # | JSON 路径 | 类型 | 来源 | 缺失表示 |
|--:|---|---|---|---|
| 38 | demographics.baseline | JSON 对象 | omr | {} |
| 39 | demographics.home_medications | JSON 数组 | ed/medrecon | [] |
| 40 | investigations.microbiology | JSON 数组 | microbiologyevents | [] |
| 41 | diagnoses.ed_diagnoses | JSON 数组 | ed/diagnosis | [] |
| 42 | treatments.pharmacy_orders | JSON 数组 | pharmacy | [] |
| 43 | treatments.medication_administrations | JSON 数组 | emar + emar_detail | [] |
| 44 | treatments.hcpcs | JSON 数组 | hcpcsevents + d_hcpcs | [] |
| 45 | disposition.transfer_path | JSON 数组 | transfers | [] |
| 46 | disposition.icu_stays | JSON 数组 | icustays | [] |
| 47 | disposition.drg | JSON 对象 | drgcodes | null |

**总字段数: 47**（37 原有 + 10 新增）

---

## 六、文件大小预估

### 单 visit 大小分解（基于 G 盘源表行数 + ~300K eligible visit 估算）

| 字段组 | 行/visit | KB/visit | 占比 |
|---|---|---|---|
| investigations.laboratory | ~190 | 28.5 | 32% |
| treatments.medication_administrations | ~130 | 12.7 | 14% |
| narrative.discharge_note_full | 1 | 12.0 | 14% |
| treatments.pharmacy_orders | ~34 | 10.2 | 12% |
| treatments.medications (prescriptions) | ~39 | 7.8 | 9% |
| narrative (7 DS 章节) | 1 | 5.0 | 6% |
| investigations.radiology | ~2 | 3.0 | 3% |
| diagnoses (primary + other + ed) | ~15 | 2.25 | 3% |
| demographics.baseline (omr) | ~21 | 2.0 | 2% |
| disposition (核心 + transfer + icu + drg) | ~6 | 2.1 | 2% |
| 其余（vitals, medrecon, cardiology, hcpcs） | | 1.2 | 1% |
| **合计** | | **~88** | 100% |

### 总文件大小

| 指标 | 值 |
|---|---|
| 平均 visit 大小 | ~88 KB |
| 中位数 visit 大小 | ~45 KB |
| p90 visit 大小 | ~200 KB |
| eligible visit 数 | ~300K |
| **JSONL 原始** | **~26 GB** |
| **gzip 压缩后** | **~5-7 GB** |

体积前 5 项占 82%。如需缩减，pharmacy_orders（与 prescriptions 重叠）是最可考虑的取舍点。

---

## 七、提取管线

```text
Stage 0  admissions + patients + icustays + services + transfers + drgcodes + omr
         -> 候选 Visit + 人口统计筛选
Stage 1  diagnoses_icd + d_icd_diagnoses + ed/diagnosis -> 诊断筛选
Stage 2  discharge(DS) -> 出院小结筛选
         ---- 纳入漏斗结束 ----
Stage 3  DS 章节字段（8 narrative + 4 disposition + 全文）
Stage 4  investigations（laboratory + microbiology + radiology + cardiology + respiratory）
Stage 5  treatments（medications + pharmacy + emar + procedures + hcpcs）
Stage 6  disposition（transfer_path + icu_stays + drg + services + ED）
Stage 7  demographics（baseline omr + home_medications medrecon）
Stage 8  组装 + 验证 + 写入 JSONL
```

纳入条件（不变）：age>=18 + 有效主诊断 + 有效 DS + 非空 Chief Complaint

输出：rwd_benchmark_visits.jsonl（UTF-8），每行一个 visit 完整 JSON 对象，47 字段。

---

## 八、禁止操作

（继承 出题数据抽取规范.md 全部禁止操作，另增）：

- 不从 chartevents/inputevents/outputevents/datetimeevents/ingredientevents/procedureevents 提取数据
- icustays 仅取元数据（careunit, los），不关联 ICU 事件表
- 不从 ICU 连续监测表推断生命体征或治疗措施
