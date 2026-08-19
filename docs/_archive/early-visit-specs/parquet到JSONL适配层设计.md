# G 盘 parquet -> visit 级 JSONL 适配层设计

> **生成日期**: 2026-08-07
> **输入**: G:/Projects/医疗数据集评测-MIMIC/outputs/episodes/（9 张 parquet，~58GB）
> **输出**: rwd_benchmark_visits.jsonl（47 字段，~26GB 原始 / ~5-7GB gzip）
> **核心思路**: 复用 G 盘已完成的事件解析和关联，跳过原始 .csv.gz 重新解析；仅从 patients.csv.gz 补 age/sex

---

## 一、为什么从 G 盘 parquet 提取

| 维度 | 从 .csv.gz 原始表 | 从 G 盘 parquet |
|---|---|---|
| chartevents 解压 | 11 分钟 | 0（已在 parquet，且直接排除） |
| labevents 解压 | 6 分钟 | 0（已在 parquet） |
| emar+emar_detail 解压 | 5 分钟 | 0 |
| 事件关联 | 需自行实现 | 已完成（2.25 亿 native_link，1.3% unresolved） |
| 值标准化 | 需自行映射 | 已完成（normalized_value / normalized_unit） |
| 概念命名 | 需 JOIN 字典表 | 已内嵌（concept_name） |
| 原始行数据 | 直接读 | 保留在 event_items.raw_payload（JSON） |
| 预估总耗时 | 数小时 | 数十分钟 |

---

## 二、G 盘数据模型回顾

### 2.1 9 张 parquet 的角色

| 表 | 行数 | 角色 | 适配层用法 |
|---|---|---|---|
| episode_index | 545,880 hospital | 每个住院一行，含 hadm_id/admission_type/location | 主表，定义 eligible visit |
| care_contacts | 3,069,421 | care-unit 级 contact 映射 | 取 transfer_path（contact_type='transfer'）+ ICU 标记 |
| timeline_events | 238,203,827 | 每个临床事件一行，含 episode_id/event_type/event_time | 按 event_type 路由到不同 JSONL 字段 |
| event_items | 892,073,791 | 事件明细，含 concept_name/raw_value/normalized_value/raw_payload | 按 source_table 过滤 ICU 后提取值 |
| evidence_links | 900,934,117 | 事件到文档的链接 | 不使用（出题层按需） |
| documents | 2,652,892 | note 全文（DS/RR/AR） | 取 DS 做章节解析，取 RR 做影像报告 |
| episode_coverage | 767,971 | 每 episode 的覆盖标记 | 用于质量统计，不参与提取 |
| patient_history_refs | 767,971 | 跨 episode 引用 | 不使用 |
| unresolved_events | 13,067,505 | 未关联事件 | 不使用 |

### 2.2 关联链

```
episode_index.episode_id ── 1:N ──→ timeline_events.episode_id
                                 ── 1:N ──→ care_contacts.episode_id
                                 ── 1:N ──→ documents.episode_id

timeline_events.event_id ──── 1:N ──→ event_items.event_id
```

### 2.3 event_type 到 JSONL 字段的映射

G 盘的 timeline_events.event_type 直接对应 JSONL 字段组：

| event_type | JSONL 目标 | ICU 排除 |
|---|---|---|
| laboratory_panel | investigations.laboratory | 保留 |
| microbiology_specimen | investigations.microbiology | 保留 |
| provider_order (Radiology/Cardiology/Respiratory) | investigations.radiology/cardiology/respiratory | 保留 |
| prescription | treatments.medications | 保留 |
| pharmacy_order | treatments.pharmacy_orders | 保留 |
| medication_administration | treatments.medication_administrations | 保留 |
| diagnosis_code | diagnoses.primary / other | 保留 |
| procedure_code | treatments.procedures | 保留 |
| ed_diagnosis_code | diagnoses.ed_diagnoses | 保留 |
| ed_triage | vitals | 保留 |
| ed_vital_signs | （备用，当前不提取） | 保留 |
| transfer | disposition.transfer_path | 保留 |
| service_transfer | disposition.primary_service | 保留 |
| drg_code | disposition.drg | 保留 |
| icu_observation / icu_input / icu_output / icu_ingredient_input / icu_datetime_observation / icu_procedure | **排除** | 排除 |

### 2.4 raw_payload 的价值

event_items.raw_payload 是原始源表行数据的完整 JSON。例如 labevents 的 raw_payload：

```json
{"subject_id":"10000032","hadm_id":"29079034","stay_id":"39553978","charttime":"2180-07-23 12:36:00","itemid":"50912","value":"1.5","valuenum":"1.5","valueuom":"mg/dL","ref_range_lower":"0.4","ref_range_upper":"1.1","flag":"abnormal"}
```

这意味着适配层可以从 raw_payload 提取任何字段（itemid/valuenum/ref_range/flag），无需回到原始 .csv.gz。

### 2.5 数据缺口

G 盘 parquet 不包含以下信息，需从原始 .csv.gz 补充：

| 缺口 | 来源 | 补法 |
|---|---|---|
| age / sex | patients.csv.gz（364,627 行） | 按 subject_id 关联，加载到内存 dict |
| DS 章节解析 | documents.text（在 parquet 里） | 在适配层 Python 解析，不需原始表 |

---

## 三、适配层架构

### 3.1 处理流程

```
Phase 0  加载 patients.csv.gz -> age/sex 内存 dict
Phase 1  过滤 eligible episode（age>=18 + 有效主诊断 + 有效 DS）
Phase 2  按 event_type 批量聚合（DuckDB SQL，排除 ICU）
Phase 3  DS 章节解析（Python，对 documents.text）
Phase 4  组装 JSON 对象 + 写入 JSONL
```

### 3.2 Phase 0: 加载 patients

patients.csv.gz 仅 364,627 行，加载到内存 dict：

```python
patients = {}
for row in read_gzip('patients.csv.gz'):
    sid = row['subject_id']
    patients[sid] = {
        'anchor_age': int(row['anchor_age']),
        'anchor_year': int(row['anchor_year']),
        'gender': row['gender']
    }
```

### 3.3 Phase 1: 过滤 eligible episode

从 episode_index 取全部 hospital episode（545,880 行），逐条过滤：

```sql
-- Step 1a: 有效主诊断（从 timeline_events 取 diagnosis_code seq_num=1）
CREATE TEMP TABLE eligible_dx AS
SELECT te.episode_id
FROM timeline_events te
JOIN event_items ei ON te.event_id = ei.event_id
WHERE te.event_type = 'diagnosis_code'
  AND ei.raw_payload LIKE '%seq_num%1%'  -- 粗筛
  AND te.episode_id IN (SELECT episode_id FROM episode_index WHERE episode_type='hospital')
GROUP BY te.episode_id;

-- Step 1b: 有效 DS（从 documents 取 note_type=DS 且 text 非空）
CREATE TEMP TABLE eligible_ds AS
SELECT DISTINCT episode_id
FROM documents
WHERE note_type = 'DS' AND length(text) > 0;

-- Step 1c: eligible = 有 hadm_id + 有效主诊断 + 有效 DS
CREATE TEMP TABLE eligible AS
SELECT ei.episode_id, ei.hadm_id, ei.subject_id
FROM episode_index ei
WHERE ei.episode_type = 'hospital'
  AND ei.hadm_id IS NOT NULL
  AND ei.episode_id IN (SELECT episode_id FROM eligible_dx)
  AND ei.episode_id IN (SELECT episode_id FROM eligible_ds);
```

age >= 18 和 sex 有效在 Phase 4 用 patients dict 检查（避免在 SQL 里 JOIN 36 万行 dict）。

### 3.4 Phase 2: 按 event_type 批量聚合

这是适配层的核心。对每个 event_type 组，用 DuckDB SQL 批量聚合到 episode 级：

```sql
-- laboratory_panel: 按 episode + concept_name 聚合，保留全时序
CREATE TEMP TABLE agg_lab AS
SELECT
    te.episode_id,
    ei.concept_name AS label,
    list({
        'charttime': te.event_time,
        'value': ei.raw_value,
        'valuenum': ei.normalized_value,
        'valueuom': ei.raw_unit,
        'flag': ei.flag
    }) AS results
FROM timeline_events te
JOIN event_items ei ON te.event_id = ei.event_id
WHERE te.event_type = 'laboratory_panel'
  AND te.episode_id IN (SELECT episode_id FROM eligible)
  AND ei.source_table LIKE '%/labevents%'
GROUP BY te.episode_id, ei.concept_name;

-- diagnosis_code: 按 seq_num 分离主诊断和其他诊断
CREATE TEMP TABLE agg_dx AS
SELECT
    te.episode_id,
    json_extract_string(ei.raw_payload, 'icd_code') AS icd_code,
    json_extract_string(ei.raw_payload, 'icd_version') AS icd_version,
    ei.concept_name AS diagnosis_name,
    CAST(json_extract_string(ei.raw_payload, 'seq_num') AS INTEGER) AS seq_num
FROM timeline_events te
JOIN event_items ei ON te.event_id = ei.event_id
WHERE te.event_type = 'diagnosis_code'
  AND te.episode_id IN (SELECT episode_id FROM eligible);

-- medication_administration: 排除 ICU 来源
CREATE TEMP TABLE agg_emar AS
SELECT
    te.episode_id,
    te.event_time AS charttime,
    json_extract_string(ei.raw_payload, 'medication') AS medication,
    json_extract_string(ei.raw_payload, 'event_txt') AS event_txt,
    ei.raw_payload AS full_payload
FROM timeline_events te
JOIN event_items ei ON te.event_id = ei.event_id
WHERE te.event_type = 'medication_administration'
  AND te.episode_id IN (SELECT episode_id FROM eligible)
  AND ei.source_table LIKE '%/hosp/emar%'
ORDER BY te.episode_id, te.event_time;

-- transfer: 取转运路径
CREATE TEMP TABLE agg_transfer AS
SELECT
    te.episode_id,
    json_extract_string(ei.raw_payload, 'eventtype') AS eventtype,
    json_extract_string(ei.raw_payload, 'careunit') AS careunit,
    te.event_time AS intime,
    json_extract_string(ei.raw_payload, 'outtime') AS outtime
FROM timeline_events te
JOIN event_items ei ON te.event_id = ei.event_id
WHERE te.event_type = 'transfer'
  AND te.episode_id IN (SELECT episode_id FROM eligible)
ORDER BY te.episode_id, te.event_time;
```

其余 event_type（microbiology_specimen / prescription / pharmacy_order / procedure_code / ed_diagnosis_code / service_transfer / drg_code / ed_triage）同理，每个一段 SQL。

### 3.5 Phase 3: DS 章节解析

从 documents 取 DS note，用 Python 正则解析章节（算法见 出题数据抽取规范.md 第五节）：

```python
# 对每个 eligible episode 取选定的 DS
ds_sql = """
    SELECT episode_id, note_id, note_seq, event_time, text
    FROM documents
    WHERE note_type = 'DS'
      AND episode_id IN (SELECT episode_id FROM eligible)
    ORDER BY episode_id, note_seq DESC, event_time DESC
"""

# 对每个 episode 选 DS（有非空 Chief Complaint 的最新一条）
# 然后解析章节
```

### 3.6 Phase 4: 组装 JSON + 写入

```python
for episode_id in eligible_episodes:
    # 从 patients dict 取 age/sex
    p = patients[subject_id]
    age = p['anchor_age'] + year(admittime) - p['anchor_year']
    if age < 18 or p['gender'] not in ('M', 'F'):
        continue

    # 组装 8 个顶层分组
    visit = {
        'identifiers': {'subject_id': str(subject_id), 'hadm_id': str(hadm_id)},
        'demographics': {...},
        'vitals': {...},
        'narrative': {...},
        'investigations': {...},
        'diagnoses': {...},
        'treatments': {...},
        'disposition': {...}
    }

    # 写一行 JSONL
    f.write(json.dumps(visit, ensure_ascii=False) + '\n')
```

---

## 四、ICU 排除策略

两层过滤，确保 ICU 连续监测数据不进入输出：

### 4.1 event_type 过滤

排除以下 event_type 的全部 timeline_events：

| event_type | 说明 |
|---|---|
| icu_observation | chartevents 生命体征/GCS/呼吸机 |
| icu_input | inputevents 输液/药物 |
| icu_output | outputevents 尿量/引流 |
| icu_ingredient_input | ingredientevents 药物成分 |
| icu_datetime_observation | datetimeevents 时间型事件 |
| icu_procedure | procedureevents ICU 操作 |

### 4.2 source_table 过滤

```sql
AND ei.source_table NOT LIKE '%/icu/chartevents'
AND ei.source_table NOT LIKE '%/icu/inputevents'
AND ei.source_table NOT LIKE '%/icu/outputevents'
AND ei.source_table NOT LIKE '%/icu/datetimeevents'
AND ei.source_table NOT LIKE '%/icu/ingredientevents'
AND ei.source_table NOT LIKE '%/icu/procedureevents'
```

icustays 保留（从 care_contacts 取 contact_type='icu' 的时长信息）。

---

## 五、性能设计

### 5.1 批处理策略

不逐 episode 查询（300K 次 SQL 查询太慢），而是按 event_type 批量聚合：

```
对每个 event_type 组：
  1. DuckDB SQL: WHERE episode_id IN eligible AND event_type = 'xxx'
  2. GROUP BY episode_id（或 ORDER BY episode_id, event_time）
  3. fetchall() -> Python dict[episode_id] -> [events]
```

8 个 event_type 组 x 1 次批量查询 = 8 次 DuckDB 全表扫描。

### 5.2 预估耗时

| 阶段 | 耗时预估 | 说明 |
|---|---|---|
| Phase 0 patients 加载 | < 5s | 36 万行 dict |
| Phase 1 eligible 过滤 | ~2min | 3 次全表扫描（episode_index + timeline_events + documents） |
| Phase 2 批量聚合 | ~15-30min | 8 次 event_type 组扫描，排除 ICU 后 ~5.5 亿行 |
| Phase 3 DS 解析 | ~5min | ~33 万条 DS 章节正则 |
| Phase 4 组装写入 | ~5min | ~30 万行 JSON 序列化 |
| **合计** | **~30-45min** | 对比从原始表：数小时 |

### 5.3 内存策略

| 数据 | 大小 | 策略 |
|---|---|---|
| patients dict | ~50MB | 全量内存 |
| eligible episode set | ~10MB | 全量内存 |
| 聚合结果（per event_type） | 流式 | DuckDB fetchmany 逐批 |
| DS text | ~1.8GB | 按 episode_id 分批 |
| JSONL 输出 | 流式 | 逐行写入，不累积 |

### 5.4 并行化（可选）

DuckDB 支持多线程。Phase 2 的 8 个 event_type 组可以并行执行（各自独立 SQL）。
Phase 3-4 按 episode_id 分片并行（如 4 个线程各处理 1/4 eligible episode）。

---

## 六、适配层代码结构

```
src/parquet_to_jsonl/
  adapter.py          -- 主入口，协调 Phase 0-4
  eligibility.py      -- Phase 1: eligible episode 过滤
  aggregators.py      -- Phase 2: 按 event_type 聚合 SQL
  ds_parser.py        -- Phase 3: DS 章节解析（复用已有逻辑）
  assembler.py        -- Phase 4: JSON 对象组装
  config.py           -- 路径、event_type 映射、排除规则
```

运行方式：

```bash
python -m src.parquet_to_jsonl.adapter \
    --parquet-dir 'G:/Projects/医疗数据集评测-MIMIC/outputs/episodes' \
    --patients 'D:/Projects/llm_benchmark/data/RawData/mimic-iv-3.1/hosp/patients.csv.gz' \
    --output 'D:/Projects/llm_benchmark/data/rwd_benchmark_visits.jsonl' \
    --batch-size 10000
```

---

## 七、与原始表提取的对比

| 维度 | 从 .csv.gz 提取 | 从 G 盘 parquet 适配 |
|---|---|---|
| 源数据解析 | 需解压 41 张 .csv.gz | 直接读 parquet（已解压+已关联） |
| 事件关联 | 自行实现 hadm_id 关联 | 复用 episode_id（已关联） |
| 值标准化 | 自行映射 valuenum/unit | 复用 normalized_value/unit |
| 概念命名 | JOIN d_labitems/d_items | 复用 concept_name |
| ICU 排除 | 不读取 6 张表 | SQL WHERE 过滤 |
| 预估耗时 | 数小时 | ~30-45min |
| 数据等价性 | 完全等价（非 ICU 部分） | 完全等价 |
| 风险 | 低（直接控制） | 依赖 G 盘 pipeline 质量（quality_report 已验证） |

### 风险与缓解

| 风险 | 缓解 |
|---|---|
| G 盘 unresolved_events 1.3% | quality_report 显示 0 重复/0 orphan，可接受；抽取后验证 eligible_count |
| raw_payload JSON 解析失败 | 对每条记录 try/except，记录 episode_id + event_id，不阻断 |
| concept_name 与 d_labitems.label 不一致 | 抽取后抽样校验，不一致时从 raw_payload.itemid 补 label |
| patients dict 内存 | 36 万行 ~50MB，无风险 |

---

## 八、验收标准

| 检查项 | 标准 |
|---|---|
| JSONL 行数 | == eligible episode 数（age>=18 + 有效主诊断 + 有效 DS） |
| 每行 JSON 合法 | json.loads 成功率 100% |
| hadm_id 唯一 | 0 重复 |
| 必需字段非 null | subject_id/hadm_id/age/sex/admission_type/chief_complaint/primary_icd_code 全部非 null |
| 无 ICU 连续监测 | investigations/treatments 中 source_table 不含 icu/chartevents 等 6 表 |
| Lab 全时序 | 同一 itemid 的 results 数组长度 >= 1 且按 charttime 升序 |
| DS 章节一致性 | discharge_note_full 包含各章节子串 |
| 字段填充率 | 47 字段各报非 null 比例 |
| 平均行大小 | ~88KB +/- 20% |
| 处理耗时 | < 60min |
