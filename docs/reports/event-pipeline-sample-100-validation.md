# 100 例 `cleaned_events.parquet` 修复后验收报告

## 验收结论

**通过。当前 `cleaned_events.parquet` 已达到“可以开始确定性归一化准备”的标准。**

独立审计结果为：

```text
can_start_normalization = true
blocking_issue_codes = []
```

本轮只修复和重建 cleaning 层，没有运行归一化、NER 或外部模型。现有 `normalization/` 目录仍引用旧 cleaned 文件的 SHA-256，属于过期产物，不得继续使用；后续需要按独立方案重新生成。

机器可读证据：`docs/reports/cleaned-events-acceptance-audit.json`。复现脚本：`eda/analysis/audit_cleaned_events_acceptance.py`。

## 本轮修复

| 原阻断点 | 根修复 | 复验结果 |
|---|---|---|
| 68 条 discharge 为 `administrative_end` | `transform_discharge_note` 固定输出 `post_hoc` | 68/68 为 `post_hoc` |
| 5,169 条 prescription order time 没有支撑来源 | 使用已与 raw POE 交叉核验的 `poe_timeline` 源行作为时间来源，同时保存 `supporting_source_row_ids` 与 `supporting_raw_row_refs` | 5,169/5,169 条均有且仅有一个可解析支撑来源；14 条无法连接的处方时间继续保持空 |
| 3,248 条 POE 存在大小写重复 flag | 在事件写入边界将 flag 映射为冻结大写枚举并去重；schema 禁止非规范格式 | 大小写碰撞 0；非规范 flag 0 |
| 缺少 `cleaning_status` | 事件 schema 增加 `accepted`，拒绝表增加 `rejected` | 57,777 条 cleaned 全为 accepted；251 条 rejected 全为 rejected |

临床事件 schema 从 `clinical_event/1.0.0` 升级到 `clinical_event/1.1.0`；事件 ID 算法没有变化。

## 验收范围与方法

核验输入与产物：

- 原始 100 例：`data/validation/mimic-admission-raw-coronary-sample-100.jsonl`；
- 临床可读输入：`data/validation/mimic-admission-raw-coronary-sample-100-poe-timeline-decoded.jsonl`；
- `data/derived/event_pipeline_sample_100/cleaning/cleaned_events.parquet`；
- 同目录 rejected、encounter manifest、source reconciliation、term inventory 和 run manifest。

审计没有调用转换器或归一化器来复述自身结论，而是独立执行：

- 全部 57,777 条事件的 `raw_row_ref`、患者/住院归属、源表、数组下标、源行 ID、支撑来源与时间映射核验；
- 全部 251 条拒绝记录的来源和 reason code 复现；
- 全部 57,144 条纳入源行的 accepted/rejected 集合对账；
- 固定随机种子 `20260812`，每张源表抽 3 条，共留存 42 条抽样引用；
- 原始与 decoded 输入逐行比较：删除新增 `*_decoded` 和 `poe_timeline` 后，100/100 行身份及原始内容一致；
- 输入和输出 SHA-256 与 run manifest 对照。

## Parquet 结构

| 项目 | 实际值 |
|---|---:|
| 文件大小 | 4,152,121 bytes |
| 事件行数 | 57,777 |
| 字段数 | 44 |
| Row groups | 12（前 11 组各 5,000 行，末组 2,777 行） |
| Parquet format | 2.6 |
| 压缩 | ZSTD |
| Writer | parquet-cpp-arrow 25.0.1 |
| Arrow schema metadata | `clinical_event/1.1.0` |

关键类型：

- ID、类别、时间和文本：`string`；
- `source_array_index/jsonl_line_number`：`int64`；
- `value_numeric/normalized_value_numeric`：`double`；
- `quality_flags/supporting_source_row_ids/supporting_raw_row_refs`：`list<string>`。

完整 44 字段与类型已写入机器可读审计文件。Parquet schema 仍允许 nullable，但运行前 JSON Schema 和独立审计共同执行非空与条件门禁。

### 计划字段映射

| 计划字段 | 当前字段 | 结果 |
|---|---|---|
| `event_id`、`subject_id`、`hadm_id` | 同名 | 通过 |
| `source_module`、`source_table`、`source_row_id`、`raw_row_ref` | 同名 | 通过 |
| `event_kind` | 同名 | 通过 |
| `event_time`、`available_time`、`recorded_time` | 同名 | 通过 |
| `evidence_phase` | 同名 | 通过 |
| `raw_concept_code` | `source_concept_id` | 语义等价 |
| `raw_concept_term` | `source_label` | 语义等价 |
| `parsed_value` | `value_numeric/value_text/value_structured_json` | 类型拆分，语义等价 |
| `quality_flags` | 同名 `list<string>` | 通过，冻结大写枚举 |
| `cleaning_status` | 同名 | 通过 |
| 跨表支撑来源 | `supporting_source_row_ids/supporting_raw_row_refs` | 通过 |

`normalization_status` 继续只表达归一化状态，在 cleaned 文件中为空，不与 `cleaning_status` 混用。

## 事件化结果

| 源表 | accepted 源行 | 事件数 | `event_kind` |
|---|---:|---:|---|
| `ed.triage` | 35 | 259 | symptom 35；vital 190；acuity 34 |
| `ed.vitalsign` | 160 | 820 | `vital_measured` |
| `hosp.labevents` | 21,225 | 21,225 | `laboratory_resulted` |
| `hosp.microbiologyevents` | 379 | 379 | `microbiology_resulted` |
| `hosp.poe_timeline` | 12,773 | 12,773 | lab order 2,277；imaging order 415；clinical order 10,081 |
| `hosp.prescriptions` | 5,183 | 5,183 | `medication_ordered` |
| `hosp.pharmacy` | 4,349 | 4,349 | `medication_order_status_recorded` |
| `hosp.emar` | 11,343 | 11,343 | administered 7,677；not administered 1,613；documented 2,053 |
| `hosp.services` | 109 | 109 | `service_changed` |
| `hosp.transfers` | 389 | 389 | `patient_transferred` |
| `hosp.procedures_icd` | 225 | 225 | `procedure_recorded_post_hoc` |
| `icu.procedureevents` | 348 | 348 | `procedure_performed` |
| `note.radiology` | 307 | 307 | `imaging_reported` |
| `note.discharge` | 68 | 68 | `document_recorded` |

事件总数和顺序与修复前一致，57,777 个 `event_id` 完全不变。逐字段差异严格限定为：

- 57,777 条 schema version 更新；
- 新增 `cleaning_status` 与 `supporting_raw_row_refs`；
- 68 条 discharge phase 修正；
- 5,169 条 prescription 增加支撑来源；
- 4,024 条事件的 quality flag 被规范为冻结大写编码，其中原 3,248 条大小写语义重复被合并。

没有删除字段，没有改变原始临床值。

## 可追溯性

- 57,777/57,777 条事件的主 `raw_row_ref` 可解析；
- 患者、住院、模块、源表、源数组下标和 `source_row_id` 全部一致；
- 5,169 条有 order time 的 prescription 均可通过 `supporting_raw_row_refs` 回到同住院、同 `poe_id`、同时间的 `hosp.poe_timeline` 行；
- 14 条没有可验证 POE 时间的 prescription 继续保持时间为空，并标记 `ORDER_TIME_UNRESOLVED`；
- 251 条 rejected 全部回到 `hosp.pharmacy` 的空 medication 源行；
- `event_id` 57,777 个，无空值、无重复。

这里没有用 prescription `starttime` 代替 order time，也没有用文本相似度猜连接。

## 时间语义

| 来源 | 复验结果 |
|---|---|
| `labevents` | `event_time=charttime`；`available_time=recorded_time=storetime`；104 条缺 storetime，保持空并标志 |
| `radiology` | `event_time=charttime`；`available_time=recorded_time=storetime`；307 条均完整 |
| `poe_timeline` | `event_time=available_time=event_time`；12,773 条已与 raw POE ordertime 交叉检查 |
| `prescriptions` | 5,169 条引用 POE timeline 时间及来源；14 条保持空 |
| `ed.triage` | 259 条事件三类时间均空，状态为 unresolved |
| `ed.vitalsign` | 820 条仅有 event_time，available/recorded 保持空 |
| `transfers` | 389 条仅以 intime 作为 event_time，其他时间保持空 |
| `procedures_icd` | 225 条全部 `post_hoc` |
| `note.discharge` | 68 条全部 `post_hoc`，`available_time=recorded_time=storetime` |
| ICU procedure | 348 条使用 starttime/storetime；105 条按完成时间派生 available time 并显式标志 |
| eMAR | 266 条 storetime 早于 charttime，保留原值并显式标志 |

没有发现时间语义不匹配或静默填补。

## 清洗对账

| 分类 | 行数 |
|---|---:|
| 输入源行 | 57,144 |
| accepted 源行 | 56,893 |
| rejected 源行 | 251 |
| 事件行 | 57,777 |

每张源表及总计均满足：

```text
input source rows = accepted source rows + rejected source rows
57,144 = 56,893 + 251
```

accepted 按每张表的唯一 `source_row_id` 计数，不按事件数计数。

## 下一步分流

| 数据 | 下一步处理 |
|---|---|
| vitals、lab、microbiology、POE、prescription、pharmacy、eMAR、services、transfers、ICD、ICU procedure | Python 确定性归一化 |
| 已解码 lab/item/ICD 概念 | 直接使用源编码和官方字典，不进入 LLM |
| 35 条 chief complaint | Python 词典/规则优先，未解析项进入人工或 NER 队列 |
| 307 份 radiology 文本 | 单独建立文档/章节层后筛选 NER |
| 68 份 discharge 文本 | 单独建立文档/章节层后筛选 NER，所有产物继承 `post_hoc` |
| 时间或来源仍不可靠的条目 | review 或 rejected 队列，不猜测、不自动填补 |

Note 全文没有进入 `cleaned_events.parquet`；后续 NER 不应把整张事件表交给模型。任何模型调用仍需单独授权。

## 当前产物状态

| 产物 | 状态 |
|---|---|
| `cleaning/cleaned_events.parquet` | 通过，可作为后续输入 |
| `cleaning/cleaning_rejected.parquet` | 通过 |
| `cleaning/source_reconciliation.json` | 通过 |
| `cleaning/run_manifest.json` | 通过，run ID `4d438ffc0e328d65c21fa4eb` |
| `cleaning/term_inventory.parquet` | 随通过的 cleaning 层重新生成，可进入后续确定性映射 |
| `normalization/` | **过期，不可使用**；manifest 仍引用旧 cleaned SHA-256 |

当前 cleaned SHA-256：

```text
f9b485bf227c95a2d36413309111a8fb0da66dee9fb4fbcf28c6b1412a43fe97
```

旧 normalization manifest 引用：

```text
edf5296f5f73f3d50c628d7277bff80790b992b5bc7a99171cafbdf6e1a33a5a
```

二者不同，因此旧 normalization 不能被误认为当前 cleaning 的下游。

## 验证与复现

```powershell
.\.venv\Scripts\python.exe -m unittest -v `
  tests.test_event_pipeline `
  tests.test_event_pipeline_viewer

.\.venv\Scripts\python.exe -m eda.analysis.audit_cleaned_events_acceptance `
  --cleaned data\derived\event_pipeline_sample_100\cleaning\cleaned_events.parquet `
  --rejected data\derived\event_pipeline_sample_100\cleaning\cleaning_rejected.parquet `
  --source-jsonl data\validation\mimic-admission-raw-coronary-sample-100-poe-timeline-decoded.jsonl `
  --raw-source-jsonl data\validation\mimic-admission-raw-coronary-sample-100.jsonl `
  --reconciliation data\derived\event_pipeline_sample_100\cleaning\source_reconciliation.json `
  --manifest data\derived\event_pipeline_sample_100\cleaning\run_manifest.json `
  --output-json docs\reports\cleaned-events-acceptance-audit.json
```

当前结果：39 项相关测试通过，独立审计阻断计数为 0；使用最终代码重建的全部 cleaning 文件与 canonical 结果字节级一致。
