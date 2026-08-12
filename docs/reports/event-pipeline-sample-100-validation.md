# 100 例临床事件化与确定性归一化验收报告

## 验收结论

针对 `data/validation/mimic-admission-raw-coronary-sample-100-poe-timeline-decoded.jsonl` 的两阶段流水线已通过本任务验收。正式产物使用 Parquet；输入 JSONL 未被修改，源文件 SHA-256 与运行 manifest 一致。

本阶段只统计注册表中明确纳入的 14 类来源，不把 admission 中其他表纳入分母。共读取 57,144 条目标源行，其中 56,893 条 accepted、251 条 rejected，满足每张表及总计：

```text
input rows = accepted source rows + rejected source rows
57,144 = 56,893 + 251
```

一条 accepted 源行可以生成多条原子事件，因此事件数 57,777 不要求等于 accepted 源行数。典型情况是 `ed.triage` 一行拆出主诉、多个生命体征和分诊等级。

## 正式输出

输出根目录：`data/derived/event_pipeline_sample_100/`。该目录受 `.gitignore` 的 `data/` 规则保护，不进入 Git 仓库。

### 第一阶段

| 文件 | 行数 | 字节数 | 用途 |
|---|---:|---:|---|
| `cleaning/cleaned_events.parquet` | 57,777 | 4,065,718 | 未归一化的结构化事件 |
| `cleaning/cleaning_rejected.parquet` | 251 | 8,922 | 已知数据拒绝及 reason code |
| `cleaning/term_inventory.parquet` | 2,495 | 81,302 | 原始术语和单位清单 |
| `cleaning/encounter_manifest.parquet` | 100 | 4,788 | 住院级计数与行号 |
| `cleaning/source_reconciliation.json` | — | — | 逐表源行对账 |
| `cleaning/run_manifest.json` | — | — | 输入输出哈希与 run ID |

第一阶段 run ID：`b2a8cc5b8072244adce04387`。

251 条 rejected 全部来自 `hosp.pharmacy` 的空 `medication`，reason code 为 `PHARMACY_MEDICATION_MISSING`。这些源行没有被静默删除，仍保留稳定 `source_row_id`、`raw_row_ref`、住院标识和错误原因。

### 第二阶段

| 文件 | 行数 | 字节数 | 用途 |
|---|---:|---:|---|
| `normalization/normalized_events.parquet` | 57,777 | 4,329,758 | 确定性归一化事件 |
| `normalization/normalization_mappings.parquet` | 2,495 | 75,059 | 原始术语/单位到标准值的冻结映射 |
| `normalization/normalization_review_queue.parquet` | 1,067 | 38,312 | 术语或单位待审核项 |
| `normalization/normalization_manifest.json` | — | — | 映射版本、状态和输出哈希 |

第二阶段 run ID：`7487052fd7161654cccd597e`，映射版本为 `event-terminology/1.0.0`。

术语状态覆盖全部 57,777 条事件：

- `mapped`：28,735
- `unresolved`：29,042
- `not_applicable`：0

单位状态覆盖全部事件：

- `mapped`：14,538
- `unresolved`：5,282
- `not_applicable`：37,957

`unresolved` 是显式结果，不代表运行失败。当前冻结映射只接受源编码、已有字典解码和本地审核映射；流水线不调用 LLM，也不根据相似字符串创造映射。

## 门禁结果

| 门禁 | 结果 |
|---|---|
| 输入源文件 SHA-256 与 manifest 一致 | 通过 |
| 57,777 个 cleaned `event_id` 唯一 | 通过 |
| 57,777 个 normalized `event_id` 唯一 | 通过 |
| 两阶段事件 ID 和顺序保持一致 | 通过 |
| 原始字段从 cleaned 到 normalized 完全不变 | 通过 |
| 每条事件包含可解析的 `raw_row_ref` | 通过 |
| 每张表 `input = accepted + rejected` | 通过 |
| 每个术语状态属于 mapped/unresolved/not_applicable | 通过 |
| 每个单位状态属于 mapped/unresolved/not_applicable | 通过 |
| 类别级 POE 获得具体 `concept_id` 的违规数 | 0 |
| 5000 与 777 读取批大小的两阶段文件 SHA-256 | 完全一致 |

时间字段缺失或语义不完整时没有填默认值。主要显式非完整时间来自：`ed.vitalsign` 820 条、`hosp.transfers` 389 条、`ed.triage` 259 条、`hosp.procedures_icd` 225 条、`hosp.labevents` 104 条、`hosp.prescriptions` 14 条、`hosp.microbiologyevents` 2 条。

ICU `procedureevents` 使用 `event_time=starttime`、`recorded_time=storetime`、`available_time=max(endtime, storetime)`；这是防止 `procedure_performed` 在完成前暴露的固定政策，原始时间均保留。eMAR 允许系统在计划事件时间前记录未给药，并以质量标志表达，不把合法业务时序拒绝掉。

## 第 35 条住院核对

第 35 条真实样例仅用于验收，不作为全局模板。检查结果：

- `Chest pain` 生成 1 条 `symptom_reported`，映射为 `symptom:chest_pain`。
- `General Xray` 生成 1 条 `imaging_ordered`，映射为通用 `investigation:general_xray`；没有推断为 Chest X-ray。
- `Hemoglobin 14.2 g/dL` 生成 1 条 `laboratory_resulted`，概念为 `lab:51222`，`event_time=2119-11-13T17:30:00`，`available_time=2119-11-13T17:59:00`。
- radiology 只生成文档元数据事件，没有从全文抽取“Normal chest radiograph”。
- discharge 只生成文档元数据事件，标记为 `administrative_end`。

## 测试结果

与当前调用链直接相关的 27 项测试全部通过：

```powershell
.\.venv\Scripts\python.exe -m unittest -v `
  tests.test_clean_clinical_archive `
  tests.test_poe_timeline `
  tests.test_event_pipeline
```

完整项目测试共发现 100 项，其中 98 项通过、2 项既有测试失败：

1. `test_cleaning.DeepSeekClientTests.test_retries_invalid_response`：当前环境启用了 SOCKS 代理，但既有环境缺少 `socksio`。
2. `test_standardization`：既有导入 `rwd_pipeline.standardization.common` 指向不存在的模块。

这两项不经过 `data_pipeline.event_pipeline`，本任务没有安装无关代理依赖或补造旧模块来掩盖失败。
