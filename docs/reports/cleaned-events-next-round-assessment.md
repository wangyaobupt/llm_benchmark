# Cleaned events 改善完成与验收报告

## 结论

`data/derived/event_pipeline_sample_100/cleaning/` 已按新源表、药物连接和时间契约重新生成，并通过独立验收。当前100例清洗层达到“可以开始重新执行结构化归一化”的标准；旧 normalization 产物不匹配新 cleaned SHA-256，不能继续使用。

本轮没有运行结构化归一化、NER或外部模型。

## 正式产物

| 项目 | 当前值 |
|---|---:|
| 住院记录 | 100 |
| 事实源 | 21张 |
| support源 | 6张 |
| context源 | 6张 |
| 输入事实源行 | 65,811 |
| accepted源行 | 65,768 |
| rejected源行 | 43 |
| 事件 | 66,652 |
| term inventory | 3,895 |
| cleaned Parquet大小 | 5,851,276 bytes |
| Parquet row groups | 14 |
| cleaned SHA-256 | `bda93a98cf50f8de8961d7c6883e2e401f0c38618c83c08d7074fef5072997bb` |

清洗契约为：

- 输出schema：`mimic_cleaned_events/1.2.0`
- 清洗逻辑：`1.3.0`
- source catalog：`1.1.0`
- source catalog SHA-256：`037f3265a9ba3c13c145dd8e47ca820e7f0bb0854ce87b5d1307dec6d819b57e`

## 本轮完成的修复

### 1. 封闭式覆盖33张输入表

`SOURCE_CATALOG` 对全部33张表逐一指定唯一角色、事实归属、身份策略、时间策略、evidence phase和纳入理由：21张表生成事实，6张表只提供support，6张表只提供context。`EVENT_SOURCE_REGISTRY` 只包含21张事实拥有者；出现未登记输入表时流水线直接失败。

本轮新增进入事件层的源表与事件数：

| 源表 | event_kind | 事件数 |
|---|---|---:|
| `hosp.diagnoses_icd` | `condition_recorded_post_hoc` | 1,727 |
| `ed.diagnosis` | `condition_recorded_post_hoc` | 80 |
| `hosp.hcpcsevents` | `procedure_recorded_post_hoc` | 33 |
| `ed.medrecon` | `medication_reconciled` | 521 |
| `ed.pyxis` | `medication_dispensed` | 143 |
| `icu.inputevents` | `input_administered` | 4,352 |
| `icu.outputevents` | `output_measured` | 1,811 |

### 2. 修复药物原生键连接

- pharmacy先按 `pharmacy_id` 连接prescriptions，再决定是否接受。
- 原本因药名缺失而被拒绝的251行中，208行得到唯一药名并进入accepted。
- 剩余23行多候选，以 `PHARMACY_MEDICATION_AMBIGUOUS` 拒绝；20行无候选，以 `PHARMACY_MEDICATION_UNRESOLVED` 拒绝。
- eMAR使用 `pharmacy_id`、`poe_id`/`poe_seq` 建立到pharmacy、prescriptions、POE timeline和eMAR detail的supporting lineage。
- 288条eMAR事件的缺失药名通过唯一原生键连接确定性补全，没有调用LLM。

### 3. 统一全事件时间下界

所有事件同时保留源端 `source_available_time` 和泄漏安全的有效 `available_time`。当源端可用时间早于事件发生时间时，保留原始时间并写入原因与质量标志，再将有效可用时间提高到事件发生时间；ICU区间事件还应用完成时间下界。

| 时间处理 | 事件数 |
|---|---:|
| 发现源端 `available < event` | 791 |
| 有效时间按 `event_time` 提高 | 525 |
| 有效时间按完成时间提高 | 3,010 |
| 有效 `available_time < event_time` | 0 |
| 可用时间未知并明确标志 | 4,317 |

每条事件均带 `time_policy_id`、`time_resolution_status`、`time_precision` 和 `time_resolution_reasons`。出院小结继续固定为 `post_hoc`。

## 独立验收结果

验收脚本不调用转换器、归一化代码或外部模型，直接从源JSONL复算身份、时间和可拒绝原因。

| 检查项 | 结果 |
|---|---|
| event_id非空且全局唯一 | 通过 |
| 66,652条accepted事件逐条回查 | 通过 |
| 43条rejected记录逐条回查并复算拒绝原因 | 通过 |
| 患者、住院、source_row_id、raw_row_ref | 通过 |
| supporting lineage身份与住院边界 | 通过 |
| 21张事实源 `input = accepted + rejected` | 全部通过 |
| 一对多事件数量 | 通过 |
| event_kind与evidence phase | 通过 |
| 四个时间值字段、时间状态、精度、原因和标志 | 通过 |
| Parquet字段类型和schema元数据 | 通过 |
| manifest版本、计数和文件哈希 | 通过 |
| 去除解码字段和POE timeline后的100行上游原文等价 | 100 / 100 |
| 阻断问题 | 0 |

审计结论：`can_start_normalization = true`。

完整机器可读证据见 `docs/reports/cleaned-events-acceptance-audit.json`。

## 对旧正确事件的回归核查

以旧 normalization 中57,777条事件作为只读历史快照，与新 cleaned events按 `event_id` 全量比较：

- 旧57,777个事件全部仍存在，缺失数为0；
- `source_row_id`、患者、住院、`raw_row_ref`、`event_kind`、`event_time`、`recorded_time`、数值和单位均无非预期变化；
- 新增8,875条事件：8,667条来自新增事实源，208条来自pharmacy确定性恢复；
- 其余差异限定在本轮明确修改的字段：药物supporting lineage、药物连接结构、288条eMAR药名补全、267条有效可用时间修正、68条出院小结evidence phase修正及新增时间质量标志。

因此，本轮没有通过删除或改写旧事实来换取新覆盖。

## 下一步门禁

旧 `normalization/normalization_manifest.json` 记录的 cleaned SHA-256 为 `edf5296f5f73f3d50c628d7277bff80790b992b5bc7a99171cafbdf6e1a33a5a`，与当前 `bda93a98...` 不匹配，且旧事件数为57,777。因此旧归一化结果已失效。

下一项任务应重新执行确定性结构化归一化，并要求新的 normalization manifest：

1. 输入 cleaned SHA-256 等于 `bda93a98cf50f8de8961d7c6883e2e401f0c38618c83c08d7074fef5072997bb`；
2. 输入事件数等于66,652；
3. 使用本轮重新生成的3,895行 `term_inventory.parquet`；
4. 不把 `post_hoc` 事件用于前瞻决策快照；
5. 归一化完成并审计后，才筛选ED主诉和影像报告进入首批NER。
