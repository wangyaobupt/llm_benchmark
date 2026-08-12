# 临床事件化与确定性归一化流水线

本模块把 admission 级嵌套 JSONL 转换为一行一个临床事件的 Parquet。它不改写输入文件，也不把整次住院重新封装成另一个巨大 JSON 对象。

## 两阶段合同

### 第一阶段：结构化事件化

固定处理以下来源：

- `ed.triage`、`ed.vitalsign`
- `hosp.labevents`、`hosp.microbiologyevents`
- `hosp.poe_timeline`、`hosp.prescriptions`、`hosp.pharmacy`、`hosp.emar`
- `hosp.services`、`hosp.transfers`、`hosp.procedures_icd`
- `icu.procedureevents`
- `note.radiology`、`note.discharge` 的文档元数据

输出：

- `cleaned_events.parquet`：通过结构和语义门禁的原始概念事件；归一化字段保持空值。
- `cleaning_rejected.parquet`：已知数据问题及稳定 reason code。
- `term_inventory.parquet`：按实体类型、原始编码、原始术语和单位汇总的术语清单。
- `encounter_manifest.parquet`：每次住院的源行、事件和拒绝数。
- `source_reconciliation.json`：逐表验证 `input_rows = accepted_source_rows + rejected_source_rows`。
- `run_manifest.json`：输入及输出 SHA-256、事件计数和确定性 run ID。

`hosp.poe_timeline` 是本阶段唯一的 POE 事件输入。程序同时读取原始 `hosp.poe` 做 `poe_id`、动作和时间交叉验证，但不会从 raw POE 再生成第二批事实。

### 第二阶段：确定性归一化

第二阶段只读取第一阶段的 `cleaned_events.parquet` 与 `term_inventory.parquet`，使用冻结规则处理：

- `d_labitems`、ICD 和 ICU `d_items` 已解码编码；
- POE 解析结果中的原始类别和 subtype；
- NDC、GSN 等源药物编码；
- 本地审核同义词表；
- 冻结单位别名表。

输出：

- `normalization_mappings.parquet`：每个术语和单位使用的映射、状态、规则和版本。
- `normalized_events.parquet`：保留全部原始字段，同时增加标准概念、标准值和标准单位。
- `normalization_review_queue.parquet`：术语或单位 unresolved 的审核队列。
- `normalization_manifest.json`：输入输出哈希、映射版本和状态计数。

运行期间不会调用 LLM，也不会自动创造同义词。每个事件的 `normalization_status` 必须是 `mapped`、`unresolved` 或 `not_applicable`。

## 运行命令

一次运行两阶段：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline run `
  data\validation\mimic-admission-raw-coronary-sample-100-poe-timeline-decoded.jsonl `
  --output-dir data\derived\event_pipeline_sample_100
```

也可以分别执行：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline clean INPUT.jsonl `
  --output-dir OUTPUT\cleaning

.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline normalize `
  OUTPUT\cleaning\cleaned_events.parquet `
  OUTPUT\cleaning\term_inventory.parquet `
  --output-dir OUTPUT\normalization
```

输出目录已存在时程序拒绝覆盖。每个阶段先写同目录临时文件；组合命令也只在两个阶段全部通过后一次发布输出根目录。
读取批大小可以调整，但 Parquet 固定按 5000 行写 row group；因此批大小不会改变输出字节和 manifest 哈希。

## 逐项查看清洗结果

清洗目录可通过本机只读浏览器分页查看，不需要 Excel，也不会改写 Parquet：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline.viewer `
  data\derived\event_pipeline_sample_100\cleaning
```

程序只监听 `127.0.0.1:8765` 并自动打开浏览器。页面可在四份 Parquet 间切换，按 JSONL 行号、患者、住院、事件类型、源表或拒绝原因筛选；点击任一行可检查全部字段，并由 `raw_row_ref` 回读原始 JSONL 数组元素。若源文件不在默认的 `data\validation` 位置，使用 `--source-jsonl PATH` 指定。运行前只验证文件而不启动服务时使用 `--check`。

## 时间政策

- ED triage 没有原生时间：三个时间均保留 `null`，`time_resolution_status=unresolved`。
- ED vitals 只有 `charttime`：只填写 `event_time`，不猜 `available_time`。
- 检验：`event_time=charttime`，`available_time=recorded_time=storetime`；缺失 `storetime` 时明确标志。
- POE：`event_time=available_time=event_time`，保留 lifecycle action。
- 处方：只通过原生 `poe_id` 获取下单时间；连接失败时不拿 `starttime`冒充下单时间。
- eMAR：`event_time=charttime`，`available_time=recorded_time=storetime`；允许提前记录的未给药/计划事件并加质量标志。
- ICU procedure：`event_time=starttime`，`recorded_time=storetime`，`available_time=max(endtime, storetime)`，防止“已执行”在完成前暴露。
- `procedures_icd` 和出院小结分别标记 `post_hoc`、`administrative_end`。

## 事件和来源身份

- `source_row_id` 优先由原生主键或复合键生成；无稳定键时使用规范化整行哈希。
- `event_id` 由 `source_row_id + event component` 生成，不依赖 JSONL 行号或数组位置。
- `raw_row_ref` 保留文件名、JSONL 行号、模块、表名和数组下标，供来源门禁回读。
- 一条复合源行可以生成多条原子事件，例如 triage 一行可生成主诉、心率和血压事件；逐表对账按源行而不是事件数计算。

类别级 POE 保持 `concept_id=null`、`content_specificity=category_only`、`normalization_status=unresolved`，不能成为具体检查答案。
