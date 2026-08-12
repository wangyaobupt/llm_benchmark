# 临床事件化与确定性归一化流水线

本模块把 admission 级嵌套 JSONL 转换为一行一个临床事件的 Parquet。它不改写输入文件，也不把整次住院重新封装成另一个巨大 JSON 对象。

## 两阶段合同

### 第一阶段：结构化事件化

事件流水线采用封闭式 `SOURCE_CATALOG`。当前合同登记33张输入表，任何未登记表都会以 `UNREGISTERED_SOURCE_TABLE` 原子终止运行，缺少必需表则以 `REQUIRED_SOURCE_TABLE_MISSING` 终止。

21张事实拥有者会生成事件：

- `ed.triage`、`ed.vitalsign`、`ed.diagnosis`、`ed.medrecon`、`ed.pyxis`
- `hosp.labevents`、`hosp.microbiologyevents`
- `hosp.poe_timeline`、`hosp.prescriptions`、`hosp.pharmacy`、`hosp.emar`
- `hosp.services`、`hosp.transfers`、`hosp.diagnoses_icd`、`hosp.procedures_icd`、`hosp.hcpcsevents`
- `icu.inputevents`、`icu.outputevents`、`icu.procedureevents`
- `note.radiology`、`note.discharge` 的文档元数据

6张支持表只建立来源身份和连接，不独立重复生成事实：

- `hosp.poe`、`hosp.poe_detail` 支持 `hosp.poe_timeline`；
- `hosp.emar_detail` 支持 `hosp.emar`；
- `icu.ingredientevents` 支持 `icu.inputevents`；
- `note.radiology_detail`、`note.discharge_detail` 支持各自文档。

6张上下文表不生成事件：`hosp.patients`、`hosp.admissions`、`hosp.drgcodes`、`icu.icustays`、`icu.datetimeevents`、`ed.edstays`。`icu.chartevents` 与 `hosp.omr` 已在归档上游排除并保留明确理由，不属于当前33张输入表。

输出：

- `cleaned_events.parquet`：通过结构和语义门禁的原始概念事件；`cleaning_status=accepted`，归一化字段保持空值。
- `cleaning_rejected.parquet`：已知数据问题及稳定 reason code；`cleaning_status=rejected`。
- `term_inventory.parquet`：按实体类型、原始编码、原始术语和单位汇总的术语清单。
- `encounter_manifest.parquet`：每次住院的源行、事件和拒绝数。
- `source_reconciliation.json`：逐表验证 `input_rows = accepted_source_rows + rejected_source_rows`。
- `run_manifest.json`：输入及输出 SHA-256、事件计数和确定性 run ID。

`hosp.poe_timeline` 是本阶段唯一的 POE 事件输入。程序同时读取原始 `hosp.poe` 做 `poe_id`、动作和时间交叉验证，但不会从 raw POE 再生成第二批事实。

源表角色、事实拥有者、身份策略、时间策略、纳入理由和合同 SHA-256 定义在 `source_registry.py`。`EVENT_SOURCE_REGISTRY` 只由 `SOURCE_CATALOG` 中的 `role=event` 项自动派生，不能单独维护第二份表单。

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

## 三批清洗回归基线

`tests/fixtures/event-cleaning-regression.json` 固化了人工测试过的100例和两批随机1000例。清单记录每批输入文件的大小与 SHA-256，并对全量事件保存以下逻辑摘要：

- `source_row_id` 与 `event_id` 的有序摘要；
- 全部 cleaned event 和 rejected row 的语义摘要；
- manifest 计数、`event_kind` 和 `evidence_phase` 分布；
- 每个 `source_table × event_kind` 的代表源行；
- 每张源表事件拆分数最大的代表源行。

代表案例保存 `raw_row_ref`、预期事件类型、一对多事件数和允许的质量标志。患者、住院和三个时间字段只保存 SHA-256 期望值，原值继续留在被 Git 忽略的本地数据中。

快速验证三批既有产物没有漂移：

```powershell
uv run --no-cache python -m data_pipeline.event_pipeline.regression verify
```

在未改变清洗合同的日常开发中，可重新运行清洗并与基线比较：

```powershell
uv run --no-cache python -m data_pipeline.event_pipeline.regression verify --rerun
```

当前仓库正在扩展旧14张事件源到21张事实拥有者，已发布Parquet仍对应旧合同。因此在新的cleaned events完成并人工验收前，`--rerun` 会按设计报告合同差异；此时不得执行 `capture` 覆盖旧基线。快速 `verify` 仍用于确认三批既有产物自身没有漂移。

可用 `--batch sample_100`、`--batch random_1000_a` 或 `--batch random_1000_b` 单独复跑。只有在人工确认行为变化符合新的清洗合同后，才允许显式更新基线：

```powershell
uv run --no-cache python -m data_pipeline.event_pipeline.regression capture
```

该回归基线证明原有已验收输出没有被后续修改意外破坏，不代表旧 `SOURCE_REGISTRY` 已经覆盖全部临床源表。源表覆盖完整性仍由独立的 source coverage 门禁负责。

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
- `procedures_icd` 和出院小结均标记 `post_hoc`；行政出院时间、死亡和出院去向才属于 `administrative_end`。
- 对结果类事件，如果源数据出现 `available_time < event_time`，不改写或清空原始时间；整条源行进入 `cleaning_rejected.parquet`，reason code 固定为 `AVAILABLE_BEFORE_EVENT_TIME`。其他 schema、来源追踪和身份约束错误仍会原子终止运行。

## 事件和来源身份

- `source_row_id` 使用合同中显式声明的原生键或复合键；键缺失时硬失败，不再静默回退。没有可靠键的表显式使用 `canonical_row_hash_with_occurrence`，完全重复行以重复序号区分。
- `event_id` 由 `source_row_id + event component` 生成，不依赖 JSONL 行号或数组位置。
- `raw_row_ref` 保留文件名、JSONL 行号、模块、表名和数组下标，供来源门禁回读。
- 跨表派生字段同时保留 `supporting_source_row_ids` 与 `supporting_raw_row_refs`；处方下单时间引用已经与 raw POE 交叉核验的 `poe_timeline` 源行。

### 药物原生键连接

- prescription与POE只允许使用 `poe_id + poe_seq`；只有二者同时匹配时才能取得下单时间。
- prescription与pharmacy、eMAR与pharmacy只允许使用 `pharmacy_id`；eMAR再使用自身 `poe_id` 连接POE。禁止药名相似度、时间邻近或LLM补链。
- eMAR detail使用 `subject_id + emar_id + emar_seq` 回到父eMAR，只作为支持证据，不独立生成药物事实。
- pharmacy的 `medication` 为空时，先按 `pharmacy_id` 读取所有关联prescription。药名唯一则接受，并标记 `MEDICATION_LABEL_RESOLVED_FROM_LINKED_SOURCE`；存在多个不同药名则拒绝为 `PHARMACY_MEDICATION_AMBIGUOUS`；没有候选则拒绝为 `PHARMACY_MEDICATION_UNRESOLVED`。
- 两条原生键链对 `poe_id` 给出不同结果时保留原值和全部来源，标记 `PHARMACY_POE_ID_CONFLICT`，不得覆盖成某一侧的值。
- 一条复合源行可以生成多条原子事件，例如 triage 一行可生成主诉、心率和血压事件；逐表对账按源行而不是事件数计算。

质量标志在事件边界规范为冻结的大写下划线编码；schema 拒绝非规范格式和重复值。

类别级 POE 保持 `concept_id=null`、`content_specificity=category_only`、`normalization_status=unresolved`，不能成为具体检查答案。
