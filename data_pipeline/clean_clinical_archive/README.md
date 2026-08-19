# clean_clinical_archive：字典解码 + POE 医嘱时间线的一体化临床可读清洗包

一次读取 admission 级原始 JSONL，用五份 MIMIC 官方字典把编码行追加为可读释义，并把 POE 医嘱记录重建为按时间排序、带关系链与增量 diff 的"可观察医嘱时间线"，输出 schema 标识为 `mimic_admission_clinical_readable/1.0.0` 的 JSONL。本目录是可整体拷贝搬走的自包含清洗包：代码、规则文档与授权字典全部在目录内，运行只需 Python 3.12 标准库。

## 1. 在流水线中的位置（完成什么事情）

本模块是推荐清洗主流程的第二步：接收 `mimic_raw_archive` 产出的 admission 级原始归档，完成"编码 → 可读文本"与"医嘱行 → 时间线事件"两类确定性派生，交给 `event_pipeline` 做事件化与归一化。

```text
MIMIC-IV 原始 CSV.GZ（hosp / icu / ed / note 各模块表）
        │
        │  data_pipeline.mimic_raw_archive（Admission 级原始归档）
        ▼
mimic_admission_raw/1.0.0 JSONL ──────────────────────────────┐
        │                                                      │
        │  【本模块】clean_clinical_archive                     │
        │    · decoder.py      五份官方字典追加式解码            │
        │    · poe/parser.py   POE 医嘱时间线重建                │
        │    · pipeline.py     端到端编排 + 可逆性自检            │
        │    · verify_bundle.py + bundle-manifest.json 便携自检  │
        ▼                                                      │
mimic_admission_clinical_readable/1.0.0 JSONL  +  report.json（审计报告）
        │
        │  data_pipeline.event_pipeline（事件化 + 归一化）
        ▼
event_pipeline 输出 ──▶ data_pipeline.event_aggregation ──▶ data_pipeline.investigation_selection
```

- **上游**：`data_pipeline.mimic_raw_archive`（`mimic_admission_raw/1.0.0`）。
- **下游**：`data_pipeline.event_pipeline` → `event_aggregation` → `investigation_selection`。失效的 phenotype 线已迁到 `data_pipeline.archived.phenotype`。
- 本模块不依赖 `rwd_pipeline.standardization`，也不需要先运行 `mimic_episode` 或 `parquet_to_jsonl`；旧字典解码入口 `data_pipeline.tools.mimic_dictionary.decode_archive` 反向复用本目录的 `decoder.py` 内核。

## 2. 目录结构与职责

| 文件 | 职责 | 关键函数 / 类 / 常量 |
|---|---|---|
| `__init__.py` | 包公共 API：输入/输出 schema 常量、主入口、逆变换 | `INPUT_SCHEMA`、`OUTPUT_SCHEMA`、`prepare_archive`、`restore_source_record`、`ClinicalReadableArchiveError` |
| `__main__.py` | CLI 入口（argparse），打印一行摘要 | `build_parser()`、`main()` |
| `decoder.py` | 唯一共享字典解码内核（本清洗器与旧 `tools.mimic_dictionary` 共用） | `DECODE_RULES`、`DICTIONARY_KEYS`、`DecodeError`、`load_json_dictionaries()`、`decode_record()`、`decode_records()`、`strip_decoded_fields()`、`file_sha256()`、`load_duckdb_dictionaries()` |
| `pipeline.py` | 端到端编排：schema 校验、逐条解码 + POE 解析、可逆性自检、原子输出与报告 | `validate_input_record()`、`_prepare_record()`、`restore_source_record()`、`_validate_paths()`、`prepare_archive()` |
| `verify_bundle.py` | 便携包完整性自检（Python 版本、文件清单、字典行数/大小/SHA-256） | `verify_bundle()`、`_load_manifest()`、`BundleVerificationError`、`main()` |
| `bundle-manifest.json` | 便携包清单：schema、Python 约束、12 个必需文件、五份字典指纹 | — |
| `poe/__init__.py` | POE 子包导出 | `parse_admission`、`run`、`PoeTimelineError`、`OUTPUT_SCHEMA` |
| `poe/parser.py` | POE 时间线解析核心（约 1000 行）：输入校验、四表连接、动作映射、关系链、增量 diff、质量标志、独立流式入口 | `parse_admission()`、`_validate_order()`、`_snapshot()`、`_medications()`、`_action_from_transaction()`、`_increment()`、`_clinical_changes()`、`_root_and_position()`、`_order_key()`、`run()` |
| `dictionaries/*.json` | 五份 MIMIC 官方字典 JSON 数组（授权资源，不进 Git、不分发，见 §7） | `d_labitems` / `d_items` / `d_icd_diagnoses` / `d_icd_procedures` / `d_hcpcs` |
| `docs/decoding-rules.md` | 编码—字典映射与失败条件（与 `DECODE_RULES` 一一对应） | — |
| `docs/poe-rules.md` | POE 连接、动作、证据边界与质量标志表 | — |
| `docs/schema-contract.md` | 输入/输出 schema 与可逆性契约 | — |
| `docs/mimic-poe-official-evidence.md` | MIMIC-IV v3.x POE 官方语义证据边界（解析器保守设计的依据） | — |

## 3. 工作原理深度解析（如何完成的）

### 3.1 字典解码内核（decoder.py）

**目的**：把源行中的 MIMIC 编码（`itemid`、`icd_code+icd_version`、`hcpcs_cd`）解释为官方可读文本，且绝不改动任何原始字段。

**输入**：`dictionaries/` 下五份 JSON 数组 + 单条 admission 记录。

**固定映射**（`DECODE_RULES` 元组，顺序固定即处理顺序）：

| 源 JSON 路径 | 源键 | 字典（字典键） | 新增字段 |
|---|---|---|---|
| `mimic_iv_hosp.labevents[]` | `itemid` | `d_labitems(itemid)` | `itemid_decoded` |
| `mimic_iv_hosp.diagnoses_icd[]` | `icd_code`+`icd_version` | `d_icd_diagnoses(icd_code, icd_version)` | `icd_decoded` |
| `mimic_iv_ed.diagnosis[]` | `icd_code`+`icd_version` | `d_icd_diagnoses(icd_code, icd_version)` | `icd_decoded` |
| `mimic_iv_hosp.procedures_icd[]` | `icd_code`+`icd_version` | `d_icd_procedures(icd_code, icd_version)` | `icd_decoded` |
| `mimic_iv_hosp.hcpcsevents[]` | `hcpcs_cd` | `d_hcpcs(code)` | `hcpcs_cd_decoded` |
| `mimic_iv_icu.datetimeevents[]` | `itemid` | `d_items(itemid)` + `linksto` 校验 | `itemid_decoded` |
| `mimic_iv_icu.ingredientevents[]` | `itemid` | 同上 | `itemid_decoded` |
| `mimic_iv_icu.inputevents[]` | `itemid` | 同上 | `itemid_decoded` |
| `mimic_iv_icu.outputevents[]` | `itemid` | 同上 | `itemid_decoded` |
| `mimic_iv_icu.procedureevents[]` | `itemid` | 同上 | `itemid_decoded` |

注意两个不对称：`d_hcpcs` 的字典键字段名是 `code` 而源字段是 `hcpcs_cd`；ICU 五张事件表的 `itemid` 除必须命中 `d_items` 外，命中行的 `linksto` 必须与当前表名完全相同（防止跨表错用条目）。

**处理步骤**：

1. `load_json_dictionaries()`：逐份加载（`utf-8-sig` 容忍 BOM），根必须是数组、每行必须是对象、键分量必须完整、键必须唯一，任一违例抛 `DecodeError`；同时记录每份字典的绝对路径、行数、字节数与 SHA-256（进报告与 manifest 校验）。
2. 键归一化（`_clean_key_component`）：一律 `str()` + 去首尾空白，空串归一为 `None`——因此 `itemid: 50801`（数字）与 `"50801"`（字符串）等价匹配。
3. `decode_record()` 按规则元组逐表逐行处理：
   - **追加而非替换**：在源行上新增 `*_decoded` 字段，值为 `{"source_dictionary": <字典名>, **<整行字典条目>}`（如 `label/fluid/category` 或 `long_title`），原始编码原样保留；
   - **键为空**（单键为空或组合键全空）：跳过不解码，计入 `null_keys_by_path`；
   - **组合键部分为空**（如有 `icd_code` 缺 `icd_version`）：立即失败——不允许把缺失版本的编码解释成任何概念；
   - **非空完整键查不到**：立即失败（fail-closed），报出 admission 序号、路径、行号与键值——**不是**静默保留原码继续跑；
   - **行内已存在同名 `*_decoded`**：失败，防止重复加工；
   - **`d_items` 的 `linksto` 与表名不符**：失败。
4. `strip_decoded_fields()` 递归删除一切以 `_decoded` 结尾的键，是可逆性契约（§4）的逆变换基础。
5. `load_duckdb_dictionaries()` 供旧字典入口从 DuckDB 读同样的五张表（可选依赖，主流水线不用）。

**输出**：原地充实的记录 + 计数（`decoded_counts` / `null_key_counts`，报告里按路径排序）。

**确定性**：规则顺序固定、字典为纯键查表、键归一化规则唯一、报告字典按键排序——同一输入与同一字典必然得到逐字节一致的输出。

### 3.2 POE 时间线解析（poe/parser.py: parse_admission）——核心机制

**目的**：把一次住院内散落在四张表里的医嘱记录，重建为一条**按时间排序、可追溯 provenance、带前后关系链与增量 diff** 的"可观察医嘱时间线"。POE 只证明提供者在系统中录入/操作了医嘱，不证明执行；因此输出刻意区分"官方原值"与"派生标签"，绝不发明源表没有的临床内容。

**输入**（单条 admission 内的四个数组，缺一即 `PoeTimelineError`）：

- `mimic_iv_hosp.poe` —— 医嘱主表，每行一条医嘱记录（`poe_id/poe_seq/subject_id/hadm_id/ordertime/order_type/order_subtype/transaction_type/discontinue_of_poe_id/discontinued_by_poe_id/order_status/...`）；
- `mimic_iv_hosp.poe_detail` —— EAV 明细（实体 `poe_id` + `field_name` + `field_value`）；
- `mimic_iv_hosp.prescriptions` —— 处方（经 `poe_id` 挂到医嘱）；
- `mimic_iv_hosp.pharmacy` —— 药房补充（`pharmacy_id` 唯一标识，`poe_id` 可空）。

**处理步骤**（一条 admission 的完整重建流程）：

1. **结构存在性**：四张表必须存在且为数组（`parse_admission` 开头的 Key 检查）；档案顶层 `subject_id`/`hadm_id` 必填。
2. **逐行标识校验**：
   - `_validate_order()`：每条 poe 行的 `poe_id/poe_seq/subject_id/ordertime/order_type` 五字段必填；`subject_id` 必须与档案一致；`hadm_id` 若非空必须一致；`poe_id` 应符合 `subject_id-poe_seq` 格式，不符**不失败**，仅打 `poe_id_format_mismatch` 标志；
   - `_validate_archive_row_ids()`：`poe_detail`（`hadm_id` 可缺）/`prescriptions`/`pharmacy`（`hadm_id` 必填）的行内 `subject_id`、`hadm_id` 必须与档案一致，冲突即失败。
3. **建索引**：`_index_rows_by_poe_id()` 把 `poe_detail`、`prescriptions` 按 `poe_id` 分桶；`_index_pharmacy_by_pharmacy_id()` 建 `pharmacy_id → pharmacy 行`（重复 `pharmacy_id` 失败）；`by_id` 建 `poe_id → poe 行`（重复 `poe_id` 失败）。附属表经 `_validate_linked_rows()` 再校验其携带的 `subject_id/poe_seq/hadm_id` 与所属医嘱行一致。
4. **快照构建（`_snapshot()`，每条医嘱一份）**：
   - `order_type` / `order_subtype`（清洗后原值）；
   - `details`：该 `poe_id` 的全部 EAV 行，按 `(field_name, field_value)` 排序；每条附 `documentation_status`（`_detail_documentation_status()`：官方 v2.2 文档展示过的 11 个字段 → `documented_v2_2`；样本观察到的扩展字段 `Route` → `observed_extension`；其余 → `unclassified`）。EAV 是**开放集合**，未知 `field_name` 不拒绝、不丢值，只计入 `unmapped_detail_field_counts`；
   - `medications`（`_medications()`）：对每条挂在本 `poe_id` 下的处方，字段优先取处方自身值，缺失字段回退到**精确 `pharmacy_id` 匹配**的药房行（`_pharmacy_match()`）。药房行匹配不到 → 标志 `unresolved_pharmacy_id`，只输出处方字段；药房行的 `poe_id` 指向别的医嘱 → 标志 `pharmacy_poe_id_conflict` 并**拒绝**用该行补充——即使本医嘱下只有一条药房记录，也绝不凭"唯一候选"猜连接（对应官方证据文档的工程约束）。每条药物标 `source_tables: ["prescriptions"]` 或 `["prescriptions","pharmacy"]`；结果按规范化 JSON 排序，保证确定序。
5. **事件生成与排序**：对每条 poe 行按 `_order_key() = (ordertime, int(poe_seq), poe_id)` 稳定排序生成事件。`ordertime` 是 ISO 字符串，字典序即时间序；防御性哨兵：缺 `ordertime` 用 `9999-12-31 23:59:59`、非整数 `poe_seq` 用 `2**63-1` 排到末尾（正常情况下这两类行已在第 2 步因必填校验失败）。
6. **动作映射（`_action_from_transaction()`）**，官方六值枚举之外的语义一律不猜：

   | `transaction_type` 原值 | `action` | 中文动作 | 质量标志 |
   |---|---|---|---|
   | `New` | `create` | 新开 | — |
   | `Change` | `change` | 变更 | — |
   | `D/C` | `discontinue` | 停止 | — |
   | `Co` / `H` / `T`（官方列出但未解释） | `uninterpreted` | `未解释的官方操作 X：` | `official_transaction_semantics_unresolved` |
   | 空 | `unknown` | `缺失操作：` | `missing_transaction_type` |
   | 其他任意值 | `unknown` | `未知操作 X：` | `unknown_transaction_type` |

   原值始终保留在 `action_raw`；`order_status`（Active/Inactive）原样放 `order_status_raw`，不用于推断"停嘱时间"。
7. **关系链校验与重建**：`discontinue_of_poe_id` 指向前驱（被本医嘱停止的医嘱），`discontinued_by_poe_id` 指向后继。逐项检查并按具体情况打标志：目标不在本 admission → `unresolved_predecessor` / `unresolved_successor`；反指不一致 → `nonreciprocal_predecessor_link` / `nonreciprocal_successor_link`；类别不同 → `predecessor_category_mismatch` / `successor_category_mismatch`；时间倒挂 → `predecessor_time_after_current_event` / `successor_time_before_current_event`。`_root_and_position()` 沿 `discontinue_of_poe_id` 向上走到链根，输出 `chain_root_poe_id`、`chain_position`（跳数）与 `chain_complete`；检测到环 → `relation_cycle` 并终止上溯。链接缺失或冲突只以标志表达，**从不用内容相似度补链**。
8. **增量计算（`_increment()` + `_clinical_changes()`）**——"这条医嘱相对前驱改了什么"的重建：
   - `_facts()` 把快照展开为事实字符串集合：`order_type=...`、`order_subtype=...`、`detail.<名>=<值>`、`medication[n].<临床字段>=<值>`（仅 `MEDICATION_CLINICAL_FIELDS` 12 个临床字段）；
   - 与前驱快照做集合差 → `added_facts` / `removed_facts`（排序）/ `unchanged_fact_count` / `observable_content_change`；
   - `create`：`comparison_basis=new_order`，全部事实为新增；`discontinue`：`added_facts` 固定为 `["order_state=discontinued"]`，`removed_facts` 为前驱全部事实；`change` 有前驱走 diff、无前驱记 `current_event_only`；
   - `_clinical_changes()` 生成结构化字段级 diff：`changed_field`（类别/子类型）、`changed_detail`（按属性名聚合成值列表再比较，天然容纳重复 EAV 值）、`added_medication` / `removed_medication` / `changed_medication_field`（药物按 `drug_type:drug` 分组）；**同名多条药物的保守策略**：仅 1:1 分组才逐字段比对；多对多时整体比较规范化视图，不同则记一条 `ambiguous_medication_group_change` 并打 `ambiguous_medication_pairing` 标志，绝不给错配；
   - `change` 但可见事实无差异 → `change_without_observable_delta`；
   - `summary_zh` 生成中文摘要（如 `给药频次：q8h → q12h`），无可描述差异时如实写"源数据标记为变更，但可见字段未显示临床内容差异"。
9. **展示与分级**：`display_text_zh = 动作词 + _content_text(快照)`（类别中文标签 `CATEGORY_LABELS_ZH` + 子类型 + 药物摘要 `_medication_text` + 属性明细）；`discontinue` 且前驱可解时**展示的是被停医嘱的内容**（"停止了什么"）。`content_specificity`（`_content_specificity()`）只描述可见内容具体程度：`entity_specific`（有具体处方药物）> `attribute_enriched`（有 EAV 属性）> `subtype_only` > `category_only`；`category_only` 事件（如只有 `order_type=Lab`）额外打 `category_only_no_specific_order_content`，**不猜测**具体检验项目。`resolution_sources` / `medication_resolution` 记录该事件由哪些表支撑、药物字段完整度。
10. **质量标志去重保序**（`dict.fromkeys`）后写入事件；`provenance` 嵌入当前 poe 行 + 三张附属表的关联行（pharmacy 侧为"直接挂本 poe 的行 ∪ pharmacy_id 精确匹配的行"按 `pharmacy_id` 去重，`_unique_rows_by_pharmacy_id()`）；做过前驱比较的还嵌 `comparison` 源行——每条事件可独立复核。

**输出**（事件对象，schema `mimic-poe-timeline-event/2.0.0`，写入 `mimic_iv_hosp.poe_timeline`）：

| 字段 | 含义 |
|---|---|
| `schema` | `{"name":"mimic-poe-timeline-event","version":"2.0.0"}` |
| `subject_id` / `hadm_id` / `event_time` / `poe_id` / `poe_seq` | 归档与时间定位（`event_time`=poe.ordertime） |
| `action` / `action_raw` / `order_status_raw` | 派生动作 / 官方原始事务码 / 官方状态 |
| `clinical_category` | `{raw, zh, subtype_raw}`：官方类别、中文标签、子类型 |
| `display_text_zh` | 一句话中文可读描述 |
| `content_specificity` | 四档内容具体度 |
| `resolution_sources` / `medication_resolution` | 支撑表清单 / 药物字段完整度统计 |
| `order_content` | 当前医嘱快照（类别、子类型、details、medications） |
| `incremental_information` | `comparison_basis`、`added_facts`、`removed_facts`、`unchanged_fact_count`、`observable_content_change`、`clinical_changes[]`、`summary_zh` |
| `relations` | `predecessor_poe_id`、`successor_poe_id`、`chain_root_poe_id`、`chain_position`、`chain_complete` |
| `quality_flags` | 去重后的质量标志列表 |
| `provenance` | `{current: {poe, poe_detail, prescriptions, pharmacy}, comparison: 同构或 null}` |

**失败（`PoeTimelineError`）与质量标志的两档边界**：结构性/完整性问题直接失败——缺四表之一、poe 行缺必填字段、`subject_id`/`hadm_id` 冲突、重复 `poe_id`、pharmacy 行缺 `pharmacy_id`、admission 内重复 `pharmacy_id`、处方缺 `pharmacy_id`、关联行 ID 冲突；而**语义不确定**（未解释事务码、断链、类别不一致、时间倒挂、无法配对的药物、只有类别没有内容）一律保留事件并打标志，不猜、不丢。

**与规则文档的对应**：`docs/poe-rules.md` 的动作表 ↔ `ACTION_LABELS`/`_action_from_transaction()`；关系链与标志表 ↔ 第 7 步各项检查；`content_specificity` 定义 ↔ `_content_specificity()`；`docs/mimic-poe-official-evidence.md` 的证据等级表（`Co/H/T` 只能原样呈现、`pharmacy_id` 严格连接、不改写 POE 证据层级）分别落在第 6 步、`_pharmacy_match()` 与"只输出可观察医嘱时间线"的整体命名上。

**独立入口 `run()`**：保留的便携流式入口（JSONL → 加 `poe_timeline` 的 JSONL + 质量报告，schema `mimic-poe-timeline-quality-report/2.0.0`，含 `poe_detail_coverage`、`resolved_predecessor_rate`、`observable_delta_rate_among_changes` 等覆盖率/速率指标），用临时文件 + `os.replace` 原子落盘。主流水线不经过它（`pipeline.py` 直接调 `parse_admission` 并生成自己的报告），它用于单独调试 POE 解析质量。

### 3.3 端到端流水线（pipeline.py: prepare_archive）

**目的**：把解码与 POE 解析组成一次单遍流式处理，并以"可逆性自检 + 原子落盘"保证输出可信。

**输入**：raw JSONL（`utf-8-sig` 打开，容忍 BOM）、输出路径、报告路径、字典目录、可选 `limit`。

**处理步骤**：

1. **前置约束**（`_validate_paths()` 等）：`limit` 必须为正整数；input/output/report 三个解析后路径必须互不相同；输入文件必须存在；**输出与报告文件均不得已存在**（防覆盖）；对应 `.partial` 文件也不得残留。
2. **字典加载**：`load_json_dictionaries()`（§3.1），失败统一包装为 `ClinicalReadableArchiveError`。
3. **逐条处理（`_prepare_record()`）**：
   - `validate_input_record()`：记录必须是对象；**顶层字段名及其顺序必须严格等于** `(schema, subject_id, hadm_id, mimic_iv_hosp, mimic_iv_icu, mimic_iv_ed, mimic_iv_note)`；`schema` 必须逐字段等于 `{"name":"mimic_admission_raw","version":"1.0.0"}`；`subject_id`/`hadm_id` 非空；四个模块组必须是对象——防止旧格式或已加工数据被再次当作 raw 清洗；
   - 深拷贝后依次 `decode_record()`（追加字典释义）与 `parse_admission()`（得到事件列表），两类底层错误统一包装为带记录序号的 `ClinicalReadableArchiveError`；
   - 事件写入 `mimic_iv_hosp.poe_timeline`；顶层 `schema` 替换为输出 schema，并新增 `source_schema` 保存原 raw schema；
   - **可逆性自检**：`restore_source_record(prepared)`（递归删 `_decoded` 字段 → 删 `poe_timeline` → 弹出 `source_schema` 并用它恢复 `schema`）必须与输入记录深度相等，否则整趟失败——任何原始字段被删除、覆盖或改值都逃不过这一步。
4. **流式写出**：紧凑 JSON（`ensure_ascii=False`，`separators=(",",":")`，`\n` 行尾）写入 `*.partial`（`"x"` 独占模式创建）。空行、非法 JSON、admission 数为 0 均失败。
5. **报告与原子提交**：先写报告 `.partial` 并**回读解析**验证 JSON 有效；再 `replace` 输出、置 `output_finalized`、`replace` 报告。任何异常都会删除两个 `.partial`（及已提交的输出文件）后重新抛出——**不存在部分成功的输出**。

**输出**：`mimic_admission_clinical_readable/1.0.0` JSONL + `report.json`。

**report.json 内容**：输出/输入/POE 三个 schema 标识；输入与输出的绝对路径、字节数与 SHA-256；字典目录与五份字典各自的路径/行数/字节数/SHA-256；`admissions`；`dictionary_decoded_total`、`decoded_by_path`、`null_keys_by_path`（按路径排序）；`unresolved_total`（成功报告恒为 `0`，因为非空完整键未命中直接失败，不会产出"部分解码"的报告）；`poe_events`、`poe_action_counts`、`poe_quality_flag_counts`；`limit`；`output_bytes`、`output_sha256`。

### 3.4 便携包自检（verify_bundle.py + bundle-manifest.json）

**目的**：这个包设计为"整个目录拷走即用"，但字典受授权约束不进 Git、拷贝过程可能遗漏或截断文件——自检在首次使用或复制后证明包完整且未被篡改。

**校验项**（`verify_bundle()`，任何一项不符抛 `BundleVerificationError`）：

1. `bundle-manifest.json` 存在、合法 JSON、根为对象；
2. **运行时 Python 必须恰好是 3.12**（`sys.version_info[:2] == (3, 12)`，与 manifest 的 `minimum 3.12 / maximum_exclusive 3.13` 一致）；
3. manifest `required_files` 列出的 12 个文件（README、五个顶层 py 文件、`poe/` 两个文件、四份 docs）全部存在；
4. `dictionaries/` 能通过 `load_json_dictionaries()` 的全部结构校验（数组、行对象、键完整唯一）；
5. 字典清单与 manifest 完全一致，且每份字典的**行数、字节数、SHA-256** 三项逐一与 manifest 指纹相等。

**输出**：JSON 摘要（schema、bundle_root、Python 版本、文件数、每份字典实测指纹、总行数 293,483、`status: "ok"`），由 `main()` 打印。manifest 本身记录：schema `clean_clinical_archive_portable_bundle/1.0.0`、纯标准库依赖声明、五份字典指纹（`d_labitems` 1,650 行 / `d_items` 4,095 行 / `d_icd_diagnoses` 112,107 行 / `d_icd_procedures` 86,423 行 / `d_hcpcs` 89,208 行，合计约 36.5 MB）。

## 4. 数据契约

**输入**（`docs/schema-contract.md` + `validate_input_record()`）：UTF-8 JSONL，一行一条 admission。顶层字段及**顺序**固定为 `schema, subject_id, hadm_id, mimic_iv_hosp, mimic_iv_icu, mimic_iv_ed, mimic_iv_note`；`schema` 严格等于 `{"name":"mimic_admission_raw","version":"1.0.0"}`；`subject_id`/`hadm_id` 非空；四个模块为对象。另因解码与 POE 规则的存在，每条记录需包含十条解码路径对应的数组（可为空数组）与 `mimic_iv_hosp.poe/poe_detail/prescriptions/pharmacy` 四个数组（可为空），缺失按 fail-closed 处理。

**输出**：一行一条 admission，schema 为 `{"name":"mimic_admission_clinical_readable","version":"1.0.0"}`，新增顶层 `source_schema`（原 raw schema）。派生内容只有三处：源行上的 `itemid_decoded` / `icd_decoded` / `hcpcs_cd_decoded`、`mimic_iv_hosp.poe_timeline`（每元素 schema `mimic-poe-timeline-event/2.0.0`，结构见 §3.2）、顶层 `source_schema`。输出 schema 与 raw schema 分开命名，让下游能明确区分"未经加工的原始归档"与"含确定性派生字段的临床可读归档"。

**可逆性契约**：对每条输出依次执行 ① 递归删除所有以 `_decoded` 结尾的字段（`strip_decoded_fields`）；② 删除 `mimic_iv_hosp.poe_timeline`；③ 删除顶层 `source_schema`；④ 用 `source_schema` 恢复 `schema`——结果必须逐字段等于输入记录。流水线在写出每条记录前实际执行这一比较（`_prepare_record` 末尾），不等即失败。

**报告结构**：见 §3.3；报告自身在落盘前会被回读解析验证。

## 5. 正确性与可靠性保障

**fail-closed 条件清单**（任一触发即整趟失败，无部分输出）：

- 路径与参数：输入文件不存在；input/output/report 路径重叠；输出、报告或对应 `.partial` 已存在；`limit ≤ 0`；
- 字典：目录/文件缺失；JSON 非法；根非数组；行非对象；字典键不完整；字典键重复；
- 输入记录：空行；非法 JSON；非对象行；顶层字段名或顺序漂移；schema 身份不符；`subject_id`/`hadm_id` 缺失；模块组缺失或非对象；十条解码路径任一数组缺失/含非对象；行内已有 `*_decoded`；组合键部分为空；非空完整键未命中字典；`d_items` 的 `linksto` 与表名不符；
- POE：四表缺失或非数组；poe 行缺五个必填字段之一；`subject_id`/`hadm_id` 与档案冲突；admission 内重复 `poe_id`；pharmacy 行缺 `pharmacy_id` 或重复；处方缺 `pharmacy_id`；附属行与所属医嘱的 `subject_id/poe_seq/hadm_id` 冲突；
- 收尾：admission 数为 0；可逆性自检不等；报告回读解析失败。

**防覆盖 / 原子性**：输出与报告先写 `.partial`（输出以独占模式 `"x"` 创建），全部成功并验证后才原子 `replace`；失败路径统一清理 `.partial` 与已提交文件。已存在的目标文件直接 `FileExistsError`。

**确定性约束**：解码规则顺序固定；事件按 `(ordertime, poe_seq, poe_id)` 稳定排序；details/medications 排序确定；质量标志去重保序；计数器落报告前排序；紧凑 JSON + `\n` 行尾——同输入同字典得到逐字节一致输出，报告中的 SHA-256 可独立复验。

**语义不确定≠失败**：未解释事务码、断链、类别不一致、时间倒挂、同名药物无法配对、只有类别无内容等，全部以 `quality_flags` 显式呈现（见 §3.2），既不猜也不丢。

## 6. 使用方法

**方式一：项目内运行**（仓库根目录，用虚拟环境 Python）：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.clean_clinical_archive `
  data\mimic-admission-raw-coronary-all-three-modules-random-100.jsonl `
  --output data\clean_clinical_archive\random-100-clinical-readable.jsonl `
  --report data\clean_clinical_archive\random-100-clinical-readable.report.json
```

**方式二：拷贝后独立运行**（把 `clean_clinical_archive` 整个目录复制到任意位置，在其父目录执行，任意 Python 3.12）：

```powershell
python -m clean_clinical_archive `
  input.jsonl `
  --output output-clinical-readable.jsonl `
  --report output-clinical-readable.report.json
```

**参数表**（`__main__.py: build_parser()`，与 `prepare_archive()` 约束一致）：

| 参数 | 必填 | 默认值 | 约束与说明 |
|---|---|---|---|
| `input`（位置参数） | 是 | — | Admission 级 raw JSONL 路径，文件必须存在 |
| `--output` | 是 | — | 输出 JSONL；已存在即报错（防覆盖） |
| `--report` | 是 | — | 运行报告 JSON；已存在即报错 |
| `--dictionary-dir` | 否 | 包内 `dictionaries/` | 五份官方字典 JSON 所在目录，可指向同结构外部目录 |
| `--limit` | 否 | `None`（全量） | 只处理前 N 条 admission；必须为正整数，适合小批量验证 |

三个路径参数解析后必须互不相同。运行结束打印一行摘要（admissions、decoded rows、POE events）。

**便携包自检**（首次使用或复制后必跑）：

```powershell
# 拷贝后的包内：
python -m clean_clinical_archive.verify_bundle

# 项目内：
.\.venv\Scripts\python.exe -m data_pipeline.clean_clinical_archive.verify_bundle
```

**单元测试**（仓库根目录）：

```powershell
.\.venv\Scripts\python.exe -m unittest -v `
  tests.test_clean_clinical_archive `
  tests.test_poe_timeline
```

- `tests/test_clean_clinical_archive.py`：十条路径全量解码 + POE 附加 + schema 标识、共享解码内核、默认字典位置在包内、脱离项目导入可运行、错误 schema 无残留输出、部分 ICD 键拒绝、未解析编码拒绝、`d_items` 表不符拒绝、字典键重复拒绝；
- `tests/test_poe_timeline.py`：create→change→discontinue 链重建、重复 EAV 值保留与不可见变更、官方未解释事务码与断链标志、非法/缺失事务值区分、流式 JSONL 与质量报告、缺源表拒绝、`poe_id` 官方连接与重复键冲突拒绝、输出路径冲突拒绝、绝不回退到不匹配的 `pharmacy_id`、`pharmacy.poe_id` 为空时仍按精确 ID 连接、指向其他 POE 的药房行不用于补充、非互指后继链标志、必填字段缺失与档案 ID 冲突拒绝、同名药物保守 diff、比较 provenance 嵌入与明细来源分级。

## 7. 设计取舍与已知限制

- **字典授权约束（硬边界）**：五份官方字典受 MIMIC 数据使用协议约束，作为本地授权资源随包使用，**不进入 Git、不公开分发**。全新 clone 或复制不完整的目录会缺字典，`verify_bundle` 与主流水线都会明确报缺而非降级运行。
- **纯标准库 + Python 3.12**：主流水线只用标准库；`verify_bundle` 硬性要求解释器恰为 3.12（manifest：`3.12 ≤ version < 3.13`）。DuckDB 读取仅为旧字典入口的可选依赖。
- **追加式解码优先于紧凑**：为满足可逆性与可复核性（`source_dictionary` + 整行字典条目 + 完整 provenance 嵌入），输出明显大于输入；换取的是每条派生结论可独立回溯到官方字典行与源表行。
- **fail-closed 与质量标志两档**：结构/完整性错误宁可整趟失败也不产出"部分解码"的数据（`unresolved_total` 恒为 0 的含义）；语义不确定保留原值 + 标志。代价是大批量数据中单条脏行会终止整趟，需要先修数再重跑。
- **证据边界（不猜测清单）**：`Co/H/T` 不扩写为临床动作；`order_status` 不用于推断停嘱时间；断链不靠内容相似度补全；药房行不凭"唯一候选"连接；`category_only` 事件不猜具体项目名；处方不当作实际给药、药房状态不当作床旁执行。要回答"医嘱是否执行"，需另行连接 `emar/emar_detail`、检验结果、影像报告或 ICU 执行事件，不能改写 POE 本身的证据层级。
- **POE 语义范围**：POE 只是"可观察医嘱时间线"——官方仅说多数治疗和操作经 POE 下达，MIMIC 准备过程还移除了 audit trails，因此输出不宣称是完整 EHR 审计历史。
- **admission 内闭合**：关系链只在当前 admission 内解析，指向其他住院的 `discontinue_of`/`discontinued_by` 目标记为 `unresolved_*`；`poe.hadm_id` 官方可空（`poe_detail` 行不强制携带 hadm）。时间沿用 MIMIC 去标识化平移时间，仅患者内相对时序可解释，排序依赖 ISO 字符串字典序。
- **`chartevents`、微生物表不入解码范围**：前者不在当前 raw archive 契约内；后者已自带可读描述字段且无独立可靠字典映射；放射检查名称也不从 POE 类别猜测。
