# 100 例 `cleaned_events.parquet` 独立验收报告

## 验收结论

**不通过。当前 `cleaned_events.parquet` 不能作为归一化输入，也不能开始全量 NER。**

文件的基础事件化大部分正确：57,777 个 `event_id` 全部非空且唯一；57,777 条事件和 251 条拒绝记录均能通过 `raw_row_ref` 回查；14 张纳入源表都满足源行级 `input = accepted + rejected`；检验、影像、POE、ICU procedure 等已检查时间字段没有被静默填补。

但发现 4 类阻断问题：

1. 68 条出院小结被标为 `administrative_end`，没有按项目数据契约标为 `post_hoc`；
2. 5,169 条处方事件的下单时间来自另一张 `hosp.poe` 源行，但没有记录该支撑源行；
3. 3,248 条类别级 POE 事件同时包含大小写不同、语义相同的质量标志；
4. `cleaned_events.parquet` 没有显式 `cleaning_status` 字段。

同目录已经存在的 `term_inventory.parquet` 和 `normalization/` 产物是在本次验收通过前生成的。它们与当前文件哈希可以内部一致，但上游清洗层未通过，因此不得作为后续正式数据；修正转换规则并重新验收后必须重新生成，不能在现有归一化文件上打补丁。

机器可读证据见 `docs/reports/cleaned-events-acceptance-audit.json`。审计脚本为 `eda/analysis/audit_cleaned_events_acceptance.py`。

## 验收范围与方法

本次只读检查以下文件：

- 原始 100 例：`data/validation/mimic-admission-raw-coronary-sample-100.jsonl`；
- 事件管线输入：`data/validation/mimic-admission-raw-coronary-sample-100-poe-timeline-decoded.jsonl`；
- `cleaned_events.parquet`、`cleaning_rejected.parquet`；
- `source_reconciliation.json`、`run_manifest.json`；
- 事件 schema、来源注册表、转换与时间解析代码。

审计不调用事件转换器、归一化器或外部模型。它独立完成：

- 全部 57,777 条事件的来源位置、患者/住院归属、源表、源数组下标、`source_row_id` 和时间规则核验；
- 全部 251 条拒绝记录的来源与拒绝原因复现；
- 全部 57,144 条纳入源行的 accepted/rejected 集合对账；
- 按固定随机种子 `20260812`，每张源表抽取 3 条，共 42 条事件留存抽样引用；
- 原始 100 例与 decoded 输入逐行比较：删除新增的 `*_decoded` 和 `poe_timeline` 字段后，100/100 行身份与原始内容完全一致。

当前 decoded 输入的 SHA-256 与事件 `run_manifest.json` 一致；`cleaned_events.parquet` 和 `cleaning_rejected.parquet` 的 SHA-256 也都一致。项目内没有找到专属于这个 decoded 文件的上游运行报告，因此本次用逐行等价审计补足了当前快照验证；全量重跑时仍应让临床可读层 manifest 显式记录原始输入与输出哈希，形成连续 provenance chain。

复现命令：

```powershell
.\.venv\Scripts\python.exe -m eda.analysis.audit_cleaned_events_acceptance `
  --cleaned data\derived\event_pipeline_sample_100\cleaning\cleaned_events.parquet `
  --rejected data\derived\event_pipeline_sample_100\cleaning\cleaning_rejected.parquet `
  --source-jsonl data\validation\mimic-admission-raw-coronary-sample-100-poe-timeline-decoded.jsonl `
  --raw-source-jsonl data\validation\mimic-admission-raw-coronary-sample-100.jsonl `
  --reconciliation data\derived\event_pipeline_sample_100\cleaning\source_reconciliation.json `
  --manifest data\derived\event_pipeline_sample_100\cleaning\run_manifest.json `
  --output-json docs\reports\cleaned-events-acceptance-audit.json
```

## 文件结构与 Parquet 元数据

| 项目 | 实际值 |
|---|---:|
| 文件大小 | 4,065,718 bytes |
| 事件行数 | 57,777 |
| 字段数 | 42 |
| Row groups | 12（前 11 组各 5,000 行，末组 2,777 行） |
| Parquet format | 2.6 |
| 压缩 | ZSTD |
| Writer | parquet-cpp-arrow 25.0.1 |
| Arrow schema metadata | `clinical_event/1.0.0` |

关键类型：ID、类别、时间和文本字段为 `string`；`source_array_index/jsonl_line_number` 为 `int64`；`value_numeric/normalized_value_numeric` 为 `double`；`quality_flags/supporting_source_row_ids` 为 `list<string>`。完整 42 字段及类型已写入机器可读审计文件。

Parquet schema 把全部字段声明为 nullable；当前文件中的 `event_id` 实际无空值。非空和条件必填约束目前主要依赖写入前 JSON Schema 校验，而不是 Parquet schema 本身。

### 计划字段与实际字段

| 计划字段 | 实际结果 | 判定 |
|---|---|---|
| `event_id`、`subject_id`、`hadm_id` | 同名字段 | 存在 |
| `source_module`、`source_table`、`source_row_id`、`raw_row_ref` | 同名字段 | 存在 |
| `event_kind` | 同名字段 | 存在 |
| `event_time`、`available_time`、`recorded_time` | 同名字段 | 存在 |
| `evidence_phase` | 同名字段 | 存在，但 discharge 值错误 |
| `raw_concept_code` | `source_concept_id` | 语义等价，可接受命名 |
| `raw_concept_term` | `source_label` | 语义等价，可接受命名 |
| `parsed_value` | `value_numeric`、`value_text`、`value_structured_json` | 类型拆分更适合 Parquet，可接受 |
| `quality_flags` | 同名 `list<string>` | 存在，但值域未规范化 |
| `cleaning_status` | 无 | 阻断缺口 |

`normalization_status` 不能替代 `cleaning_status`：前者在 cleaned 文件中为空，表示尚未归一化；后者应明确表达该源行/事件是否通过清洗。

## 事件化结果

| 源表 | accepted 源行 | 事件数 | 实际 `event_kind` |
|---|---:|---:|---|
| `ed.triage` | 35 | 259 | `symptom_reported` 35；`vital_measured` 190；`triage_acuity_recorded` 34 |
| `ed.vitalsign` | 160 | 820 | `vital_measured` 820 |
| `hosp.labevents` | 21,225 | 21,225 | `laboratory_resulted` |
| `hosp.microbiologyevents` | 379 | 379 | `microbiology_resulted` |
| `hosp.poe_timeline` | 12,773 | 12,773 | `laboratory_ordered` 2,277；`imaging_ordered` 415；`clinical_ordered` 10,081 |
| `hosp.prescriptions` | 5,183 | 5,183 | `medication_ordered` |
| `hosp.pharmacy` | 4,349 | 4,349 | `medication_order_status_recorded` |
| `hosp.emar` | 11,343 | 11,343 | administered 7,677；not administered 1,613；documented 2,053 |
| `hosp.services` | 109 | 109 | `service_changed` |
| `hosp.transfers` | 389 | 389 | `patient_transferred` |
| `hosp.procedures_icd` | 225 | 225 | `procedure_recorded_post_hoc` |
| `icu.procedureevents` | 348 | 348 | `procedure_performed` |
| `note.radiology` | 307 | 307 | `imaging_reported` |
| `note.discharge` | 68 | 68 | `document_recorded` |

逐源行复算事件拆分数没有发现丢失或凭空增加：triage/vitalsign 按实际非空主诉、生命体征、血压和 acuity 拆分，其余 accepted 源行各生成一条事件。检验事件的编码、解码标签、数值、文本值、单位和时间均与源行一致；Note 全文没有被复制进事件表，当前仅保存文档元数据。

## 可追溯性

### 通过项

- 57,777/57,777 条事件的 `raw_row_ref` 格式、文件名、JSONL 行号、模块、表名和数组下标都可解析；
- 57,777/57,777 条事件的 `subject_id/hadm_id` 与 admission 及源行一致；
- 57,777/57,777 条事件的 `source_row_id` 可从对应源行稳定复算；
- `event_id` 57,777 个，无空值、无重复；
- 251/251 条 rejected 都能回到 `hosp.pharmacy` 的空 `medication` 源行，reason code 为 `PHARMACY_MEDICATION_MISSING`；
- accepted 与 rejected 源行集合不重叠、不遗漏。

### 阻断：处方下单时间缺少跨表来源

`transform_prescription` 的 `event_time/available_time` 不是来自 prescription 源行，而是通过 `poe_id` 连接 `hosp.poe.ordertime`。5,183 条处方中：

- 5,169 条成功取得 order time；
- 14 条取不到，保持空并标记 `ORDER_TIME_UNRESOLVED`；
- 5,169 条有时间的事件全部 `supporting_source_row_ids=[]`。

因此主 `raw_row_ref` 只能定位到 prescription 行，无法证明时间来自哪一条 POE 行。这违反“派生字段必须能回到产生该字段的源行”，也使单条事件审计无法独立复现时间。

根修复：把用于连接的 `hosp.poe` 行作为 enrichment source 建立稳定 `source_row_id` 和 `raw_row_ref`；在处方事件中同时写入 `supporting_source_row_ids` 与可直接解析的 `supporting_raw_row_refs`。验证器必须要求：凡字段来自跨表连接，至少有一个对应的支撑来源，且支撑来源可回查。不能仅保留 `poe_id` 文本，也不能用 prescription 自身 `starttime` 冒充 order time。

## 时间语义

全量复算后，除 discharge phase 外，时间来源映射均与既定规则一致：

| 来源 | 核验结果 |
|---|---|
| `labevents` | `event_time=charttime`；`available_time=recorded_time=storetime`；104 条缺 storetime，保持空并标志 |
| `radiology` | `event_time=charttime`；`available_time=recorded_time=storetime`；307 条均有时间 |
| `poe_timeline` | `event_time=available_time=event_time`；与 raw POE ordertime 的管线交叉检查计数为 12,773 |
| `prescriptions` | 5,169 条从 POE 取得 ordertime；14 条保持空，未拿 starttime 填补；但跨表来源缺失 |
| `ed.triage` | 259 条事件三个时间均空，`time_resolution_status=unresolved` |
| `ed.vitalsign` | 820 条只有 event_time，available/recorded 均空，`partially_resolved` |
| `transfers` | 389 条只有 intime 作为 event_time，available/recorded 均空 |
| `procedures_icd` | 225 条 `post_hoc`，只有 chartdate 作为 event_time |
| ICU procedure | 348 条使用 starttime/storetime；105 条 available_time 因完成时间晚于 storetime 而取 endtime，并显式标志 |
| eMAR | 266 条 storetime 早于 charttime，原值保留并标记 `AVAILABLE_BEFORE_EVENT_TIME` |

### 阻断：出院小结 evidence phase 错误

68/68 条 discharge 事件当前为 `evidence_phase=administrative_end`。项目字段字典和清洗设计把 `note.discharge.*` 明确定义为 `post_hoc`，而 `administrative_end` 用于 dischtime、死亡、出院去向等结局字段。现有决策快照规则主要拒绝 `post_hoc`；使用错误类别会形成后续泄漏风险。

根修复：`transform_discharge_note` 必须输出 `evidence_phase=post_hoc`。如果仍需表达“出院文档”角色，应增加独立的文档类别字段，不能占用证据阶段。测试需断言 discharge 无论 charttime/storetime 早晚都为 `post_hoc`。

## 清洗对账

| 源表 | 输入源行 | accepted 源行 | rejected 源行 | 是否平账 |
|---|---:|---:|---:|---|
| `ed.triage` | 35 | 35 | 0 | 是 |
| `ed.vitalsign` | 160 | 160 | 0 | 是 |
| `hosp.labevents` | 21,225 | 21,225 | 0 | 是 |
| `hosp.microbiologyevents` | 379 | 379 | 0 | 是 |
| `hosp.poe_timeline` | 12,773 | 12,773 | 0 | 是 |
| `hosp.prescriptions` | 5,183 | 5,183 | 0 | 是 |
| `hosp.pharmacy` | 4,600 | 4,349 | 251 | 是 |
| `hosp.emar` | 11,343 | 11,343 | 0 | 是 |
| `hosp.services` | 109 | 109 | 0 | 是 |
| `hosp.transfers` | 389 | 389 | 0 | 是 |
| `hosp.procedures_icd` | 225 | 225 | 0 | 是 |
| `icu.procedureevents` | 348 | 348 | 0 | 是 |
| `note.radiology` | 307 | 307 | 0 | 是 |
| `note.discharge` | 68 | 68 | 0 | 是 |
| **总计** | **57,144** | **56,893** | **251** | **是** |

这里的 accepted 数按每张表的唯一 `source_row_id` 计数，不按事件行数计数。

## 其他结构缺陷

### `quality_flags` 大小写碰撞

3,248 条类别级 POE 事件同时包含：

- `category_only_no_specific_order_content`；
- `CATEGORY_ONLY_NO_SPECIFIC_ORDER_CONTENT`。

根因是转换器保留上游小写 flag 后，又以大写形式追加同一语义；当前去重只区分大小写。用户影响是质量统计双计数、筛选结果不一致，并使 reason code 失去稳定性。

根修复：在事件边界对 quality flag 做冻结枚举映射，只输出一种规范形式；去重和 schema 校验都应按规范化后的 code 执行。不得通过报表端合并两个值掩盖源数据缺陷。

### 缺少 `cleaning_status`

当前通过“位于 cleaned 文件还是 rejected 文件”隐式表达状态，单条事件本身没有 `cleaning_status`。这不满足本次字段契约，也不利于跨文件合并后的审计。

根修复：在 cleaned schema 中增加非空枚举 `cleaning_status=accepted`；rejected schema 增加 `cleaning_status=rejected`。`normalization_status` 继续只表达归一化状态，不能复用。

## Python 与 NER/LLM 分流

| 数据 | 下一步处理 | 为什么 | 对用户的影响 |
|---|---|---|---|
| vitals、lab、microbiology、POE、prescription、pharmacy、eMAR、services、transfers、ICD procedure、ICU procedure | Python 确定性规则 | 具有原生代码、固定字段或稳定连接键 | 可复现、可对账，不引入模型猜测 |
| 已解码的 lab/item/ICD 概念 | 直接进入确定性映射 | 当前来源代码与官方字典标签已存在 | 不再交给 LLM 重复判断 |
| 35 条 chief complaint | Python 词典/规则优先，未解析短语再入人工/NER 队列 | 文本短、34 个唯一值，不应把整表送给模型 | 降低成本并保留原文 |
| 307 份 radiology 文本 | 文档分节后进入专用 NER | 事件表当前只有元数据，全文仍在 Note 源行 | NER 必须保留 note/span/时间引用 |
| 68 份 discharge 文本 | 文档分节后进入专用 NER，但所有结果继承 `post_hoc` | 全文 68/68 非空，属于后验文档 | 不得进入前瞻性决策快照 |
| 时间或来源无法可靠确定的事件 | 规则修正或 review/rejected 队列 | 不能用默认时间、相似文本或 LLM 猜来源 | 防止时间泄漏和错误连接 |

本样本共有 307 份 radiology 文本、68 份 discharge 文本和 35 条 chief complaint。NER 不应直接读取整张 `cleaned_events.parquet`；Note 应先建立文档与章节层。任何外部模型调用仍需单独授权和合规确认。

## 修正后的生成顺序

当前先修规则，不生成新的归一化结果：

1. 修改 discharge phase、跨表 lineage、quality flag 规范化和 `cleaning_status` schema；
2. 从同一 100 例输入重新生成 `cleaned_events.parquet`、`cleaning_rejected.parquet`、`encounter_manifest.parquet`、`source_reconciliation.json`、`run_manifest.json`；
3. 重新运行本验收，要求 4 类阻断计数全部为 0；
4. 验收通过后重新生成 `term_inventory.parquet`；
5. 结构化术语生成确定性 `normalization_mappings.parquet`、`normalized_events.parquet` 和 `normalization_review_queue.parquet`；
6. Note 另行生成 `note_index.parquet`、`note_sections.parquet` 和筛选后的 `text_ner_candidates.parquet`；NER 后再生成 `entity_mentions.parquet`、文本来源的 `clinical_events.parquet` 与 `relations.parquet`。

现有归一化文件不应继续使用。修复时应从转换规则重新生成，不通过修改验收阈值、在报表端合并 flag 或给缺失来源填默认值来绕过。

## 复验门禁

只有同时满足以下条件，才可判定“可以开始归一化”：

- `event_id` 全局非空且唯一；
- 每张源表 `input source rows = accepted source rows + rejected source rows`；
- 每条事件及每个跨表派生字段都能回到对应源行；
- 处方非空 order time 均有 POE 支撑来源；
- discharge 全部为 `post_hoc`；
- quality flag 仅使用冻结枚举，不存在大小写或语义重复；
- cleaned/rejected 均有明确 `cleaning_status`；
- 缺失时间保持空并有 `time_resolution_status` 或稳定 quality flag；
- 重新生成的 manifest 哈希与全部输出一致；
- 本审计结果 `can_start_normalization=true`。
