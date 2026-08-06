# MIMIC 全诊疗过程多系统聚合实施方案

> 状态：需求已确认，待实现
>
> 适用数据：MIMIC-IV 3.1、MIMIC-IV-ED 2.2、MIMIC-IV-Note 2.2
>
> 当前任务：完成患者一次诊疗过程的多系统数据聚合
>
> 后续任务：从聚合结果中构建评测所需的结构化字段、问题与评分规则

## 1. 结论

本项目不再把“有出院小结的一次住院”作为唯一病例单位。权威数据层需要同时保存：

1. 未进入可匹配 MIMIC 住院的完整 ED episode；
2. 急诊后住院或直接住院的连续 episode；
3. episode 内的急诊、住院、ICU 和病区流转阶段；
4. 无法可靠归入某次就诊的门诊相关化验、影像、微生物和 OMR 事件；
5. 患者在本次就诊前已经可用的全部历史证据。

聚合的根不是单一原生 ID，而是项目定义的 `clinical_episode`：

```text
患者：subject_id
│
├─ 未进入可匹配 MIMIC 住院
│  └─ episode_id = E:{ed_stay_id}
│
├─ 急诊后住院或直接住院
│  └─ episode_id = H:{hadm_id}
│     ├─ ED care_contact
│     ├─ inpatient care_contact
│     ├─ ICU care_contact
│     └─ transfer care_contacts
│
└─ 无可靠就诊边界的门诊相关事件
   └─ subject_id + 原始事件 ID；episode_id 为空
```

当前 `outputs/stage1/case_index.parquet` 以可匹配的出院小结为入口，只覆盖 331,732 次住院，不能作为完整 episode 宇宙。新的聚合管线必须从 `admissions` 与 `edstays` 建立 episode，再把文本和结构化事件挂接进去。

## 2. 目标与边界

### 2.1 本任务必须完成

- 聚合 MIMIC-IV Hosp、ICU、ED 和 Note 中可用的文本与结构化事件；
- 建立统一的 episode、care contact、事件组、事件明细和文档表示；
- 保留所有原始 ID、原始值、原始文本、原始时间和来源版本；
- 区分原生关联、唯一时间关联和未解决关联；
- 区分事件发生时间、信息可用时间和记录时间；
- 保留医嘱、报告、给药和操作的完整状态变化链；
- 为所有标准化事件提供可回溯的证据锚点；
- 不因资料不完整而删除病例，只记录覆盖情况；
- 支持按需导出一个可阅读、可用于 Agent 输入的病例 JSON。

### 2.2 本任务明确不做

- 不生成具体评测问题、答案或评分器；
- 不划分训练集、验证集和测试集；
- 不把时间先后自动解释为医学因果关系；
- 不把 ICD、DRG 等后验编码当作早期诊断决策；
- 不把无 `hadm_id` 的事件全部标为门诊；
- 不按固定天数截断患者既往史；
- 不生成摘要、推理理由或其他模型合成文本；
- 不引入疾病中心知识图谱、PSR 排序、embedding 或人口级统计关系。

## 3. 本地数据核实结果

以下数字来自本地完整 CSV 的只读统计，用于确定实施边界，不包含患者级内容。

### 3.1 核心就诊标识

| 数据 | 本地结果 | 设计含义 |
|---|---:|---|
| 住院记录 | 546,028 | 546,028 个 `hadm_id` 均唯一 |
| 有住院记录的患者 | 223,452 | `subject_id` 不能代表一次就诊 |
| 有多次住院的患者 | 100,163 | 占住院患者约 44.8% |
| 单名患者最多住院次数 | 238 | 禁止按患者直接拼成一个病例 |
| 急诊记录 | 425,087 | 425,087 个 ED `stay_id` 均唯一 |
| 无后续住院 ID 的急诊 | 222,071 | 必须建立独立 ED episode，结局不一定是回家 |
| 急诊后住院 | 203,016 | 与匹配的 `hadm_id` 合成连续 episode |
| ICU stay | 94,458 | 全部具有 `hadm_id` |
| 包含多次 ICU stay 的住院 | 7,695 | ICU stay 是住院 episode 的子阶段 |
| transfer 记录 | 2,413,581 | `transfer_id` 表示物理位置阶段，不表示完整就诊 |

### 3.2 急诊事件覆盖

| 来源表 | 行数 | 覆盖的 ED stay | 关联核验 |
|---|---:|---:|---|
| `triage` | 425,087 | 425,087 | 无孤立 stay、无患者冲突 |
| `vitalsign` | 1,564,610 | 408,146 | 无孤立 stay、无患者冲突 |
| `diagnosis` | 899,050 | 423,989 | 后验诊断，不作为到院输入 |
| `medrecon` | 2,987,342 | 307,196 | 入急诊前用药核对 |
| `pyxis` | 1,586,053 | 303,361 | 药柜发药，不等同完整给药记录 |

### 3.3 门诊相关与未归属事件

| 数据 | 总行数 | 无 `hadm_id` | 严格落入 ED 时间窗 |
|---|---:|---:|---:|
| `labevents` | 158,374,764 | 73,768,897 | 14,408,892 个唯一事件 |
| `microbiologyevents` | 3,988,224 | 2,228,343 | 514,144 个唯一事件 |
| `radiology` | 2,321,355 | 1,176,597 | 206,015 份唯一报告 |
| `omr` | 7,753,027 | 表中没有 `hadm_id` | 只有日期，不能严格到时间 |

补充事实：

- OMR 覆盖 193,501 名患者和 2,916,137 个“患者—日期”，主要是血压、体重、BMI 和身高等门诊测量；
- 52,212,109 条 `poe`、17,847,567 条 `pharmacy` 和 20,292,611 条 `prescriptions` 在本地均具有 `hadm_id`，不能用它们恢复完整门诊医嘱链；
- 42,808,593 条 `emar` 中有 1,417,390 条缺少 `hadm_id`，但 eMAR 是院内床旁给药系统，不能把 ID 缺失解释成门诊给药；
- 无 `hadm_id` 的化验中仍有 1,525,147 个唯一事件落在住院时间窗内，说明“无住院 ID”不等于“门诊”；
- 无 `hadm_id` 的放射报告中有 16,127 份落在住院时间窗内；
- 无 `hadm_id` 的微生物记录中有 127,757 行落在住院时间窗内；
- OMR 只有日期：82,105 个患者日期与 ED 同日，195,814 个患者日期落在某次住院日期范围内，不能据此声明精确就诊归属。

结论：MIMIC 能较完整地重建急诊和住院事件过程，但门诊只能形成“患者级门诊相关事件流”，不能声称恢复了完整门诊诊疗全过程。

## 4. 核心领域模型

### 4.1 `clinical_episode`

表示一次具有可靠开始和结束边界的诊疗过程。

两种 episode 类型：

| `episode_type` | `episode_id` | 构建规则 |
|---|---|---|
| `hospital` | `H:{hadm_id}` | `admissions` 中每个合法 `hadm_id` 一条 |
| `emergency_department` | `E:{stay_id}` | ED 无 `hadm_id`，或给出的 `hadm_id` 无法与住院表和患者一致匹配 |

`hospital` episode 的范围：

- 有直接关联 ED stay：开始时间为最早关联 ED `intime`；
- 无关联 ED stay：开始时间为 `admittime`；
- `clinical_end_time` 为住院内死亡时间与出院时间中更早的有效时间；
- `administrative_end_time` 保留 `dischtime`；
- 所有直接关联到同一 `hadm_id` 的 ED stay 均保留并按时间排序，不只取第一条；
- ICU stay、transfer、service、检查、医嘱、治疗和文本均作为该 episode 的子对象或事件。

`emergency_department` episode 的范围：

- 开始时间为 ED `intime`；
- 结束时间为 ED `outtime`；
- `disposition` 是 episode 结局字段，不能作为更早时点的输入；
- 如果 ED 声称关联某个 `hadm_id`，但住院表中不存在或患者不一致，保留候选 `hadm_id` 和失败原因，不制造住院 episode。

### 4.2 `care_contact`

表示 episode 内不同系统或地点的接触阶段。

| 类型 | 原生键 | 说明 |
|---|---|---|
| `emergency_department` | ED `stay_id` | 急诊到院至离开急诊 |
| `inpatient` | `hadm_id` | 住院行政阶段 |
| `icu` | ICU `stay_id` | 一次连续 ICU 阶段，可在同一住院出现多次 |
| `transfer` | `transfer_id` | 一个物理病区/床位阶段 |

建议的稳定命名空间：

```text
episode_id: H:{hadm_id} / E:{ed_stay_id}
contact_id: ED:{stay_id} / IP:{hadm_id} / ICU:{stay_id} / TR:{transfer_id}
```

任何 ID 都必须与 `source_dataset`、`source_table` 一起解释。即使本地 ED 和 ICU `stay_id` 没有碰撞，也不允许脱离模块使用裸 `stay_id`。

### 4.3 `timeline_event` 与 `event_item`

`timeline_event` 对应临床上可理解的一次事件组，`event_item` 保存该事件中的全部原始明细。

```text
timeline_event
├─ event_items[]
└─ evidence_refs[]
```

事件组规则：

| 数据 | `timeline_event` | `event_item` |
|---|---|---|
| 普通化验 | 一份 `specimen_id` 标本/面板 | 每个 `labevent_id` 结果 |
| 微生物 | 一份 `micro_specimen_id` 标本 | 培养、病原体、药敏结果行 |
| 放射检查 | 一份 `note_id` 报告 | 检查代码、名称、正文段落及补充关系 |
| 医嘱 | 一条 `poe_id` 医嘱链 | 新建、修改、暂停、撤销等状态 |
| 药物 | 处方/药房链 | 药名、剂量、频次、途径和状态 |
| 给药 | 实际 eMAR 给药事件 | 实际剂量、途径、延迟、拒绝或未给 |
| OMR | 同一患者同一日期的测量组 | 每个 `seq_num` 原始测量；不代表一次门诊 |
| ED | 分诊、生命体征、用药核对、发药、诊断等事件组 | 对应原始行 |
| ICU | 观察、输入、输出、操作等事件组 | 对应 `itemid` 与原始行 |

事件组只增加临床可读性，不删除、合并或改写原始明细。必须验证每条源记录最终进入某个 `event_item`、`document` 或 `unresolved_event`。

## 5. 关联规则

所有事件使用以下互斥关联状态：

### 5.1 `native_link`

满足以下条件：

- 原始记录直接带有 `hadm_id` 或 `stay_id`；
- 对应 episode/contact 存在；
- `subject_id` 与目标 episode/contact 一致。

该关联可以进入 episode，并可作为后续严格评测的候选证据。

### 5.2 `unique_temporal_link`

仅在以下条件全部满足时建立：

- 原始记录没有可用的原生 episode/contact ID；
- `subject_id` 相同；
- `event_time` 严格落入某个 ED 或住院区间；
- 在同类候选 contact 中只命中一个区间；
- 不使用未声明的前后时间容差。

时间关联必须保存：匹配区间、匹配方法、候选数量和规则版本。它可以进入时间线，但必须与原生关联区分。

### 5.3 `unresolved`

出现以下任一情况时不归入具体 episode：

- 没有命中任何 episode/contact；
- 同时命中多个候选区间；
- 原生 ID 不存在于目标表；
- `subject_id` 与目标 ID 所属患者不一致；
- 只有日期，无法满足任务要求的时间精度；
- 时间字段缺失或逻辑冲突。

未解决事件继续保存在患者事件流中，并记录 `unresolved_reason`。不得静默丢弃，也不得作为某个 episode 的严格金标准证据。

### 5.4 关联优先级

```text
native_link > unique_temporal_link > unresolved
```

时间关联不能覆盖有效原生关联；原生 ID 出现患者冲突时必须判为未解决，不能用时间匹配掩盖冲突。

## 6. 时间语义与信息泄漏控制

每个事件最多保存三个时间：

| 字段 | 含义 |
|---|---|
| `event_time` | 检查、采样、医嘱、治疗或接触实际发生时间 |
| `available_time` | 该信息最早对医生或模型可见的时间 |
| `recorded_time` | 数据录入、完成或签署时间 |

同时保存：

- `time_precision`：`timestamp`、`date`、`encounter_start_proxy`、`unknown`；
- `available_time_source`：原生字段、事件时间等同、派生规则或未知；
- `start_time`、`end_time`：持续事件的开始和结束；
- 原始时间字段，不用标准化值覆盖原值。

### 6.1 主要来源映射

| 来源 | `event_time` | `available_time` | 说明 |
|---|---|---|---|
| ED triage | ED `intime` | ED `intime` | 原表无分诊时间，标记为代理时间 |
| ED vitals | `charttime` | `charttime` | 没有独立录入时间 |
| POE | `ordertime` | `ordertime` | 医嘱下达即为可见动作 |
| labevents | `charttime` | `storetime` | 通常分别对应采样与结果可见 |
| microbiology | `charttime`/`chartdate` | `storetime`/`storedate` | 日期级记录保留日期精度；当前只表示最后已知更新 |
| radiology note | `charttime` | `storetime` | `storetime` 缺失时不假定报告已可用 |
| discharge note | `charttime` | `storetime` | 不能用于更早决策时点 |
| prescriptions | `starttime` | 对应医嘱可用时间 | 药物计划与实际给药分开 |
| pharmacy | `entertime`/`starttime` | `verifiedtime` | 分别保留录入、核验和计划开始 |
| eMAR | `charttime` | `storetime` | 实际给药与记录时间分开 |
| OMR | `chartdate` | `chartdate` | 只有日期，不伪造具体时刻 |
| ICD/DRG | 临床发生时间可能未知 | `NULL`，标记 `post_episode_only` | 不进入早期决策输入 |

若 `available_time` 无法可靠确定，保持为空并记录原因。后续评测视图默认只允许：

```text
available_time <= decision_time
```

不得用 `COALESCE(recorded_time, event_time)` 静默制造信息可用时间。

## 7. 医疗决策与状态变化

### 7.1 决策证据等级

| 等级 | 定义 | 后续评测资格 |
|---|---|---|
| `observed_decision` | 数据中直接观察到的医嘱、治疗、检查申请、转科或去向 | 可作为候选金标准 |
| `documented_reasoning` | 文本明确记录的判断或理由，并具有原文证据范围 | 可作为候选金标准 |
| `inferred_relationship` | 根据时间顺序或共现推测的关系 | 只作研究辅助，不作严格金标准 |

必须遵守：

- 时间先后不自动等于因果关系；
- ICD、DRG、ED 出院诊断和 disposition 是后验信息；
- 出院小结是回顾性文档，不能泄漏到入院或住院早期；
- “检查后发生治疗”不能自动解释为“该检查导致治疗”。

### 7.2 状态变化链

不只保存最终状态，必须保留：

- POE 的新建、修改、暂停、撤销和完成；
- `discontinue_of_poe_id`、`discontinued_by_poe_id` 形成的医嘱链；
- 处方、药房记录和实际给药之间的关系；
- 已给、延迟、拒绝、漏给、停药等 eMAR 状态；
- 放射和出院文书的正文、addendum、parent/addendum 关系；
- 初步结果、更新结果和补充说明的各自可用时间。

旧记录不得被新记录覆盖。规范化层用 `supersedes_event_id`、`parent_event_id` 或关系表表达更新。

## 8. 既往背景与本次就诊

每个 episode 在逻辑上分为：

```text
clinical_episode
├─ prior_context
└─ current_episode
```

规则：

- `current_episode` 只包含本次 episode 开始至结束的事件；
- `prior_context` 引用所有 `available_time < episode_start_time` 的患者历史；
- 聚合阶段不设置 30 天、1 年等固定回溯窗口；
- 历史内容只保存引用，不为每个 episode 复制完整事件载荷；
- 本次 episode 结束后的事件继续进入患者历史，但不进入本次 current episode；
- 具体任务以后决定默认展示多少历史，以及 Agent 是否可以主动检索更多历史。

## 9. 原始证据、标准化事件与证据锚点

### 9.1 双轨保存

```text
raw_evidence                standardized_event
├─ source_dataset           ├─ event_type
├─ source_version           ├─ standardized_concept
├─ source_table             ├─ normalized_value
├─ native_row_key           ├─ normalized_unit
├─ raw_code                 ├─ clinical_display
├─ raw_value                └─ normalization_provenance
├─ raw_unit
├─ raw_text
└─ raw_timestamps
```

规则：

- ICD、CPT、HCPCS、NDC、GSN、`itemid` 等原始编码始终保留；
- 标准化值不覆盖原始值；
- 无法可靠映射的概念标记为 `unmapped`，不猜测；
- 每条标准化结果保存规则名称和规则版本；
- 更换标准化规则时不需要重新读取原始数据库。

### 9.2 强制证据锚点

结构化证据至少保存：

```text
source_table
native_row_key
source_columns
raw_value
```

文本证据至少保存：

```text
note_id
section_name
character_start
character_end
evidence_text
text_hash
```

文本偏移必须基于未改写的原始全文。分段、章节识别和标准化文本只能生成引用，不能替换原文。一个结论可以链接多个证据锚点；没有直接锚点的内容不能成为严格评测金标准。

## 10. 权威输出

Parquet 是完整聚合结果的权威存储；病例 JSON 只按需生成，不预先创建几十万个小文件。

### 10.1 `episode_index.parquet`

关键字段：

```text
episode_id
episode_type
subject_id
hadm_id
episode_start_time
clinical_end_time
administrative_end_time
outcome_type
linked_ed_contact_count
icu_contact_count
transfer_contact_count
source_versions
```

### 10.2 `care_contacts.parquet`

```text
contact_id
episode_id
subject_id
contact_type
hadm_id
stay_id
transfer_id
start_time
end_time
contact_sequence
link_method
source_table
```

### 10.3 `timeline_events.parquet`

```text
event_id
event_group_id
episode_id
contact_id
subject_id
event_type
event_subtype
event_time
available_time
recorded_time
time_precision
status
decision_evidence_level
link_status
normalization_status
source_table
source_version
```

### 10.4 `event_items.parquet`

```text
item_event_id
event_id
native_row_key
concept_id
concept_name
raw_code
raw_value
raw_unit
normalized_value
normalized_unit
flag
item_ordinal
```

### 10.5 `documents.parquet`

```text
note_id
subject_id
episode_id
contact_id
document_type
note_type
event_time
available_time
recorded_time
text
parent_note_id
addendum_note_id
link_status
source_table
source_version
```

### 10.6 `evidence_links.parquet`

```text
evidence_link_id
target_type
target_id
evidence_type
source_table
native_row_key
note_id
section_name
character_start
character_end
relationship_type
link_method
```

### 10.7 `patient_history_refs.parquet`

```text
episode_id
subject_id
referenced_type
referenced_id
available_time
history_relation
```

该表只保存引用，不复制事件或文档正文。

### 10.8 `episode_coverage.parquet`

至少包含：

```text
has_chief_complaint
has_triage_vitals
has_serial_vitals
has_laboratory
has_microbiology
has_radiology
has_orders
has_prescriptions
has_medication_administration
has_procedures
has_diagnoses
has_disposition
has_discharge_summary
laboratory_count
radiology_report_count
native_link_count
temporal_link_count
unresolved_event_count
first_event_time
last_event_time
```

不设置聚合准入阈值。缺失表示“数据库中未记录或当前不可用”，不能解释为“医生没有实施”。

### 10.9 `unresolved_events.parquet`

保存所有无法可靠归入 episode 的事件：

```text
event_id
subject_id
event_type
event_time
available_time
native_hadm_id
native_stay_id
candidate_episode_count
unresolved_reason
source_table
native_row_key
```

### 10.10 按需病例 JSON

```json
{
  "episode_id": "H:...",
  "patient": {},
  "prior_context": [],
  "current_episode": {
    "care_contacts": [],
    "timeline_events": [],
    "documents": []
  },
  "coverage": {},
  "provenance": {}
}
```

JSON 只是 Parquet 的确定性视图，不能包含 Parquet 中不存在的模型生成结论。

## 11. 数据源纳入顺序

### 11.1 episode 与 contact 基础

- `hosp/patients`
- `hosp/admissions`
- `hosp/transfers`
- `hosp/services`
- `ed/edstays`
- `icu/icustays`

### 11.2 早期状态与急诊过程

- `ed/triage`
- `ed/vitalsign`
- `ed/medrecon`
- `ed/pyxis`
- `ed/diagnosis`

### 11.3 检查与结果

- `hosp/labevents`、`hosp/d_labitems`
- `hosp/microbiologyevents`
- `note/radiology`、`note/radiology_detail`
- `hosp/omr`

### 11.4 医嘱、用药与操作

- `hosp/poe`、`hosp/poe_detail`
- `hosp/pharmacy`
- `hosp/prescriptions`
- `hosp/emar`、`hosp/emar_detail`
- `hosp/procedures_icd`
- `hosp/hcpcsevents`
- ICU `inputevents`、`ingredientevents`、`outputevents`、`procedureevents`

### 11.5 ICU 状态

- ICU `chartevents`
- ICU `datetimeevents`
- ICU `d_items`
- ICU `caregiver`

### 11.6 后验编码与长文本

- `hosp/diagnoses_icd`、`hosp/d_icd_diagnoses`
- `hosp/drgcodes`
- `note/discharge`、`note/discharge_detail`

这些来源完整保留，但必须根据可用时间和证据等级阻止后验信息进入早期评测视图。

## 12. 实现架构

### 12.1 保留现有第一阶段

当前第一阶段已验证：

- 固定 Python 3.12、uv 和 DuckDB 运行环境；
- 八张 CSV 的 schema 锁定；
- 出院与放射文档、detail、ED 分诊的基础关联；
- 流式写出宽文本，避免物理排序导致内存耗尽；
- 结果回读和患者级划分泄漏检查。

新聚合任务不修改这些输出的既有语义，也不依赖 `outputs/stage1` 才能运行。它复用同一运行时、路径验证、SQL 模板和质量报告机制，从原始 CSV 独立生成权威聚合表。

### 12.2 建议代码结构

```text
mimic_pipeline/
├─ source_catalog.py
├─ episode_pipeline.py
├─ episode_export.py
└─ ...现有第一阶段模块

sql/episode_aggregation/
├─ create_source_views.sql
├─ build_episodes.sql
├─ build_contacts.sql
├─ build_events.sql
├─ build_documents.sql
├─ build_evidence.sql
├─ build_history_refs.sql
├─ build_coverage.sql
├─ quality_checks.sql
└─ export_outputs.sql
```

`source_catalog.py` 以数据驱动方式集中维护来源文件、版本、schema、原生键和时间字段，避免在多个脚本中重复硬编码三次以上。

### 12.3 运行入口

统一入口扩展为：

```powershell
.\scripts\run_mimic_pipeline.ps1 -Task validate-episodes
.\scripts\run_mimic_pipeline.ps1 -Task aggregate-episodes
.\scripts\run_mimic_pipeline.ps1 -Task export-episode -EpisodeId 'H:...'
```

建议输出目录：

```text
outputs/episode_aggregation/
```

该目录已经由 `.gitignore` 的 `/outputs/` 规则排除。

## 13. 分阶段实现

### 阶段 A：来源目录与 schema 锁定

1. 建立全来源 catalog；
2. 锁定每张 CSV 的完整表头、原生键、关联键和时间字段；
3. 对重复原生键、空关键字段和跨表患者冲突建立失败测试；
4. 验证所有本地必需文件存在。

完成标准：任何源表变化必须在生成患者级输出前失败，不能静默忽略新列或缺列。

### 阶段 B：episode 与 care contact

1. 由 `admissions` 创建 `H:` episode；
2. 将合法 ED→住院关系挂入 `H:` episode；
3. 为没有后续住院 ID 或住院链接异常的 ED 建立 `E:` episode；
4. 添加 ICU、transfer 和 service 阶段；
5. 生成 episode/contact 完整性报告。

完成标准：原生 ID 唯一、患者一致、所有 ED stay 均被解释为已挂接或独立 episode。

### 阶段 C：高价值事件与文档

按以下顺序纳入：

1. ED triage、vitals、medrecon、pyxis、diagnosis；
2. radiology 与 discharge 文档及 addendum 关系；
3. labs、microbiology、OMR；
4. POE、pharmacy、prescriptions、eMAR；
5. procedures、transfers、services；
6. ICU 观察、输入输出和操作；
7. ICD、DRG 等后验编码。

每加入一种来源，必须同时完成 schema、分组、时间、关联、证据和守恒检查，不能先堆表后补质量规则。

### 阶段 D：历史引用与覆盖度

1. 生成 patient-level 时间索引；
2. 为 episode 创建全部可用历史引用；
3. 生成覆盖字段、数量和时间范围；
4. 不执行病例过滤。

### 阶段 E：单病例导出

1. 从 Parquet 按 `episode_id` 查询；
2. 按 `available_time`、`event_time` 和稳定业务键排序；
3. 输出 prior/current 分层 JSON；
4. 回查每个 evidence ref；
5. 对同一 episode 重复导出必须字节级稳定，允许显式声明的元数据除外。

## 14. 测试与质量检查

### 14.1 合成数据测试

合成数据至少覆盖：

- 同一患者多次住院；
- ED 后回家、ED 后住院、直接住院；
- 同一住院多次 ED/ICU/transfer；
- 原生 ID 不存在和患者冲突；
- 时间只命中一个、同时命中多个、未命中任何 episode；
- 化验采样早于结果可用；
- 文书 charttime 早于 storetime；
- 医嘱新建、修改和撤销；
- 放射主报告与 addendum；
- 缺失 available_time；
- OMR 仅日期；
- 不完整 episode 仍被保留；
- 历史事件只作为引用进入 prior context。

### 14.2 全量质量指标

每次全量运行至少报告：

- episode/contact/事件/明细/文档总数；
- 各来源输入行数与输出守恒；
- 原生关联、唯一时间关联和未解决数量；
- 未解决原因分布；
- episode/contact ID 重复数；
- `hadm_id`、`stay_id`、`note_id` 的患者冲突数；
- 时间逻辑冲突数；
- `available_time < event_time` 的来源分布，不静默修正；
- 事件组与明细的一对多完整性；
- 文档 addendum/parent 链完整性；
- evidence ref 无法回查数；
- 各覆盖字段的 episode 数；
- 写出后 Parquet 回读行数与 schema；
- 单病例 JSON 与 Parquet 的一致性。

### 14.3 硬性验收条件

- 重复 `episode_id`、`contact_id`、权威 `event_id` 为 0；
- 接受的原生关联中患者冲突为 0；
- 每条源记录必须进入事件、文档或未解决表，不能无解释消失；
- 每个标准化事件至少有一个可回查证据锚点；
- 未解决事件不能出现在 episode 严格证据集合；
- 后验编码和出院文档不能出现在更早的可用信息视图；
- 全量写出后可回读，行数、schema 和关键唯一性检查全部通过；
- 宽文本与高基数事件使用流式写出，不执行无业务价值的全局物理排序；
- 相同输入、代码和参数产生相同业务键与病例 JSON。

## 15. 性能与数据安全

- 1.58 亿条化验是主要 I/O 压力，按来源扫描和流式写出，避免把全量宽表一次性物化进内存；
- 物理 Parquet 行顺序不属于数据契约；需要稳定顺序时在查询或病例导出阶段使用业务键排序；
- 不把长文本参与全局排序；
- 每个阶段完成后立即回读验收，不能只相信写出命令成功；
- 原始 CSV、Parquet、DuckDB、病例 JSON、患者级日志和缓存均留在 Git 之外；
- 不把患者级内容发送到普通在线模型或 API；
- Git 只保存代码、schema、测试、聚合统计和不含患者内容的文档。

## 16. 与“评测结构化字段”任务的接口

本任务只提供事实与证据层。后续评测任务可以读取：

```text
episode_id
decision_time
available_event_refs
available_document_refs
observed_decision_refs
documented_reasoning_refs
coverage
provenance
```

后续任务再定义：

- 问题与答案；
- `answer_type`；
- 决策时点；
- 允许信息与排除的未来信息；
- 证据集合；
- 难度、操作要求和评分规则。

聚合层不预先决定疾病、任务类型或正确答案，避免为某个评测问题改写事实层。

## 17. 官方定义依据

- [MIMIC-IV schema overview](https://mimic.mit.edu/docs/IV/about/schema-overview.html)
- [MIMIC-IV core concepts](https://mimic.mit.edu/docs/IV/about/concepts.html)
- [MIMIC-IV Hosp](https://mimic.mit.edu/docs/IV/modules/hosp/)
- [MIMIC-IV ED](https://mimic.mit.edu/docs/IV/modules/ed/)
- [MIMIC-IV ICU](https://mimic.mit.edu/docs/IV/modules/icu/)
- [MIMIC-IV Note](https://mimic.mit.edu/docs/IV/modules/note/)
- [admissions](https://mimic.mit.edu/docs/IV/modules/hosp/admissions.html)
- [transfers](https://mimic.mit.edu/docs/IV/modules/hosp/transfers.html)
- [labevents](https://mimic.mit.edu/docs/IV/modules/hosp/labevents.html)
- [microbiologyevents](https://mimic.mit.edu/docs/IV/modules/hosp/microbiologyevents.html)
- [OMR](https://mimic.mit.edu/docs/IV/modules/hosp/omr.html)
- [edstays](https://mimic.mit.edu/docs/IV/modules/ed/edstays.html)
- [radiology](https://mimic.mit.edu/docs/IV/modules/note/radiology.html)
- [POE](https://mimic.mit.edu/docs/IV/modules/hosp/poe.html)
- [eMAR](https://mimic.mit.edu/docs/IV/modules/hosp/emar.html)
