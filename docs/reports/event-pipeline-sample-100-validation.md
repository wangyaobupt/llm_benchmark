# 100 例临床事件流水线验收报告

## 验收结论

100 例数据的结构化事件化与确定性归一化均已通过独立验收：

```text
cleaning.can_start_normalization = true
normalization.can_publish_normalization = true
normalization.can_start_text_ner = true
blocking_issue_codes = []
```

这表示 `cleaned_events.parquet` 可以作为稳定事实层，当前 `normalized_events.parquet` 可以作为其确定性归一化下游。它不表示自由文本已经完成 NER，也不表示 MIMIC 本地编码已经全部映射到 LOINC、RxNorm、SNOMED CT 或 OMOP 标准概念。

机器可读证据：

- `docs/reports/cleaned-events-acceptance-audit.json`
- `docs/reports/normalized-events-acceptance-audit.json`

## 输入合同

| 输入 | 行数 | SHA-256 |
|---|---:|---|
| `cleaning/cleaned_events.parquet` | 66,652 | `bda93a98cf50f8de8961d7c6883e2e401f0c38618c83c08d7074fef5072997bb` |
| `cleaning/term_inventory.parquet` | 3,895 | `d88dca8d27c7530a2d98156c684eda9b51edb992aecbe6641413b45405f00f69` |

新的 normalization manifest 与上述输入哈希完全一致，旧 cleaned 版本的归一化产物已被替换。

## 清洗与事件化结果

当前清洗合同覆盖 100 例输入的全部 33 张表：21 张事实拥有者生成事件，6 张 support 表只提供原生键连接和来源证据，6 张 context 表不重复生成临床事实。

| 项目 | 结果 |
|---|---:|
| accepted 事件 | 66,652 |
| rejected 源行 | 43 |
| term inventory | 3,895 |
| `event_id` 空值或重复 | 0 |
| 有效 `available_time < event_time` | 0 |
| 无明确登记的输入表 | 0 |
| 清洗验收阻断项 | 0 |

全部 21 张事实源均满足逐表对账：

```text
input source rows = accepted source rows + rejected source rows
```

药物连接使用 `pharmacy_id`、`poe_id` 和 `poe_seq` 等原生键；没有使用 LLM 或文本相似度猜测。出院小结继续标记为 `post_hoc`。

## 确定性归一化产物

| 产物 | 行数 | SHA-256 |
|---|---:|---|
| `normalized_events.parquet` | 66,652 | `50698a7cf988c98a1b0efc27a404ad37d7f054f7c3d6c28810dfe65a49647ed4` |
| `normalization_mappings.parquet` | 3,895 | `e7be0e83ecf51abfdde7fb612d20e3a9925eb999cfe6d8b4609c1dddc704c4c5` |
| `normalization_review_queue.parquet` | 1,001 | `57b373c15bfb42588b998c937c49d2312052161e7e7f17c56c709740f2439853` |

manifest 关键字段：

```text
run_id = e15597823e4e268e1f8baf30
mapping_version = event-terminology/1.1.0
events = 66652
mapping_rows = 3895
review_queue_rows = 1001
```

### 术语归一化

| 状态/规则 | 术语数 | 事件数 | 含义 |
|---|---:|---:|---|
| `source-code` | 2,911 | 36,491 | 保留已解码或有效的源编码 |
| `reviewed-local-subtype` | 1 | 261 | 冻结的本地 subtype 映射 |
| `reviewed-synonym` | 1 | 3 | 冻结的人工审核同义词 |
| `invalid-source-code` | 29 | 639 | 无效 NDC 或多值 GSN，不冒充已映射概念 |
| `unresolved` | 953 | 29,258 | 缺少足够确定性证据，进入审核队列 |

事件层合计：36,755 条 `mapped`，29,897 条 `unresolved`。

这里的 `mapped` 表示“按冻结规则确定性保留或映射了源概念”，不是跨术语体系标准化已经完成。尤其是 MIMIC item ID、lab item ID 等仍是 MIMIC 本地概念。

### 单位归一化

| 状态 | 事件数 |
|---|---:|
| `mapped` | 25,490 |
| `not_applicable` | 40,849 |
| `unresolved` | 313 |

明确单位使用冻结别名表处理，包括 `mL`、`mg`、`sec`、`IU/L`、`mmHg`、`mmol/L` 等；`N/A` 映射为 `not_applicable`。剩余 313 条未解析单位均为 `dose`，没有凭上下文猜测其物理量。

## 本轮发现并修复的问题

1. `ndc:0` 原先会被误认为有效源编码。现在 NDC 必须是非全零的 11 位数字，否则保留原值但标记 `invalid-source-code` 和 `unresolved`。
2. 一格中包含多个 GSN 的字符串原先会被误认为单一概念。现在 GSN 必须是单个 6 位编码，否则进入审核队列。
3. 常见明确单位未进入冻结别名表，导致大量假性 unresolved。现在只扩充有确定语义的单位；含义不明确的 `dose` 仍不自动映射。

这些修复把“有字符串”与“有可用概念编码”分开，避免下游把占位值或多值列表当作一个标准概念。

## 独立验收

归一化审计脚本没有调用归一化器复述自身结果，而是独立检查：

- cleaned、inventory、normalized、mappings、review queue 的 Arrow schema；
- 66,652 个事件的数量、顺序和 `event_id`；
- 除 8 个归一化输出字段外，所有事件字段逐项不变；
- term inventory 与 mappings 一一对应；
- 映射规则、状态及事件应用结果可独立复算；
- review queue 恰好等于 unresolved 术语和单位集合；
- manifest 输入输出哈希、版本及计数一致。

允许改变的 8 个字段只有：

```text
concept_id
preferred_name
normalization_status
terminology_mapping_version
normalized_value_numeric
normalized_value_text
normalized_unit
unit_normalization_status
```

使用 batch size 5,000 和 777 分别重跑，run ID、三份 Parquet 的 SHA-256、计数和状态分布完全一致，证明结果不依赖读取批大小。

## 下一层边界

下一项任务不是对全表调用 LLM，而是生成首批文本 NER 输入清单：

1. ED chief complaint：只提取需要实体识别的原始主诉文本；
2. radiology report：按文档及章节保留来源和时间语义后进入 NER；
3. discharge note：暂不进入首批 NER，后续产物必须继承 `post_hoc`；
4. 结构化 unresolved 队列：继续走词典、原生键或人工审核，不作为 NER 文本。

任何外部模型调用仍需单独授权。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline.event_quality.audit_normalization `
  --cleaned data\derived\event_pipeline_sample_100\cleaning\cleaned_events.parquet `
  --term-inventory data\derived\event_pipeline_sample_100\cleaning\term_inventory.parquet `
  --normalized data\derived\event_pipeline_sample_100\normalization\normalized_events.parquet `
  --mappings data\derived\event_pipeline_sample_100\normalization\normalization_mappings.parquet `
  --review data\derived\event_pipeline_sample_100\normalization\normalization_review_queue.parquet `
  --manifest data\derived\event_pipeline_sample_100\normalization\normalization_manifest.json `
  --output-json docs\reports\normalized-events-acceptance-audit.json
```
