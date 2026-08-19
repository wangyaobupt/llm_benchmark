# event_aggregation：把已验收事件与完整源记录无损重连的聚合站

本模块读取上游 event_pipeline 产出的 `normalized_events.parquet` 与其 manifest 声明的临床可读、原始两份 admission JSONL，产出三份互相以 `source_record_id` 连接的 Parquet（处理后事件、去重源记录、可审计事件）加两份 JSON 报告，全程 fail-closed、原子发布。本模块**不做 NER**，也**不修改任何上游清洗/标准化结果字段**（只追加列，并逐批复核原列逐值不变）。

## 1. 在流水线中的位置（完成什么事情）

```text
MIMIC-IV 原始 CSV.GZ
        │
        ▼
┌────────────────────────────┐   admission 原始 JSONL（raw 行，raw_record）
│ mimic_raw_archive          │   例：data\test_1000_0812\<raw>.jsonl
└──────────┬─────────────────┘
           │ 清洗 / 临床可读化
           ▼
┌────────────────────────────┐   临床可读 JSONL（含解码字段、note 正文、
│ clean_clinical_archive     │   hosp comments 等自由文本）
│                            │   例：data\test_1000_0812\<source>.jsonl
└──────────┬─────────────────┘
           │ event_pipeline（事件化 cleaning + 确定性归一化）
           ▼
┌──────────────────────────────────────────────┐
│ <批次目录>\event_pipeline_output              │
│   ├─ workflow_manifest.json                  │  ← 验收位 / 输入哈希 / 计数
│   └─ normalization\normalized_events.parquet │  ← 只保留事件结构与文档元数据，
└──────────┬───────────────────────────────────┘    note 正文、hosp comments 被丢弃
           │  ★ 本模块 event_aggregation（无损补回）
           ▼
┌──────────────────────────────────────────────┐
│ event_pipeline_output\aggregation\           │  （临时目录构建，os.replace 原子发布）
│   ├─ processed_events.parquet                │  事件 + 5 类 source_text（轻量分析层）
│   ├─ raw_source_records.parquet              │  每个源行恰好一行（去重存储层）
│   ├─ traceable_events.parquet                │  事件 + 内嵌源/原始行（审计层）
│   ├─ quality_report.json                     │  不可变性 / 计数对账报告
│   └─ aggregation_manifest.json               │  输入哈希、输出哈希、行数、字节数
└──────────┬───────────────────────────────────┘
           │ 逐字符原文就绪（source_text 不做空白折叠/改写，字符偏移可被 NER 复用）
           ▼
     NER / phenotype …
```

**为什么需要这一步**：event_pipeline 的事件化只把文档级元数据带入事件（note 正文、`hosp.labevents.comments`、`hosp.microbiologyevents.comments`、`ed.triage.chiefcomplaint` 等自由文本在事件里不存在）。下游要做文本挖掘/NER 时，必须能把每条事件回溯到**完整源文本**乃至**完整源行**，且不能破坏归一化结果。本模块用 `raw_row_ref`（事件上由上游写入的行级指针）重新打开两份 JSONL，把文本与整行记录补回，同时用多重哈希与计数校验保证"补回过程零损失、零改动"。

## 2. 目录结构与职责

| 文件 | 职责 | 关键函数/类 |
|---|---|---|
| `__init__.py` | 包入口，导出公共 API | `AggregationError`、`build_event_aggregation` |
| `__main__.py` | CLI 入口（`python -m data_pipeline.event_aggregation`），argparse 解析并打印 manifest JSON | `_parser()`、`main()` |
| `pipeline.py` | 全部实现：输入发现与哈希校验、源行抽取、事件富集、不可变性校验、质量报告、manifest、原子发布 | `build_event_aggregation`、`_resolve_inputs`、`_extract_source_records`、`_append_event_outputs`、`_paired_admissions`、`_AdmissionCursor`、`_BufferedWriter`、`_assert_event_columns_unchanged` 等 |
| `README.md` | 本文档 | — |

`pipeline.py` 顶部的常量即是本模块的"契约骨架"：`RAW_REF_RE`（行级指针语法）、`TEXT_FIELDS`（五类自由文本白名单）、`REQUIRED_EVENT_COLUMNS`（对上游事件 Parquet 的最小列要求）、`SOURCE_RECORD_SCHEMA` / `PROCESSED_EXTRA_FIELDS` / `TRACEABLE_EXTRA_FIELDS`（三份输出 schema）以及四个 schema 版本号（`event-aggregation/1.0.0` 等）。表角色与来源（`role`/`origin`）复用 event_pipeline 的封闭世界目录 `SOURCE_BY_PATH`（见 `data_pipeline/event_pipeline/event_cleaning/source_catalog.py`）。

## 3. 工作原理深度解析

### 3.1 输入发现与哈希校验

- **目的**：只消费"已验收且与磁盘一致"的上游产物；任何漂移立即失败。
- **输入**：批次目录（CLI 位置参数，如 `data\test_1000_0812`）。
- **步骤**（`pipeline.py: _resolve_inputs`）：
  1. 定位 `INPUT/event_pipeline_output/workflow_manifest.json` 与 `INPUT/event_pipeline_output/normalization/normalized_events.parquet`，任一缺失 → `EVENT_OUTPUT_INCOMPLETE`。（注意：本模块读的是 **workflow_manifest.json**，不读取 normalization_manifest.json。）
  2. 校验 `workflow.acceptance` 中 `cleaning`、`normalization`、`reproducible` 三项全部为真，否则 → `EVENT_OUTPUT_NOT_ACCEPTED`（未验收批次拒绝聚合）。
  3. 从 `workflow.inputs` 读取 `source_jsonl`（临床可读）与 `raw_source_jsonl`（原始）两个文件名（缺失 → `WORKFLOW_SOURCE_PATH_MISSING`），相对批次目录解析；文件不存在 → `SOURCE_JSONL_NOT_FOUND`。
  4. 对三份输入现算 SHA-256（`_sha256_file`，1 MiB 分块），与 manifest 声明值逐一比对：`inputs.source_jsonl_sha256`、`inputs.raw_source_jsonl_sha256`、`stages.normalization.output_sha256["normalized_events.parquet"]`；缺失或不等 → `INPUT_HASH_MISMATCH`。
- **输出**：路径、workflow dict、实测哈希的字典，供后续阶段与 manifest 复用。

### 3.2 源 JSONL 与原始 JSONL 的逐行配对验证

- **目的**：两份 JSONL 必须"同一行 = 同一次住院"，否则一切行级回溯无效。
- **处理**（`pipeline.py: _paired_admissions`）：以 `zip_longest` 同时流式迭代两文件，行号从 1 起：
  - 一侧先耗尽 → `SOURCE_JSONL_LINE_COUNT_MISMATCH`；
  - 任一侧空行 → `SOURCE_JSONL_EMPTY_LINE`；
  - JSON 解析失败 → `SOURCE_JSONL_INVALID`；
  - 同一行的 `(subject_id, hadm_id)`（`str()` 归一）在两份文件中不一致 → `SOURCE_JSONL_IDENTITY_MISMATCH`；
  - 通过则 `yield (行号, 临床可读 admission, 原始 admission)`，供两个消费方复用（生成器，内存中每次只有一行）。
- **表级对齐**（`pipeline.py: _validate_table_pair`，在抽取源记录时逐表调用）：
  - `(module, table)` 不在 `SOURCE_BY_PATH` → `SOURCE_TABLE_NOT_REGISTERED`（封闭世界：临床可读 JSONL 里出现未注册表即失败）；
  - `spec.origin == "derived"`（如 `hosp.poe_timeline`）：原始侧该表必须为 `None`/`[]`，否则 → `DERIVED_TABLE_PRESENT_IN_RAW_SOURCE`；
  - 原生表：原始侧必须是列表（`RAW_SOURCE_TABLE_MISSING`）且**行数与临床可读侧相等**（`RAW_SOURCE_TABLE_COUNT_MISMATCH`）。

### 3.3 `raw_row_ref` 的解析定位与 `source_record_id` 的构造

- **语法**：`RAW_REF_RE` 定义为 `<文件名>#L<行号>/<模块>.<表>[<数组下标>]`，例：`clinical_readable.jsonl#L12/mimic_iv_hosp.labevents[3]`。其中文件名必须是**临床可读 JSONL 的文件名**、模块是 `mimic_iv_*` 形式、表是裸表名。
- **解析**（`pipeline.py: _raw_ref_parts`）：正则 `fullmatch` 失败 → `RAW_ROW_REF_INVALID`；文件名与实际临床可读文件名不符 → `RAW_ROW_REF_FILENAME_MISMATCH`；返回 `(line, module, table, index)` 四元组。
- **定位**（`pipeline.py: _resolve_row`）：在已加载的 admission dict 上按 `admission[module][table][index]` 导航；模块缺失 → `SOURCE_MODULE_MISSING`，表缺失 → `SOURCE_TABLE_MISSING`，下标越界 → `SOURCE_ARRAY_INDEX_OUT_OF_RANGE`，元素非对象 → `SOURCE_ROW_NOT_OBJECT`。
- **ID 构造**（`pipeline.py: _source_record_id`）：`"srec:" + SHA-256(raw_row_ref)[:24]`——对指针字符串本身做内容哈希取前 24 个十六进制字符（96 bit）。纯函数、跨运行稳定：同一批次无论跑多少次、无论谁跑，同一源行的 ID 恒定，天然支撑"多事件引用同一源行时去重嵌入"。

### 3.4 三份 Parquet 的生成

#### 3.4.1 `raw_source_records.parquet` —— 每个源行恰好一行（`pipeline.py: _extract_source_records`）

- **目的**：把临床可读 JSONL 中**所有注册表**（event / support / context 三种角色）的每个数组元素物化为唯一一行，同时保留其临床可读行与原始行，作为另两份输出的"存储层"。
- **输入**：临床可读 JSONL + 原始 JSONL（经 `_paired_admissions` 配对流）。
- **步骤**：对每个 admission：取 `subject_id`/`hadm_id`；遍历所有 `mimic_iv_` 前缀模块（模块值必须是对象，否则 `SOURCE_MODULE_NOT_OBJECT`；表值必须是数组，否则 `SOURCE_TABLE_NOT_ARRAY`）；对每张表先做 3.2 的 `_validate_table_pair` 拿到原始侧行数组（derived 表得 `None`）；再逐元素（必须是对象，否则 `SOURCE_ROW_NOT_OBJECT`）：
  - 构造 `raw_row_ref = f"{source_path.name}#L{行号}/{module}.{table}[{index}]"`；
  - 用 `_source_text`（见下）从**临床可读行**提取文本；
  - 原始行按同下标对齐（`raw_rows[index]`，derived 为 `None`）；
  - 经 `_BufferedWriter` 写出一行（字段结构见第 4 节）。
- **输出**：除 Parquet 外返回统计摘要（admissions、source_records、按表/角色/origin 的行数、有文本行数与字符数），全部进入 quality_report。
- **要点**：总行数 = 两份 JSONL 中所有注册表数组元素总数；其中 `source_role == "event"` 的行数之后要与 workflow 的 `stages.cleaning.counts.source_rows` 对账。

#### 3.4.2 `processed_events.parquet` —— 事件 + 五类 `source_text`（`pipeline.py: _append_event_outputs`）

- **目的**：给每条已归一化事件补上可全文检索/NER 的 `source_text`，但**不嵌入整行**（控制体积、避免事件表膨胀）。
- **输入**：`normalized_events.parquet`（`iter_batches` 流式读取）+ 两份 JSONL（经 `_AdmissionCursor` 单次前向扫描）。
- **步骤**（逐事件）：
  1. 打开上游 Parquet 时先校验 `REQUIRED_EVENT_COLUMNS`（event_id、subject_id、hadm_id、source_module、source_table、source_array_index、jsonl_line_number、raw_row_ref、supporting_raw_row_refs），缺列 → `NORMALIZED_EVENT_COLUMNS_MISSING`。
  2. `_raw_ref_parts(event["raw_row_ref"], source_path.name)` 解析指针，得到的 `(行号, 模块, 表, 下标)` 必须与事件自身四列（`jsonl_line_number`、`source_module`、`source_table` 去前缀、`source_array_index`）**完全一致**，否则 → `NORMALIZED_EVENT_LINEAGE_MISMATCH`（事件自述血统与指针互相矛盾）。
  3. `_AdmissionCursor.get(行号)` 取得该行两份 admission（游标只前进，见 3.5）。
  4. `_resolve_row` 在临床可读 admission 上定位源行；`_raw_counterpart`（`pipeline.py: _raw_counterpart`）在原始 admission 上按同 `(module, table, index)` 取原始行（derived 表返回 `None`；表未注册/原始行缺失/非对象分别 → `RAW_SOURCE_MODULE_MISSING` / `RAW_SOURCE_ROW_NOT_FOUND` / `RAW_SOURCE_ROW_NOT_OBJECT`）。
  5. 身份校验：源行所属 admission 的 `subject_id`/`hadm_id` 必须与事件一致（`NORMALIZED_EVENT_SUBJECT_MISMATCH` / `NORMALIZED_EVENT_ADMISSION_MISMATCH`）。
  6. `_source_text(module, table, source_row)` 生成四元组 `(field, kind, text, sha256)`：查 `TEXT_FIELDS` 白名单——
     | (module, table) | 源字段 | kind |
     |---|---|---|
     | `mimic_iv_hosp.labevents` | `comments` | `laboratory_comment` |
     | `mimic_iv_hosp.microbiologyevents` | `comments` | `microbiology_comment` |
     | `mimic_iv_ed.triage` | `chiefcomplaint` | `chief_complaint` |
     | `mimic_iv_note.radiology` | `text` | `radiology_report` |
     | `mimic_iv_note.discharge` | `text` | `discharge_summary` |

     取值仅做 `str()` 与"全空白判空"（空/纯空白 → `text=None`、`sha=None`，但 `field`/`kind` 仍写明），**不做空白折叠、不改写任何字符**——NER 的字符偏移因此与源字符一一对应。非白名单表四个值全为 `None`。
  7. `supporting_raw_row_refs` 逐个解析：必须与主指针**同一行号**（同一次住院），否则 → `SUPPORTING_SOURCE_CROSSES_ADMISSION`；并 `_resolve_row` 验证该行确实存在；最后只写入 `_source_record_id(supporting_ref)` 引用列表（`supporting_source_record_ids`）。**去重嵌入的关键**：支持行本体只存在于 `raw_source_records.parquet` 一处，事件侧仅存 ID 引用，绝不重复嵌入整行 JSON。
  8. `enriched = {**event, <7 个追加字段>}` 原样追加（原始列名、顺序、值不动）。
- **输出**：上游全部列 + `aggregation_schema_version`、`source_record_id`、`source_text_field`、`source_text_kind`、`source_text`、`source_text_sha256`、`supporting_source_record_ids`。

#### 3.4.3 `traceable_events.parquet` —— 事件内嵌完整源行（与 processed 同循环写出）

- **目的**：给审计/抽样复核提供"一行看全"的宽表。
- **做法**：与 processed 完全同构，仅再追加两列：`clinical_readable_record_json`（源行的 canonical JSON）与 `raw_record_json`（原始行 canonical JSON；derived 表为 `None`）。canonical 化由 `_canonical_json` 完成（`sort_keys=True`、紧凑分隔符、`ensure_ascii=False`），保证同对象序列化唯一。
- **代价**：该文件体积明显大于 processed（整行 × 事件数），所以分析场景用 processed、审计场景用 traceable。

### 3.5 对齐与不可变性校验（哪一步保证"什么都没变"）

- **前向游标**（`pipeline.py: _AdmissionCursor`）：包裹 `_paired_admissions`，`get(target_line)` 要求事件按 `jsonl_line_number` **非降序**到达（回退 → `NORMALIZED_EVENTS_NOT_SOURCE_ORDERED`）；源 JSONL 提前耗尽 → `NORMALIZED_EVENT_LINE_NOT_FOUND`。任意时刻内存中只缓存当前 admission 一对。这是"事件必须按源行序排列"这一上游约定的强制点。
- **计数对账**（`pipeline.py: build_event_aggregation` 主流程，全部对 workflow_manifest）：
  | 检查名 | 含义 |
  |---|---|
  | `event_count_matches_workflow` | 事件数 == `stages.normalization.counts.events` |
  | `event_admission_count_matches_workflow` | 事件覆盖的不同 `(subject_id, hadm_id)` 数 == `stages.cleaning.counts.admissions` |
  | `source_admission_count_matches_workflow` | 源 JSONL 行数 == 同上住院数 |
  | `workflow_event_source_record_count_matches` | `source_role_counts["event"]` == `stages.cleaning.counts.source_rows` |
  | `processed_event_rows_match` / `traceable_event_rows_match` | 两份事件输出物理行数（Parquet metadata）== 期望事件数 |
  | `raw_source_record_rows_match` | 源记录输出物理行数 == 抽取期统计值 |
  任一不过 → `AGGREGATION_QUALITY_CHECK_FAILED`（消息里列出失败检查名）。
- **逐值不可变复核**（`pipeline.py: _assert_event_columns_unchanged`）：对 processed 与 traceable 各执行一次——按上游 Parquet 的**原始列集合**重新流式读两份文件，`zip_longest` 逐 RecordBatch 用 Arrow `equals` 比较；批数不等或任一批不等 → `NORMALIZED_EVENT_FIELDS_CHANGED`。这证明"追加列之外，每一行每一列的值与上游逐值相同"，比 schema 对比强得多。通过后 quality_report 追加 `processed_normalized_fields_unchanged` / `traceable_normalized_fields_unchanged = True`。
- **行对齐**：见 3.2（行级 identity + 表级行数）与 3.4.2 第 2 步（指针 ↔ 事件自述血统互验）。

### 3.6 fail-closed 与原子发布（`pipeline.py: build_event_aggregation`）

- **入口护栏**：`batch_size <= 0` → `BATCH_SIZE_INVALID`；输出目录已存在 → 直接抛 `FileExistsError`（非 `AggregationError`；没有覆盖/强制模式）。
- **两阶段构建**：先 `_extract_source_records`（一遍扫源 JSONL 对），再 `_append_event_outputs`（第二遍扫，经游标）。
- **原子发布**：全部产物先写进输出目录**父目录**下的临时目录 `tempfile.mkdtemp(prefix=".aggregation-")`（同文件系统）；三份 Parquet + 两份 JSON 全部完成、全部检查通过后，`os.replace(temporary, output_directory)` 一次性改名上线。任何一步抛异常 → `_safe_remove_temporary`（`pipeline.py: _safe_remove_temporary`）：只允许删除"直接位于该父目录、且名字以 `.aggregation-` 开头"的目录，否则拒绝删除并抛 `RuntimeError`——保证清理逻辑本身不会误删用户数据。
- **结果**：磁盘上要么没有 `aggregation/`，要么是一个完整、已通过全部检查的目录；不存在半成品。

### 3.7 分批（batch）处理与内存策略

- **`_BufferedWriter`**（`pipeline.py: _BufferedWriter`）：每个输出文件一个 `pq.ParquetWriter`（zstd 压缩、`compression_level=9`、字典编码、开统计），行先累积在内存 list，达到 `batch_size`（默认 5000，行数）即 `flush()`：`pa.Table.from_pylist(rows, schema=schema)` 一次写出一个 RecordBatch（≈ 一个 row group）。异常路径直接 `writer.close()` 不 flush（临时文件反正会被整体删除）。
- **流式输入**：两份 JSONL 逐行生成器读取（`_paired_admissions`）；上游事件 Parquet 用 `ParquetFile.iter_batches(batch_size)` 分批；不可变复核同样分批（`_iter_batches`）。
- **内存上界**：常驻内存 ≈ 单个 admission 的两份 JSON + 一个批次的行 + 若干计数器/集合（distinct subject/admission/源指针集合，随批次规模线性但为短字符串）。全程无全量 load。
- **代价**：源 JSONL 对被完整读两遍；事件必须按行号有序（由上游排序保证，本模块强制校验）。

## 4. 数据契约

### 4.1 输入要求（上游必须提供）

1. `INPUT/event_pipeline_output/workflow_manifest.json`：`acceptance.{cleaning, normalization, reproducible}` 全真；`inputs.{source_jsonl, raw_source_jsonl, source_jsonl_sha256, raw_source_jsonl_sha256}` 齐全；`stages.normalization.counts.events`、`stages.normalization.output_sha256["normalized_events.parquet"]`、`stages.cleaning.counts.{admissions, source_rows}` 齐全。
2. 两份 admission JSONL：逐行 `(subject_id, hadm_id)` 一致、无空行、行数相等；每行内非 derived 表两侧行数相等；所有表已在 `SOURCE_BY_PATH` 注册；derived 表不得出现在原始侧。
3. `normalized_events.parquet`：含 `REQUIRED_EVENT_COLUMNS` 九列；事件按 `jsonl_line_number` 非降序；`raw_row_ref` 的文件名段等于临床可读 JSONL 文件名；`supporting_raw_row_refs` 不跨住院。

### 4.2 `raw_source_records.parquet`（schema 元数据 `event-source-record/1.0.0`，18 列）

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | 恒 `event-source-record/1.0.0` |
| `source_record_id` | string | `srec:` + SHA-256(raw_row_ref) 前 24 hex，全模块 join 键 |
| `subject_id` / `hadm_id` | string | 所属住院 |
| `jsonl_line_number` | int64 | admission 在两份 JSONL 中的行号（1 起） |
| `source_module` | string | 模块名，如 `mimic_iv_hosp` |
| `source_table` | string | 表路径，如 `hosp.labevents` |
| `source_table_name` | string | 裸表名，如 `labevents` |
| `source_array_index` | int64 | 行内数组下标 |
| `raw_row_ref` | string | `<source文件名>#L<行>/<模块>.<表>[<下标>]` |
| `source_role` | string | `event` / `support` / `context`（目录 spec.role） |
| `source_origin` | string | `raw` / `derived`（目录 spec.origin） |
| `source_text_field` / `source_text_kind` | string \| null | 五类白名单内必填（有值见 3.4.2 表），白名单表为 null |
| `source_text` | string \| null | 源字符原样（空白折叠＝无）；空/全空白为 null |
| `source_text_sha256` | string \| null | `source_text` 的 UTF-8 SHA-256 |
| `clinical_readable_record_json` | string | 临床可读行 canonical JSON（sort_keys、紧凑） |
| `raw_record_json` | string \| null | 原始行 canonical JSON；derived 表为 null |

### 4.3 `processed_events.parquet`（schema 元数据 `event-aggregation/1.0.0`）

= 上游 `normalized_events.parquet` 的**全部原始列（逐列、逐值不变）** + 追加 7 列：`aggregation_schema_version`（string）、`source_record_id`（string，指向 raw_source_records）、`source_text_field`、`source_text_kind`、`source_text`、`source_text_sha256`、`supporting_source_record_ids`（list\<string\>，支持行的去重 ID 引用）。

### 4.4 `traceable_events.parquet`（schema 元数据 `event-aggregation/1.0.0`）

= processed 全列 + `clinical_readable_record_json`（string）+ `raw_record_json`（string \| null）。行数与 processed、上游事件数完全相等。

### 4.5 `quality_report.json`（`event-aggregation-quality/1.0.0`）

```jsonc
{
  "schema_version": "event-aggregation-quality/1.0.0",
  "status": "passed",                      // 只在全部通过后才会写出该文件
  "checks": { /* 3.5 节 7 项对账 + 2 项不可变复核，共 9 个布尔 */ },
  "expected": { "events": 0, "admissions": 0,
                "workflow_event_source_records": 0, "all_source_records": 0 },
  "observed": {
    // 源侧统计：admissions、source_records、source_table_counts、
    //           source_role_counts、source_origin_counts、
    //           source_text_record_counts、source_text_character_counts
    // 事件侧统计：events、subjects、admissions、event_source_records、
    //           source_text_event_counts
    // 注意：两侧都有 admissions 键，事件侧值覆盖源侧（通过检查时二者相等）
  }
}
```

### 4.6 `aggregation_manifest.json`（`event-aggregation-manifest/1.0.0`）

```jsonc
{
  "schema_version": "event-aggregation-manifest/1.0.0",
  "created_at_utc": "<ISO8601>",           // 含时区 UTC
  "aggregation_schema_version": "event-aggregation/1.0.0",
  "batch_size": 5000,
  "inputs": {
    "workflow_manifest": "<绝对路径>", "source_jsonl": "<绝对路径>",
    "raw_source_jsonl": "<绝对路径>", "normalized_events": "<绝对路径>",
    "sha256": { "source_jsonl": "…", "raw_source_jsonl": "…", "normalized_events": "…" }
  },
  "text_fields": [ { "source_module": "…", "source_table": "hosp.labevents",
                     "source_text_field": "comments", "source_text_kind": "laboratory_comment" }, /* 共 5 项 */ ],
  "outputs": { "<name>.parquet": { "sha256": "…", "bytes": 0, "rows": 0 } /* 3 份 */ },
  "quality_report": "quality_report.json",
  "quality_status": "passed"
}
```

## 5. 正确性与可靠性保障（fail-closed 清单）

任何一项触发即抛 `AggregationError(reason_code, message)`（或注明者除外），临时目录被安全删除，**不发布输出目录**：

| 阶段 | reason_code | 触发条件 |
|---|---|---|
| 入口 | `BATCH_SIZE_INVALID` | `batch_size <= 0` |
| 入口 | （`FileExistsError`） | 输出目录已存在 |
| 输入发现 | `EVENT_OUTPUT_INCOMPLETE` | workflow_manifest 或 normalized_events.parquet 缺失 |
| 输入发现 | `EVENT_OUTPUT_NOT_ACCEPTED` | acceptance 三项未全真 |
| 输入发现 | `WORKFLOW_SOURCE_PATH_MISSING` / `SOURCE_JSONL_NOT_FOUND` | manifest 未声明 / 文件不存在 |
| 输入发现 | `INPUT_HASH_MISMATCH` | 三份输入任一 SHA-256 与 manifest 不符或缺失 |
| 行对齐 | `SOURCE_JSONL_LINE_COUNT_MISMATCH` / `SOURCE_JSONL_EMPTY_LINE` / `SOURCE_JSONL_INVALID` | 两文件行数不等 / 空行 / JSON 解析失败 |
| 行对齐 | `SOURCE_JSONL_IDENTITY_MISMATCH` | 同行 `(subject_id, hadm_id)` 不一致 |
| 表对齐 | `SOURCE_TABLE_NOT_REGISTERED` / `SOURCE_MODULE_NOT_OBJECT` / `SOURCE_TABLE_NOT_ARRAY` / `SOURCE_ROW_NOT_OBJECT` | 封闭世界外 / 结构非法 |
| 表对齐 | `DERIVED_TABLE_PRESENT_IN_RAW_SOURCE` / `RAW_SOURCE_TABLE_MISSING` / `RAW_SOURCE_TABLE_COUNT_MISMATCH` | derived 表出现在原始侧 / 原始侧缺表 / 行数不等 |
| 指针解析 | `RAW_ROW_REF_INVALID` / `RAW_ROW_REF_FILENAME_MISMATCH` | 语法非法 / 文件名段不符 |
| 指针定位 | `SOURCE_MODULE_MISSING` / `SOURCE_TABLE_MISSING` / `SOURCE_ARRAY_INDEX_OUT_OF_RANGE` | `_resolve_row` 导航失败 |
| 指针定位 | `RAW_SOURCE_MODULE_MISSING` / `RAW_SOURCE_ROW_NOT_FOUND` / `RAW_SOURCE_ROW_NOT_OBJECT` | 原始侧找不到对应行 |
| 事件血缘 | `NORMALIZED_EVENT_COLUMNS_MISSING` | 上游缺必需列 |
| 事件血缘 | `NORMALIZED_EVENT_LINEAGE_MISMATCH` | 指针四元组 ≠ 事件自述四列 |
| 事件血缘 | `NORMALIZED_EVENT_SUBJECT_MISMATCH` / `NORMALIZED_EVENT_ADMISSION_MISMATCH` | 事件与源行身份不符 |
| 事件血缘 | `NORMALIZED_EVENTS_NOT_SOURCE_ORDERED` / `NORMALIZED_EVENT_LINE_NOT_FOUND` | 事件行号回退 / 源行耗尽 |
| 支持行 | `SUPPORTING_SOURCE_CROSSES_ADMISSION` | 支持指针跨住院 |
| 收尾对账 | `AGGREGATION_QUALITY_CHECK_FAILED` | 3.5 节 7 项计数任一不符 |
| 收尾对账 | `NORMALIZED_EVENT_FIELDS_CHANGED` | 输出文件原始列任一批与上游不等 |
| 清理护栏 | （`RuntimeError`） | `_safe_remove_temporary` 拒绝删除非常规临时路径 |

（`SOURCE_MODULE_UNKNOWN` 为 `_table_path` 对未知模块的防御性分支，实际被封闭世界校验先行拦截。）

## 6. 使用方法

CLI（在项目根目录执行；PowerShell 反引号续行）：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_aggregation `
  data\test_1000_0812
```

显式指定输出目录与批大小：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_aggregation `
  data\test_1000_0812 `
  --output-dir data\test_1000_0812\event_pipeline_output\aggregation `
  --batch-size 5000
```

成功时 stdout 打印 `aggregation_manifest.json` 的内容（`json.dumps(..., ensure_ascii=False, indent=2)`）；失败时非零退出并给出 `reason_code: message`。

| 参数 | 类型 / 默认 | 说明（与 `__main__.py: _parser()` 对齐） |
|---|---|---|
| `input_directory`（位置参数，必填） | Path | 批次目录，须含 `event_pipeline_output` 与两份源 JSONL |
| `--output-dir` | Path，默认 `INPUT/event_pipeline_output/aggregation` | 输出目录；已存在则失败 |
| `--batch-size` | int，默认 `5000` | 读写批行数（内存上界与 row group 粒度），须 > 0 |

编程接口：`from data_pipeline.event_aggregation import build_event_aggregation, AggregationError`；`build_event_aggregation(input_dir, output_dir, *, batch_size=5000)` 返回 manifest dict。

单测（覆盖：三份产物行数与 `source_text` 取值、临床可读/原始行差异保留、quality_report 全绿、血缘失配时 `NORMALIZED_EVENT_LINEAGE_MISMATCH` 且不发布目录）：

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests.test_event_aggregation
```

## 7. 设计取舍与已知限制

- **文本白名单固定五类**：`TEXT_FIELDS` 是硬编码常量；新增文本字段需改代码（并同步上游）。表未列入则 `source_text` 为 null——完整字段并未丢失，仍可从两份 record JSON 取回。
- **`source_text` 取自临床可读行**（含上游解码/清洗后的文本），非 MIMIC 原始 CSV 值；原始语义完整保存在 `raw_record_json`。本模块对取到的字符串零改写（仅 `str()` 与空白判空），字符偏移相对**该 JSONL 源**无损。
- **ID 为截断内容哈希**：`srec:` + 96 bit，跨运行稳定、可去重；理论碰撞概率极低但非零，且同一源行改批重跑 ID 不变（ID 只由指针决定，与内容无关——内容变化靠输入哈希门禁拦截）。
- **单次前向扫描的代价**：事件必须按 `jsonl_line_number` 非降序（fail-closed 强制），换取 O(单 admission) 内存；源 JSONL 对被完整读取两遍。
- **支持行不跨住院**：`SUPPORTING_SOURCE_CROSSES_ADMISSION` 直接失败，未提供跨行支持建模。
- **输出目录存在即失败、无覆盖模式**；重跑须先删除旧 `aggregation/` 目录。
- **manifest 非逐字节可复现**：含 UTC 时间戳与绝对路径；Parquet 本身在同输入、同 `batch_size` 下确定（行组边界由批大小决定，故 manifest 记录了 `batch_size`）。
- **个别路径抛裸异常**：如 admission 顶层缺 `subject_id`/`hadm_id` 时 `_extract_source_records` 的直接下标抛 `KeyError`——仍 fail-closed（临时目录被清理），但没有稳定 reason code。
- **下游消费建议**：大规模分析用 `processed_events` + 按 `source_record_id` 关联 `raw_source_records`；逐事件人工审计用 `traceable_events`；本模块产物即 NER 输入的原文来源，但其本身不做任何实体识别。
