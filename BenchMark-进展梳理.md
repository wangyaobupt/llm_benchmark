# Benchmark 当前状态摘要

> 本文件只保留当前状态；检查/检验选择任务的执行合同、字段定义、时间语义、验收矩阵和 W0–W10 计划唯一维护在：[Benchmark-问题复核与实施计划](docs/Benchmark-问题复核与实施计划.md)。

## W0 失效结论

- 本轮只使用 MIMIC-IV，香港 RWD 不纳入；当前 `gold=0`。
- 旧 phenotype、8 类 phenotype 设计和旧 V2 规则/题目不作为新管线输入。
- 旧 V2 历史链路为：`1,584` 条 formal accepted 规则 → `738` 条去重规则 → `165` 条收敛规则 → `134` 道候选题 → `0` 道人工批准 gold；该链路整体因时间、split、分母和后验信息合同未冻结而失效。
- 旧 final-test 仅保留为 `engineering_audit_only` 历史审计材料，不能升级为新 formal final-test。
- 具体路径、hash、行数、旧 ID 和失效原因见 [`docs/legacy-invalidation-manifest.json`](docs/legacy-invalidation-manifest.json)。

W0 后，发布/人工审核入口拒绝旧 candidate/rule/question ID，split loader 拒绝旧 holdout，旧 phenotype formal 入口显式失败。后续 W1–W10 必须从新 `decision_document` 合同开始。

## 概览

面向患者单次就诊全流程的临床决策评测集（patient-journey benchmark），评估模型能否在不同临床决策节点，仅依据“当时已经发生且已经可用”的信息作出合理决策。

当前以 MIMIC-IV v3.1、MIMIC-IV-ED 2.2 和 MIMIC-IV-Note 2.2 开发、验证并冻结方法学；后续在香港真实世界资料上进行实践。

最终产物是五类英文 A–D 单选临床决策题，用于评估 LLM 在一次诊疗流程中的五项能力：

1. 检查检验选择；
2. 临床诊断；
3. 治疗与处置；
4. 转诊与科室选择；
5. 离院指导与随访。-->MIMIC没有这部分内容。

## 数据层

### 数据构成

- MIMIC-IV v3.1、MIMIC-IV-ED 2.2 和 MIMIC-IV-Note 2.2 
- 以 `{subject_id, hadm_id}` 构建
  - `subject_id` —— 患者 ID
  - `hadm_id` —— 住院 ID
  - 以一个 `hadm_id` 为一次住院信息，据此聚合单次住院期间的全部信息

### 数据清洗

```text
MIMIC-IV 原始 CSV.GZ（39 个锁定文件：HOSP 3.1 / ICU 3.1 / ED 2.2 / Note 2.2）四个模块
        │
        │ ① mimic_raw_archive      抽取 + 聚合（{subject_id, hadm_id} 连接、DuckDB 分片、断点续跑）
        ▼
admission 原始 JSONL                          schema: mimic_admission_raw/1.0.0
（一次住院一行；32 张表分模块内嵌、全字符串原值、无派生字段）--->分模块内嵌 可追溯，不直观
        │
        │ ② clean_clinical_archive 字典解码（具体检查、检验项目） + POE 时间线（便于冻结时间决策点）
        ▼
临床可读 JSONL                                schema: mimic_admission_clinical_readable/1.0.0
（源行追加 *_decoded 释义；新增派生表 hosp.poe_timeline；可逆性自检保证原始内容零改动）
        │
        │ ③ event_pipeline run     事件化 + 确定性归一化 + 双层独立审计 + 复跑门禁 + 原子发布
        ▼
event_pipeline_output/
  ├── cleaning/      cleaned_events.parquet（47 列事件表，一行一事件）
  ├── normalization/ normalized_events.parquet（8 个归一化字段，其余 39 列逐值不变）等 4 个产物
  ├── quality/       两级验收审计 + 复现报告
  └── workflow_manifest.json（仅全部门禁通过后存在）
        │
        │ ④ event_aggregation      无损聚合：把事件与临床可读/原始 JSONL 重连
        ▼
event_pipeline_output/aggregation/
  ├── processed_events.parquet     事件 + 五类逐字符 source_text（NER/检索分析层）
  ├── raw_source_records.parquet   每个源行恰好一行（source_record_id 存储层）
  └── traceable_events.parquet     事件内嵌完整源行（审计层）
        │
        │ ⑤ phenotype （DS）             visit 级类型化特征空间（P0 时间门禁 → P6 组装）
        ▼
visit_features_{role}.parquet（hadm_id × feature 长表，8 类特征）
visit_conditions_{role}.parquet（2-4 特征条件组合，Apriori L1 剪枝）
        │
        ▼ versions/v2-llm-stem/mcq/mining.py（多特征条件规则挖掘）→ conditional_rules → MCQ 题目生成

文本支路：text_ner / text_ner_v2 只读取 ④ 的 aggregation 产物
（raw_source_records 提供去重自由文本与血缘，processed_events 提供事件关联），不再回读源 JSONL。
```

#### mimic_raw_archive

- 将39个表中内容按照 `hadm_id` 提取

```json
{"schema":{"name":"mimic_admission_raw","version":"1.0.0"},
 "subject_id":"104","hadm_id":"1002",
 "mimic_iv_hosp":{
   "patients":[{"gender":"M","anchor_age":"62","anchor_year":"2175", ...}],
   "admissions":[{"admittime":"2181-05-21 02:00:00", ...}],
   "labevents":[{"labevent_id":"500001","itemid":"50801","charttime":"2181-05-21 04:00:00",
                 "storetime":"2181-05-21 06:30:00","valuenum":"300","valueuom":"mg/dl","flag":"abnormal", ...}],
   "poe":[{"poe_id":"104-5","poe_seq":"5","ordertime":"2181-05-21 05:00:00",
           "order_type":"Lab","order_subtype":"CBC","transaction_type":"New", ...}],
   "poe_detail":[], "prescriptions":[{"drug":"metoprolol","ndc":"00000000000", ...}],
   "pharmacy":[], "diagnoses_icd":[{"icd_code":"I25.10","icd_version":"10", ...}], ...},
 "mimic_iv_icu":{"icustays":[], ...},
 "mimic_iv_ed":{"edstays":[{"stay_id":"3000010", ...}],
   "triage":[{"chiefcomplaint":"chest pain","temperature":"98.6","acuity":"2", ...}],
   "medrecon":[{"drug":"metoprolol", ...}], "vitalsign":[...], "diagnosis":[], "pyxis":[]},
 "mimic_iv_note":{"discharge":[...], "radiology":[...], "discharge_detail":[], "radiology_detail":[]}}
```

#### clean_clinical_archive

- 1. Decode

```json
{ ..., "itemid":"50801",
  "itemid_decoded": {"source_dictionary":"d_labitems","itemid":"50801",
                     "label":"Glucose","fluid":"Blood","category":"Chemistry"} } # 原先的数据中只有id，没有具体检验项目
```

- 2. POE时间

```json
{"schema":{"name":"mimic-poe-timeline-event","version":"2.0.0"},
 "subject_id":"104","hadm_id":"1002","poe_id":"104-5","poe_seq":"5",
 "event_time":"2181-05-21 05:00:00",
 "action":"create","action_raw":"New","order_status_raw":"Active",
 "clinical_category":{"raw":"Lab","zh":"检验","subtype_raw":"CBC"},
 "content_specificity":"subtype_only",
 "incremental_information":{"comparison_basis":"new_order","added_facts":["order_type=Lab","order_subtype=CBC"], ...},
 "relations":{"chain_root_poe_id":"104-5","chain_position":0,"chain_complete":true},
 "quality_flags":[], "provenance":{"current":{"poe":[…该行…],"poe_detail":[],"prescriptions":[],"pharmacy":[]}}}
```

#### event_pipeline

event_cleaning-->构建事件表

event_normalization-->归一化

- Event化前

```JSON
{
  "schema": {"name": "mimic_admission_clinical_readable", "version": "1.0.0"},
  "subject_id": "104", "hadm_id": "1002",
  "mimic_iv_hosp": {
    "labevents": [
      { "labevent_id": "500001", "itemid": "50801",
        "itemid_decoded": {"source_dictionary": "d_labitems", "label": "Glucose", "fluid": "Blood"},
        "charttime": "2181-05-21 04:00:00", "storetime": "2181-05-21 06:30:00",
        "valuenum": "300", "value": "300", "valueuom": "mg/dl", "flag": "abnormal" }
    ],
    "prescriptions": [ { "drug": "metoprolol", "ndc": "00000000000", ... } ]
  },
  "mimic_iv_ed": {
    "triage": [ { "chiefcomplaint": "chest pain", "temperature": "98.6", "acuity": "2", ... } ]
  }
}
```

- Event化后

```JSON
// ① ED 主诉 → 归一化命中人工复核同义词
{
  "event_id": "evt:1a2b…", "source_row_id": "src:9f8e…",
  "subject_id": "104", "hadm_id": "1002", "encounter_id": "ed:3000010",
  "event_kind": "symptom_reported", "lifecycle_action": "report",
  "assertion": "present",                       // phenotype 据此取"在场症状"
  "entity_type": "symptom", "source_label": "chest pain",
  "concept_id": "symptom:chest_pain",            // ← 归一化写入
  "preferred_name": "Chest pain",
  "normalization_status": "mapped",
  "terminology_mapping_version": "event-terminology/1.1.0",
  "evidence_phase": "source_event",
  "source_table": "ed.triage", "source_array_index": 0, "jsonl_line_number": 38,
  "raw_row_ref": "xxx-clinical-readable.jsonl#L38/mimic_iv_ed.triage[0]",
  "quality_flags": ["TIME_UNAVAILABLE_IN_SOURCE"]   // 分诊行常无独立时间戳
}

// ② 血糖检验 → 时间戳 + 单位归一化
{
  "event_kind": "laboratory_resulted", "lifecycle_action": "result",
  "entity_type": "laboratory_test",
  "source_concept_id": "lab:50801", "source_label": "Glucose",
  "concept_id": "lab:50801", "normalization_status": "mapped",  // 源编码有效→直接映射
  "event_time": "2181-05-21 04:00:00",           // 抽血时刻（charttime）
  "source_available_time": "2181-05-21 06:30:00", // 结果入库（storetime）
  "available_time": "2181-05-21 06:30:00",        // = max(…) 防泄漏有效可见时间
  "value_numeric": 300.0, "unit": "mg/dl",
  "normalized_unit": "mg/dL", "unit_normalization_status": "mapped",
  "abnormal_flag": "abnormal",
  "raw_row_ref": "…#L38/mimic_iv_hosp.labevents[0]"
}

// ③ 药物医嘱 → 全 0 NDC 解析不了 → 显式 unresolved
{
  "event_kind": "medication_ordered",
  "source_concept_id": "ndc:00000000000", "source_label": "metoprolol",
  "concept_id": null, "normalization_status": "unresolved",  // 不猜，进 review queue
  "supporting_raw_row_refs": ["…#L38/mimic_iv_hosp.poe_timeline[12]"],  // 订单时间必须由时间线支撑
  "quality_flags": []
}
```



```text
event_id:              evt:3f2a...          ← 这条事件是谁（sha256 截断）
entity_id:             ent:9c1e...          ← 事件的主语实体
source_row_id:         src:8d44...          ← 来自哪行源数据
subject_id:            10001234             ← 哪个患者
hadm_id:               23456789             ← 哪次住院
encounter_id:          hadm:23456789        ← 哪个 encounter

event_kind:            laboratory_resulted  ← 什么类型的事实
lifecycle_action:      null
status:                null
assertion:             present              ← 事实断言：发生了(present)/没发生(absent)

event_time:            "2024-01-01T10:00:00"   ← 事件发生时间
source_available_time: "2024-01-01T10:15:00"   ← 源声明的时间(storetime)
available_time:        "2024-01-01T10:15:00"   ← 有效可用时间(泄漏安全)
recorded_time:         "2024-01-01T10:15:00"   ← 系统记录时间
time_resolution_status: resolved
time_precision:        second
time_policy_id:        chart_store_v2
time_resolution_reasons: []

evidence_phase:        source_event
source_concept_id:     lab:50971              ← 源概念(只标注)
concept_id:            null                   ← 归一化后概念(cleaning 阶段空着)
preferred_name:        null
source_label:          "Potassium"
entity_type:           laboratory_test
normalization_status:  null
terminology_mapping_version: null
content_specificity:   entity_specific

value_numeric:         4.2                    ← 数值通道
value_text:            "4.2"                  ← 文本通道
value_structured_json: null                   ← 结构化通道(血压/处方详情放这)
unit:                  mEq/L
abnormal_flag:         null
normalized_value_numeric: null                ← 归一化 4 字段(后续阶段填)
normalized_value_text:    null
normalized_unit:          null
unit_normalization_status: null

source_module:         mimic_iv_hosp          ← 溯源
source_table:          hosp.labevents
source_array_index:    3                      ← 源行数组下标
jsonl_line_number:     42                     ← 源 JSONL 行号
raw_row_ref:           "NEW-BATCH...#L42/mimic_iv_hosp.labevents[3]"
source_action:         null
quality_flags:         []                     ← 质量旗标
supporting_source_row_ids: []                 ← 支撑行血缘
supporting_raw_row_refs:  []
```

#### event_aggregation

- 原丢失的信息聚合

```json
// processed_events.parquet：事件 + 追加 7 列
{ ...原47列全部保留...,
  "source_record_id":"srec:a1b2c3d4e5f6a7b8c9d0e1f2",
  "source_text_field":"chiefcomplaint","source_text_kind":"chief_complaint",
  "source_text":"chest pain",                       // 逐字符原文，供 NER
  "supporting_source_record_ids":[] }

// raw_source_records.parquet：源行唯一一行（被多事件引用时去重）
{ "source_record_id":"srec:a1b2…","source_table":"ed.triage","source_array_index":0,
  "source_role":"event","source_text":"chest pain",
  "clinical_readable_record_json":"{…triage整行canonical JSON…}",
  "raw_record_json":"{…原始JSONL整行…}" }

// traceable_events.parquet：processed + 内嵌整行 JSON，审计用
```

ds-

#### phenotype

- 决策时刻快照
- 整理文本
- 挖掘RWD Gold



```text
CSV triage.chiefcomplaint="chest pain"
 → ① raw JSONL 第38行 ed.triage[0] 原样字符串
 → ③ symptom_reported 事件（assertion=present）
 → ③ 归一化 concept_id=symptom:chest_pain
 → ④ source_text="chest pain"（逐字符原文）
 → ⑤ symptom:1bce3b700f26488e 特征
 → ⑤ 条件组合成员
 → mining 条件规则 → MCQ 题干
```



## 评测层

```
### 检查、检验

### 诊断

### 治疗

### 分诊

### 随访
```

### V1-（固定 f-string）-检查数据集处理的问题

| 环节                     | 规模                                                         |
| ------------------------ | ------------------------------------------------------------ |
| 全量输入                 | MIMIC-IV 冠心病队列 **39,036 住院 / 20,136 患者**（`normalized_events.parquet`） |
| development split（60%） | **12,082 患者 / 23,626 住院** ← 655 道题从这里出             |
| validation split（20%）  | 4,027 患者 / 7,683 住院 ← 用来验证规则稳定性                 |
| final_test split（20%）  | 4,027 患者 / 7,727 住院 ← 只盲测一次，不再用于调参           |



| **selectivity**         | 特异性 lift（FDR），基于基线归一化 |   17 | **35.3%** ✅ |
| ----------------------- | ---------------------------------: | ---: | ----------: |
| likelihood              |                           条件概率 |   39 |       15.4% |
| psr                     |             概率 × 特异性 × 可靠性 |   30 |       23.3% |
| specificity×reliability |                    特异性 × 可靠性 |   30 |       23.3% |

- 检查检验是高先验的普适动作（CXR/Telemetry/BMP 几乎人人都做），会把起到筛选作用的检查/化验掩盖。

- 进一步筛选

- 数据集以ICU单病种为主，检查、化验单一，存在选择偏移
  - 分层抽样/随机抽样



### V2-规则组合





