# event_pipeline：MIMIC 临床事件的确定性结构化与门禁化发布站

本模块把"临床可读 admission JSONL"事件化为**一行一事件的 Parquet**，再做**冻结规则的确定性归一化**；两级独立审计、跨批大小复跑 SHA-256 对比和人工回归基线全部通过后，才以**临时目录 + rename 原子发布**正式产物。全程 fail-closed：任一门禁失败即抛异常、清理临时目录，绝不留下半成品。

## 1. 在流水线中的位置（完成什么事情）

```text
MIMIC 原始 CSV.GZ
      │
      ▼
mimic_raw_archive          每次住院一行原始 JSONL（mimic_admission_raw/1.0.0）
      │
      ▼
clean_clinical_archive     字典解码 + POE 解析的临床可读 JSONL（mimic_admission_clinical_readable/1.0.0）
      │                    （32 张原始表 + 1 张派生表 hosp.poe_timeline，按 module.table 分组内嵌）
      ▼
┌───────────────────────── event_pipeline（本模块）─────────────────────────┐
│  cleaning        33 张登记表 → 结构化事件 + 拒绝记录 + 逐表对账            │
│  normalization   冻结术语/单位规则 → 8 个归一化字段 + review queue          │
│  quality         两级独立审计 + 复跑 SHA-256 对比 + 人工回归基线            │
│  review/viewer   人工审阅包与本机只读浏览器                                │
└──────────────────────────────────────────────────────────────────────────┘
      │  cleaning/cleaned_events.parquet、normalization/normalized_events.parquet
      ▼
event_aggregation         无损聚合
      │
      ▼
phenotype                 visit 级特征
```

- **上游**：`--raw-source-jsonl`（原始 JSONL，供审计反推"解码未改动原始内容"）与位置参数 `source_jsonl`（临床可读 JSONL，也可直接传 raw schema 输入，`validation.py: ACCEPTED_INPUT_SCHEMAS` 同时接受两种）。
- **下游**：`event_aggregation` 只消费通过全部门禁后发布的 `cleaned_events.parquet` / `normalized_events.parquet`。

## 2. 目录结构与依赖方向

```text
event_pipeline/
├── __init__.py            # 唯一公共门面：run_cleaning / run_normalization / run_workflow / resume_workflow
├── __main__.py            # 唯一 CLI 入口（run/resume/clean/normalize/view/review/review-ui/review-master/regression）
├── workflow.py            # 固定顺序、门禁、复跑、原子发布、断点续跑
├── event_contracts/       # 纯合同：Arrow schema + JSON Schema + 冻结状态枚举（不读数据、不产事件）
│   ├── schemas.py         # 6 个 pa.schema（event/encounter/rejected/review/term_inventory/mapping）+ 28 个质量旗标枚举
│   ├── statuses.py        # CLEANING_STATUSES / NORMALIZATION_STATUSES / UNIT_NORMALIZATION_STATUSES
│   └── schemas/clinical-event.schema.json   # 事件级 JSON Schema（draft 2020-12）
├── event_cleaning/        # 事件化：登记、身份、时间语义、校验、transformer 注册表（25 个实现：21 活跃 + 4 休眠）
│   ├── source_catalog.py  # 封闭 33 表登记 + 19 条时间策略 + 目录 SHA-256
│   ├── ids.py             # src:/evt:/ent: 稳定 ID（clinical-event-id/1.0.0）
│   ├── time_resolver.py   # 事件时间/有效可用时间的确定性推导
│   ├── models.py          # SourceSpec / SourceRow / AdmissionContext / TimePolicy
│   ├── validation.py      # 输入外壳、JSON Schema、血缘、时间一致性、POE 交叉核对
│   ├── pipeline.py        # 流式写出 6 个 cleaning 产物
│   └── transformers/      # ed / laboratory / medications / orders / diagnoses_procedures / icu / notes + registry
├── event_normalization/   # 冻结术语表 + 单位别名表 → 确定性归一化（不调 LLM、不猜 unresolved）
│   ├── terminology.py     # MAPPING_VERSION、REVIEWED_TEXT_MAPPINGS、UNIT_ALIASES、resolve_term/resolve_unit
│   ├── pipeline.py        # term_inventory 先建映射，再逐事件应用并强校验
│   └── io.py              # 本阶段自有 Parquet/SHA-256/原子发布基础设施
├── event_quality/         # 独立审计（不 import transformer / terminology）
│   ├── audit_cleaning.py  # 全量独立复算：身份/时间/标签/拒绝原因/逐表对账/上游等价
│   ├── audit_storage.py   # 有界存储：JSONL 字节偏移索引、按需 ID 解析、DuckDB 磁盘对账索引
│   ├── audit_normalization.py # 不可变字段逐事件比对 + 冻结术语表副本复算
│   ├── reproducibility.py # 两次运行 8 个数据文件 + 6 项合同逐一 SHA-256 比较
│   ├── regression.py      # 三批人工确认基线的 capture/verify（隐私安全指纹）
│   ├── review_normalization.py # 生成人工审阅包（硬门禁 + 分层抽样 + 决策表）
│   └── consolidate_review.py   # 跨批合并 + 固定 100 条试审
└── event_viewer/          # 本机只读浏览器 app.py + 人工审阅窗口 review_app.py（追加式日志）
```

依赖方向（= import，箭头向上）：

```text
event_contracts                    零依赖，人人 import 它
      ▲   ▲   ▲
      │   │   │
event_cleaning ──────────┐         只依赖 contracts
      ▲   ▲              │
      │   └─ event_normalization   contracts + cleaning.validation
      │         （复用 EventValidator / EventPipelineError）
      │                     ▲
      └──── event_quality ──┘         contracts + cleaning（版本常量、SOURCE_CATALOG、
                  │                    冻结 ID 算法）+ normalization.io + viewer.review_app
                  ▼                    （review_app.py 被复制进每个审阅包）
              workflow                 cleaning + normalization + quality（顶层编排）
```

要点：`event_cleaning` 不依赖 normalization（箭头方向恰好相反，是 normalization 借用 cleaning 的校验器）；`event_quality` 额外借用 `event_viewer.review_app`（旧版依赖图未画出的边）。

关键纪律：`event_cleaning` 不依赖 normalization；**质量审计从不调用 transformer 或术语映射规则来"复述"生产实现**（见 §5）。

## 3. 工作原理深度解析

### 3.1 事件合同（event_contracts）

**目的**：让 cleaning / normalization / quality / viewer 四方共享同一份冻结契约，任何字段变更必须显式升版本并同步全部消费者。

**内容**：
- `schemas.py: EVENT_ARROW_SCHEMA`（47 列，metadata `clinical_event/1.2.0`）+ 5 个伴生 Arrow schema（encounter_manifest/1.1.0、rejected_event/1.1.0、term_inventory/1.0.0、normalization_mappings/1.0.0、normalization_review_queue/1.0.0）。
- `schemas/clinical-event.schema.json`：与 Arrow schema 一一对应的事件级 JSON Schema（`$id` …/clinical-event/1.2.0），额外施加值域约束（枚举、正则、`additionalProperties: false`、全部 47 字段 required）。`EventValidator` 用它做逐事件校验；Arrow schema 负责 Parquet 物理布局与审计的 `_arrow_schema_matches` 比对，两者是"同一合同的两面"。
- `schemas.py: QUALITY_FLAG_CODES`：28 个冻结质量旗标，`transformers/common.py: _canonical_quality_flags` 会拒绝任何不在枚举中的旗标。
- `statuses.py`：cleaning 只有 `accepted/rejected`；归一化只有 `mapped/unresolved/not_applicable`。

**关键代码**：`event_contracts/schemas.py`、`event_contracts/statuses.py`。

### 3.2 Cleaning：把 33 张表变成可追溯原子事件

**目的**：一事件一行、无信息凭空产生、每行都能回查到唯一源数组元素。

**输入**：admission 级 JSONL（每行 = 一次住院，内含 4 个 module × 若干表数组）。

**处理步骤**：

1. **封闭登记（source_catalog.py）**：`SOURCE_CATALOG` 登记全部 33 张表 = **21 fact owner（event 角色）+ 6 support + 6 context**。模块加载即执行 `validate_source_catalog()` 自检（fact owner 必须自持、support 的 owner 必须是 event 源、context 不得拥有事实、身份策略与键字段匹配等）。整个目录序列化为规范 JSON 后取 SHA-256 = `SOURCE_CATALOG_SHA256`，写入每个 manifest，供 resume 校验与审计比对。
   - **fact owner（角色= event，产出事件）**举例：`hosp.labevents`（own `laboratory_resulted`）、`ed.triage`（chief complaint/acuity/生命体征）、`icu.inputevents`（给药区间）、`hosp.poe_timeline`（全目录唯一 `origin="derived"` 的派生订单时间线）、`hosp.prescriptions`、`hosp.emar`。
   - **support（登记加载、永不独立转换）**举例：`hosp.poe`（原始 POE 行，只为派生 timeline 提供交叉核对证据）、`hosp.poe_detail`/`hosp.emar_detail`（丰富父订单/给药的剂量、途径、成分）、`icu.ingredientevents`（成分为其属主 input 区间服务，防止重复计给药）、`note.radiology_detail`/`note.discharge_detail`。
   - **context（界定边界，不产事实）**举例：`hosp.patients`、`hosp.admissions`、`icu.icustays`、`ed.edstays`、`hosp.drgcodes`（出院行政分组）、`icu.datetimeevents`（值-时间语义冻结前显式搁置）。
   - 每张表绑定一条 `TimePolicy`（共 19 条）与 `evidence_phase`（source_event / post_hoc / administrative_end）。
2. **外壳与 POE 校验（validation.py）**：`validate_admission_shell` 检查 schema 身份、subject/hadm、4 模块结构、**任何未登记表即 `UNREGISTERED_SOURCE_TABLE` 拒绝、缺必需表即 `REQUIRED_SOURCE_TABLE_MISSING` 拒绝**（封闭世界）；`crosscheck_poe_timeline` 逐行核对 `poe` 与 `poe_timeline` 行数一致、poe_id 全覆盖、`New/Change/D/C → create/change/discontinue` 动作一致、`ordertime == event_time`，防止派生层悄悄改写订单语义。
3. **原生键身份（ids.py）**：`build_source_row_id` 按 SourceSpec 的身份策略生成 `src:` ID——单键表用 `native_key`（如 `labevent_id`）、多键表用 `composite_key`（如 `subject_id stay_id charttime`）、无原生键表用 `canonical_row_hash_with_occurrence`（整行 canonical JSON 哈希；完全重复行追加 `duplicate_occurrence=N` 序数，避免静默碰撞）。`build_event_id` = `sha256(ID_VERSION + source_row_id + component)` → `evt:`；`build_entity_id` = `sha256(event_id + 'primary-entity')` → `ent:`。全部截断 24 位 hex，版本前缀 `clinical-event-id/1.0.0`。
4. **回查指针（models.py）**：`SourceRow.raw_row_ref` = `文件名#L行号/module.table[数组下标]`，viewer/审计据此做字节偏移随机回查。
5. **时间语义（time_resolver.py: resolved_times）**：四个时间字段分工——`event_time`（发生时间：charttime/starttime/entertime/transfertime/intime…）、`source_available_time`（源声明的可用时间，如 storetime，**原样保留即使早于事件**）、`available_time`（泄漏安全有效可用时间 = `max(源可用, 事件时间, 完成下界)`）、`recorded_time`（系统记录时间）。三条推导规则各自配一对 reason+flag：`source_available_precedes_event_time`+`AVAILABLE_BEFORE_EVENT_TIME`（解释性，不改动）、`completion_time_lower_bound`+`AVAILABLE_TIME_DERIVED_FROM_COMPLETION`（ICU 区间完成前不可见）、`event_time_lower_bound`+`AVAILABLE_TIME_CLAMPED_TO_EVENT_TIME`（钳制）；缺失则 `AVAILABLE_TIME_UNKNOWN`。状态机：三时间全空 = `unresolved`，事件+可用都有 = `resolved`，否则 `partially_resolved`；精度按首个非空值判 `subsecond/second/date/unknown`。**绝不猜测或填充时间**。
6. **事件化（transformers/）**：`registry.py: TRANSFORMERS` 以 `transform_` 前缀自动收集 25 个实现，提供 `SourceSpec.transformer_name`（合同名）→ 实现函数 的唯一路由。各域（详见 §3.2.1）输出 dict 列表，`common.py: _event` 统一组装 47 字段。
7. **流水线（pipeline.py: run_cleaning）**：逐 admission 构建 `AdmissionContext`（12 个按需索引：poe_by_pair、pharmacy_by_id、emar_details_by_parent、icu_ingredients_by_linkorder…）→ 逐 event 源逐行调 transformer → `EventValidator.validate` 逐事件过 JSON Schema + 血缘 + 时间一致性 → 去重（全局 `DUPLICATE_EVENT_ID` 立即失败）→ `BufferedParquetWriter` 流式写出。`KnownTransformationError`（预期内业务拒绝，如药物名为空）写 `cleaning_rejected.parquet`；`EventPipelineError`（合同破坏）直接终止。support 行统计被事件 `supporting_source_row_ids` 引用即计"已关联"。末尾强校验 `classified == total`（`SOURCE_RECONCILIATION_FAILED`），写 `source_reconciliation.json` + `run_manifest.json`（含全部输出 SHA-256 与 run_id）。

**§3.2.1 各 transformer 的表→事件类型与关键规则**：

| transformer | 源表 | event_kind | 关键去重/过滤规则 |
|---|---|---|---|
| `transform_ed_triage` | ed.triage | symptom_reported / vital_measured / triage_acuity_recorded | 一行最多拆 8 事件（主诉+5 项生命体征+血压合并+acuity）；全空 → `NO_EVENT_GENERATED` 拒绝；无时间戳统一 `TIME_UNAVAILABLE_IN_SOURCE` |
| `transform_ed_vitals` | ed.vitalsign | vital_measured | 同上生命体征拆分；收缩/舒张压合并为单个 `blood_pressure` 结构化事件 |
| `transform_labevent` | hosp.labevents | laboratory_resulted | 缺 itemid 或解码标签 → `LAB_CONCEPT_MISSING` 拒绝；`flag` 缺失时按参考区间推导 abnormal_flag；`value="___"` 且有数值时清空文本 |
| `transform_microbiology` | hosp.microbiologyevents | microbiology_resulted | 无 test_name/specimen 名 → 拒绝；标本/病原/抗生素/稀释度全部进 value_structured_json |
| `transform_poe_timeline` | hosp.poe_timeline（derived） | laboratory_ordered / imaging_ordered / clinical_ordered | 只事件化派生时间线，原始 `poe` 行只作 supporting 证据；`category_only` 强制加 `CATEGORY_ONLY_NO_SPECIFIC_ORDER_CONTENT` |
| `transform_prescription` | hosp.prescriptions | medication_ordered | **订单时间只取唯一匹配的 poe_timeline.event_time，绝不用 prescription.starttime 顶替**；匹配失败 → `ORDER_TIME_UNRESOLVED`；pharmacy_id 多义 → `AMBIGUOUS_MEDICATION_PAIRING`；与 pharmacy 行 poe_id 冲突 → `PHARMACY_POE_ID_CONFLICT` |
| `transform_pharmacy` | hosp.pharmacy | medication_order_status_recorded | 药名缺失时按 pharmacy_id 回链 prescriptions；唯一候选回填（flag 标注）、多候选拒绝、零候选拒绝 |
| `transform_emar` | hosp.emar | medication_administered / not_administered / administration_documented | `event_txt` 白名单三分类：Administered 系→present、Not Given/Hold 系→absent、其余→unknown；药名经 pharmacy→prescriptions 链回填并 flag |
| `transform_service` / `transform_transfer` | hosp.services / hosp.transfers | service_changed / patient_transferred | 时间策略声明 `reject_missing_event_time`/保持 null；实现层面 transfertime/intime 缺失时仍产事件（null 时间 + `time_resolution_status=unresolved`），transfer 恒加 `AVAILABLE_TIME_UNKNOWN` |
| `transform_diagnosis` / `transform_ed_diagnosis` / `transform_procedure_icd` / `transform_hcpcs` | hosp.diagnoses_icd / ed.diagnosis / hosp.procedures_icd / hosp.hcpcsevents | condition_recorded_post_hoc / procedure_recorded_post_hoc | 代码缺失 → `CODE_MISSING`；编码系统动态 `icd9/icd10`、`hcpcs`；全部 post_hoc + `AVAILABLE_TIME_UNKNOWN` |
| `transform_icu_input` / `transform_icu_output` / `transform_icu_procedure` | icu.inputevents / outputevents / procedureevents | input_administered / output_measured / procedure_performed | 缺 itemid/解码 → `ICU_CONCEPT_MISSING`；input/procedure 的可用时间以 `max(endtime, storetime)` 为完成下界（区间完成前不可见）；input 关联 ingredient 成分作为 supporting |
| `transform_radiology_note` / `transform_discharge_note` | note.radiology / note.discharge | imaging_reported / document_recorded | 详情行按 note_id 挂为 supporting；**正文永不复制进 value_text**（审计专查 `discharge_text_copied_to_event`） |

（registry 还登记了 `transform_poe`、`transform_drg`、`transform_icu_datetime`、`transform_icu_ingredient` 四个"休眠"实现——目录中 poe/drgcodes/datetimeevents/ingredientevents 分别是 support/context/context/support 角色，合同阶段已声明但当前不产事件。）

**输出**（`cleaning/` 目录，6 个文件）：

| 文件 | 含义 |
|---|---|
| `cleaned_events.parquet` | 通过事件（47 列，行组 5000，zstd） |
| `cleaning_rejected.parquet` | 预期内拒绝：source_row_id + raw_row_ref + reason_code + message |
| `term_inventory.parquet` | 术语清单：`(entity_type, source_concept_id, 归一化标签, unit)` 四元组聚合，含 event_count 与 first_event_id，按事件数降序 |
| `encounter_manifest.parquet` | 逐 admission 对账：raw/derived 源行数、事件数、拒绝数 |
| `source_reconciliation.json` | 33 表逐表分类计数 + support 关联计数 + POE 交叉核对总数 |
| `run_manifest.json` | schema/版本/目录 SHA-256/输入哈希/全部输出 SHA-256/event_kind 分布 |

**关键代码**：`event_cleaning/pipeline.py: run_cleaning / _source_rows_for_admission / _build_context`、`source_catalog.py: SOURCE_CATALOG / validate_source_catalog`、`ids.py: build_source_row_id`、`time_resolver.py: resolved_times`、`validation.py: EventValidator.validate / validate_admission_shell / crosscheck_poe_timeline`、`transformers/registry.py: TRANSFORMERS`、`transformers/common.py: _event`。

### 3.3 Normalization：冻结规则的确定性归一化

**目的**：只做可解释、可复现的术语/单位归一化；不确定就显式 `unresolved` 进 review queue，绝不猜。

**输入**：`cleaned_events.parquet` + `term_inventory.parquet`（不读 JSONL、不调 LLM）。

**处理步骤**（`event_normalization/pipeline.py: run_normalization`）：
1. **先建映射**：对 term_inventory 每行调 `terminology.py: resolve_term / resolve_unit`，产出 `normalization_mappings.parquet`（每行含 mapping_rule）。
2. **映射规则（terminology.py）**：有效源编码 → `mapped`（rule=`source-code`）；源编码存在但无效 → `unresolved`（rule=`invalid-source-code`）；命中 `REVIEWED_TEXT_MAPPINGS` 冻结同义词表（当前 2 条：chest pain、general xray）→ `mapped`；无 entity_type → `not_applicable`；其余 → `unresolved`。
3. **NDC/GSN 校验（`_source_code_is_usable`）**：`ndc:` 必须恰好 11 位数字且非全 0；`gsn:` 必须恰好 6 位数字；其他词表不校验格式。
4. **单位归一化（`resolve_unit` + `UNIT_ALIASES`）**：47 条冻结别名（`mg/dl→mg/dL`、`mmhg→mmHg`、`°f→°F`、`sec→s` 等，键为 casefold 归一文本）；`n/a` 视为 `not_applicable`；查不到 → `unresolved`。
5. **逐事件应用**：`normalize_event` 只写 **8 个归一化字段**——`concept_id`、`preferred_name`、`normalization_status`、`terminology_mapping_version`、`normalized_value_numeric`（=原 value_numeric，直通）、`normalized_value_text`（=原 value_text，直通）、`normalized_unit`、`unit_normalization_status`。**其余 39 列原样不动**。
6. **双保险校验**：cleaned 事件若已带归一化值 → `CLEANED_EVENT_ALREADY_NORMALIZED`；事件重算结果必须与第 1 步映射表逐字段一致（`MAPPING_APPLICATION_MISMATCH`），证明映射与应用同源；再过一遍 `EventValidator`（复用 cleaning 的校验器，字段级合同同一份）。
7. **review queue 判定**：映射行 `normalization_status=unresolved`（TERM_UNRESOLVED）或 `unit_normalization_status=unresolved`（UNIT_UNRESOLVED），两者可叠加，写入 `normalization_review_queue.parquet`。

**输出**（`normalization/` 目录）：`normalized_events.parquet`（与 cleaned 同 schema 同行序）、`normalization_mappings.parquet`、`normalization_review_queue.parquet`、`normalization_manifest.json`（run_id = sha256(cleaned 哈希|MAPPING_VERSION)）。

**关键代码**：`event_normalization/terminology.py: resolve_term / resolve_unit / normalize_event`、`pipeline.py: run_normalization / _term_key`、`io.py: BufferedParquetWriter / remove_temporary`。

### 3.4 Quality：独立审计、复现门禁、回归基线、审阅闭环

#### 3.4.1 audit_cleaning —— 不依赖实现的身份/时间/对账全量复算

**为何不调用 transformer 也能证明正确**：审计只读"不可变输入（原始 + 临床可读 JSONL）"与"已产出的 Parquet"，从零**独立重算**期望值再逐项比对——`_expected_times` + `_resolved_time_contract` 按 21 张事件表各自重推时间四元组（与 time_resolver 语义平行实现而非 import）；`_expected_pharmacy_label / _expected_emar_label` 独立重演药名回链；`_expected_rejection_reason` 独立重推拒绝原因；`_expected_event_count` 独立数出 ED 行应拆几个事件。若 transformer 有 bug，期望值与实际值必然分叉并被逐事件点名的 issue 码抓住。它 import 自 cleaning 的只有三类**契约**（常量版本号、SOURCE_CATALOG 声明、ids 的冻结 ID 算法），不 import `transformers/` 与 `terminology.py`（`event_quality/README.md` 明文纪律）。

**复算清单**（`audit_cleaning.py: _audit`，审计 schema `cleaned_events_acceptance_audit/2.0.0`）：
- 结构：3 个 Arrow schema 逐列比对（含 metadata）、必填字段、Parquet 物理统计（行组/压缩/format_version）。
- 逐事件：raw_row_ref 正则解析回查 → 行号/下标/模块/表名一致；subject/hadm 与源 admission 一致；`source_row_id` 经 `SourceIdentityResolver` 独立重导一致；表↔event_kind 白名单（`EXPECTED_KINDS`）；time_policy/evidence_phase 与目录一致；quality flag 全在冻结枚举且无大小写碰撞；**有效可用时间不得早于事件时间**；处方订单时间必须恰有一条 poe_timeline 支撑血缘；lab 数值/文本/单位/旗标逐值重算比对；radiology/discharge 正文不得入 value_text。
- 逐拒绝行：身份回查 + 拒绝原因独立重演（`rejected_reason_not_reproduced`）。
- 全量对账：`AuditIndex`（DuckDB 落盘，`SET preserve_insertion_order=false`）四表 SQL——每个 event 源行必须"恰被接受或拒绝一次"（`source_row_classification_mismatch`）、support 行必须被引用（`supporting_source_row_unlinked`）、每源行事件数必须等于独立预期（`source_row_event_count_mismatch`）、event_id 全局唯一；再与 `source_reconciliation.json` 逐表逐字段比对 + encounter manifest 逐行重数。
- 上游等价：`_restore_raw_record` 把临床可读 JSONL 剥掉全部 `*_decoded` 字段与 `poe_timeline`、还原 `source_schema→schema` 后与原始 JSONL **逐行深比较**，证明解码层没改动任何原始内容。
- 抽样：`random.Random(20260812)` 固定种子 reservoir，每表 3 例。
- 门禁：`acceptance.can_start_normalization` = 无实质 issue + 哈希全对 + 合同全对 + 对账零差异；否则 workflow 阻断。

**有界资源**（`audit_storage.py`）：`JsonlRecordStore` 一次扫描建字节偏移表 + LRU(8) 行缓存，随机回查不复制整份 JSONL；`SourceIdentityResolver` 每次只缓存 2 个 admission 的 ID 映射；`AuditIndex` 5 万行批量落 DuckDB。审计可独立 CLI 运行（`audit_cleaning.py: main`）。

#### 3.4.2 audit_normalization —— "除 8 个归一化字段外事实不变"

`MUTABLE_EVENT_FIELDS` 显式列出 8 个可变字段；`audit` 用 `zip_longest` **按行序流式配对** cleaned 与 normalized（行数、event_id 逐行相等），其余 39 个不可变字段任一变化即 `immutable_event_field_changed`；`normalized_value_numeric/text` 必须等于原值（单位别名归一化不得改数值）；event_id 去重走**磁盘 SQLite**（`WITHOUT ROWID` 表，不常驻内存）。同时它**自带一份冻结副本**的 `REVIEWED_TEXT_MAPPINGS`/`UNIT_ALIASES`/`_source_code_is_usable`（字面重复而非 import），逐映射、逐事件重算期望归一化结果（`mapping_rule_application_mismatch` / `event_mapping_application_mismatch`），并核对 mappings ↔ inventory ↔ review queue 三者互为镜像、manifest 全部计数与 SHA-256。门禁 `can_publish_normalization` / `can_start_text_ner`。

#### 3.4.3 reproducibility —— 不同 batch size 两次运行字节级一致

`compare_runs` 对 canonical 与 replay 两棵树的 **8 个数据文件逐一算 SHA-256**（cleaning 5 + normalization 3），外加 6 项合同检查（两级 run_id、counts、output_sha256 各自相等）。`acceptance.reproducible` = 全部相等。

**为什么复跑 batch size 必须不同（5000 vs 777）**：Parquet 是字节格式，flush 边界不同即字节不同。cleaning 的 `BufferedParquetWriter` 行组固定 5000、事件严格按输入顺序写出、term_inventory 写前确定性排序——这些保证了"分块不变性"；而 normalization 的 `iter_batches(batch_size)` 是真正的读端分块变量。用不同的 batch size 重跑并要求**字节级一致**，等价于一个回归测试：任何"状态跨批泄漏、顺序依赖、批量边界条件"都会立刻导致 SHA-256 不匹配而被 `run_workflow` 的 `batch_size == replay_batch_size` 强制拒绝条款 + 复跑门禁抓住。若允许两者相同，该门禁就退化为"同一函数调两次"，失去证明力。

#### 3.4.4 regression —— 人工确认的隐私安全基线

`regression.py` 维护三批基线（sample_100 / random_1000_a / random_1000_b，fixture `tests/fixtures/event-cleaning-regression.json`，schema 1.1.0）。`capture_fixture` 只在人工确认后显式执行：记录输入字节/SHA-256、接受产物的 run manifest SHA-256、全套逻辑摘要（事件数、event_id 序列摘要、source_row_id 序列摘要、事件语义摘要、拒绝语义摘要），以及**确定性选出的代表性案例**（`_CaseSelector`：每个 source_table×event_kind 的首行 + 每表最大事件扇出行）——案例中患者身份与时间值只存 `presence + sha256 指纹`，不含明文 PHI。`verify_fixture` 有两种模式：对照已接受产物验证，或 `--rerun` 在临时目录真跑一遍 `run_cleaning` 再验证。任何摘要或案例指纹漂移即回归失败。

#### 3.4.5 review_normalization + consolidate_review —— 审阅包与跨批合并

- `generate_review_package` 先过**硬门禁**：重算 5 个数据文件实时 SHA-256 必须同时匹配 normalization manifest 与审计报告（防"审计后又被动过"）、workflow 三阶段全接受、审计零 issue、行数与 event_id 序列相等；再加 8 项 sanity 检查（mapped 必有 concept_id、unresolved 不得有、category_only 不得 mapped、数值文本不得变…）。通过后产出：决策表（`priority_rank` 0=REVIEWED_TEXT_RULE 文本规则必审 / 1=review queue 必审 / 2=高频抽样 / 3=可选）、`source_table×event_kind×normalization_status` 分层事件样本（`sha256(event_id)` 前 8 字节做确定性打分的堆抽样）、CSV/Parquet 决策表、中文 checklist，并**把 `review_app.py` 复制进审阅包**使其自包含。同参数+同输入哈希 → 同 review_run_id。
- `consolidate_review_packages` 以 **5 元冻结键 `entity_type + source_concept_id + normalized_source_label + source_unit + mapping_version`** 合并 ≥2 批审阅包：`_mapping_signature`（概念/状态/单位/规则，preferred_name 仅 casefold 比较）跨批不一致即 `CROSS_BATCH_MAPPING_CONFLICT` 直接失败；review_id 不一致同样失败。合并行汇总各批事件数并保留分批证据。随后 `select_pilot_rows` 按 7 个互斥类别（P0 文本规则 2、高频无代码药物 25、一般医嘱 15、无效 NDC 20、未解决单位 15、正确保持未解决的类别项 10、有效源代码映射 13 = **恰好 100 条**）依次、按总事件影响降序选择，且要求每条所选术语在它覆盖的所有批次里都有证据样本。产出裁决协议 `adjudication_protocol.md`（决策 taxonomy：accepted_mapped / accepted_unresolved / deterministic_correction / needs_external_evidence / source_defect，其中 needs_external_evidence 非终态）。

### 3.5 Viewer

- `event_viewer/app.py: CleaningViewerStore`：DuckDB 内存视图挂载最多 **9 个数据集**（cleaning 4 + normalization 3 + review 2），支持白名单列筛选/搜索/分页；`SourceJsonlReader` 预扫描字节偏移，按 `raw_row_ref` 随机回查源数组元素。只监听 127.0.0.1，`do_POST` 一律 405"只读服务不接受写请求"。
- `event_viewer/review_app.py: ReviewStore`：人工审阅窗口。决策列表/详情/样本来自不可变 Parquet；`save_annotation` 经 taxonomy 校验（合法性、必填评论、纠正必填概念或单位、accepted_mapped/accepted_unresolved 与当前状态一致性）后**只追加写** `normalization_review_annotations.jsonl`（`schema: normalization_review_annotation/1.1.0`，含 annotation_id/reviewer/UTC 时间戳，`flush + os.fsync`），历史全保留、latest 覆盖查询视图；**绝不修改任何 Parquet/CSV/上游产物**。多批主审阅时按 summary 里记录的各批源 JSONL 路径分别回查。

### 3.6 workflow：8 步固定顺序、门禁失败行为与原子发布

`workflow.py: run_workflow`（`WORKFLOW_VERSION = event-workflow/1.1.0`）固定执行：

1. **边界校验**：输入文件存在；输出目录已存在即 `EventWorkflowError("output already exists")`；`batch_size`、`replay_batch_size` 为正且**必须不相等**；`limit` 为正。
2. 在输出目录的**父目录**创建隐藏临时目录 `.{name}.tmp-xxxx`（`tempfile.mkdtemp`），全部中间产物先写这里。
3. `run_cleaning`（canonical batch size）。
4. **cleaning 审计门禁**：`audit_cleaning.audit` 不通过 `can_start_normalization` → 抛 `EventWorkflowError`（附 blocking_issue_codes）。
5. `run_normalization`（同 batch size）。
6. **normalization 审计门禁**：`can_publish_normalization` 不通过 → 抛错。
7. **复跑**：`_run_data_stages` 以 replay batch size 在 `.replay/` 隐藏子目录整体重跑 cleaning+normalization → `compare_runs` 字节级比较 → `reproducible` 不通过 → 抛错；通过则删除 `.replay/`。
8. **原子发布**：写 `quality/` 三份报告（`_published_audit_paths` 先把绝对输入路径改写为相对路径再落盘）→ 计算 quality 哈希 → 写 `workflow_manifest.json`（run_id = sha256(源哈希|raw哈希|cleaning run_id|normalization run_id|limit)[:24]，acceptance 四项全 true）→ **`os.replace(temporary, output_directory)`** 完成发布。

**门禁失败行为**：任何异常走 `_cleanup_without_masking` —— 尽力删除临时目录，但清理自身失败只 `add_note` 附注，**原始错误始终优先抛出**（不被清理失败掩盖）；正式输出目录永远不可能出现半成品（rename 前它根本不存在）。

**原子发布如何避免半成品目录**：全程写隐藏临时目录，最后一步是同文件系统上的**目录 rename**（`os.replace` 对目录是原子操作）。读者要么看不到输出目录，要么看到的就是已含全部产物与 manifest 的完整目录。`_remove_temporary` 还带护栏：拒绝删除"不在预期父目录下"或"不以 `.` 开头"的目录。

**resume（断点续跑）**：长跑批在 cleaning 完成后崩溃时，staging 目录（含完整 cleaning/）保留。`resume_workflow` 先 `_validate_resume_staging`：staging 必须与输出同父且同名前缀、输出不存在、`normalization/.replay/quality` 均未出现（即确实停在 cleaning 检查点）、manifest 合同四元组（schema 版本、cleaning_logic_version、目录版本、目录 SHA-256）与当前代码一致、源 JSONL 文件名/字节/SHA-256/limit 逐项匹配、5 个输出文件重算哈希逐一匹配。全部通过后从第 5 步继续；失败只清理 `normalization/.replay/quality` 三个未完成阶段，**绝不碰已验证的 cleaning 检查点**。

## 4. 数据契约

### 4.1 clinical-event schema 关键字段（47 列，`clinical_event/1.2.0`）

| 字段组 | 字段 | 语义 |
|---|---|---|
| 身份 | `event_id` `entity_id` `source_row_id` | `evt:/ent:/src:` + 24 hex；见 §3.2 步骤 3 |
| 归属 | `subject_id` `hadm_id` `encounter_id` | encounter 为 `ed:{stay_id}` / `icu:{stay_id}` / `hadm:{hadm_id}` |
| 事件 | `event_kind`（27 值枚举） `lifecycle_action` `status` `assertion` | assertion ∈ present/absent/possible/unknown/not_applicable |
| 时间 | `event_time` `source_available_time` `available_time` `recorded_time` `time_resolution_status` `time_precision` `time_policy_id` `time_resolution_reasons` | 见 §3.2 步骤 5；时间串允许 date 或 datetime |
| 证据 | `evidence_phase` `content_specificity` | source_event/post_hoc/administrative_end；entity_specific→not_applicable 五级 |
| 概念 | `source_concept_id` `concept_id` `preferred_name` `source_label` `entity_type` `normalization_status` `terminology_mapping_version` | cleaning 只写 source_concept_id/source_label/entity_type；归一化补齐其余 |
| 值 | `value_numeric` `value_text` `value_structured_json` `unit` `abnormal_flag` + 4 个 normalized_* | 数值/文本/结构化三通道；normalized 两个值字段为直通拷贝 |
| 溯源 | `source_module` `source_table` `source_array_index` `jsonl_line_number` `raw_row_ref` `source_action` `quality_flags` `supporting_source_row_ids` `supporting_raw_row_refs` | 回查指针 + supporting 血缘（两列表长度必须相等） |

约束：`cleaning_status` 恒为 `accepted`（rejected 走独立 schema）；`source_table` 匹配 `^(hosp|icu|ed|note)\.[a-z_]+$`；`source_module` 四值枚举；全部字段 required 且 `additionalProperties: false`。

### 4.2 各阶段输出文件

```text
event_pipeline_<BATCH>/
├── cleaning/                          # §3.2 的 6 个文件
│   ├── cleaned_events.parquet
│   ├── cleaning_rejected.parquet
│   ├── term_inventory.parquet
│   ├── encounter_manifest.parquet
│   ├── source_reconciliation.json
│   └── run_manifest.json
├── normalization/                     # §3.3 的 4 个文件
│   ├── normalized_events.parquet      # 与 cleaned 同 schema、同行序，仅 8 字段被写
│   ├── normalization_mappings.parquet # 术语四元组 → 概念/单位/规则/版本
│   ├── normalization_review_queue.parquet  # TERM_UNRESOLVED / UNIT_UNRESOLVED(+)
│   └── normalization_manifest.json
├── quality/                           # 两级审计 + 复现报告（路径已相对化）
│   ├── cleaned-events-acceptance-audit.json
│   ├── normalized-events-acceptance-audit.json
│   └── reproducibility-report.json
├── review/                            # 显式 review 后生成（§3.4.5，自包含 review_app.py）
└── workflow_manifest.json             # 仅在全部门禁通过后出现（§3.6）
```

## 5. 正确性与可靠性保障

**fail-closed 清单**（任一命中即抛错/拒绝，绝不降级继续）：
- 输入：未知 schema、缺 ID、模块非对象、**未登记表**、**缺必需表**、表非数组、JSONL 空行/解析失败、POE 时间线行数/ID/动作/时间不符。
- 事件：JSON Schema 任一错误、source/supporting 行不存在、血缘长度不等、mapped 无 concept_id、lab 无概念、time_policy 不匹配、有效可用早于事件时间、时间反转未解释或无中生有的解释标记、下界钳制值不符、未知质量旗标、event_id 重复。
- 归一化：cleaned 已带归一化值、事件术语不在 inventory、映射表与应用结果不一致、状态缺失、输出目录已存在。
- 发布：两级审计 `can_*` 为假、复跑任一 SHA-256/合同不等、review 硬门禁失败、跨批映射冲突、pilot 类别名额不足。

**双层审计**：cleaning 审计证明"事件忠实于源"，normalization 审计证明"归一化只动了该动的 8 个字段"；两者都**独立重算**而非复用生产代码（audit_normalization 甚至字面复制术语表为冻结副本，`terminology.py` 若被改动而审计副本未同步，比对立刻失败）。

**可复现门禁**：不同 batch size（5000/777）双跑 + 8 文件 SHA-256 + 6 项合同逐一相等（§3.4.3）。所有 run_id、目录哈希、输入哈希层层写入 manifest，任何一环漂移都可定位。

**防覆盖**：cleaning / normalization / review / workflow 四级输出目录已存在即拒绝重跑；`resume` 校验 staging 必须精确停在 cleaning 检查点；`_remove_temporary` 拒绝删除非预期目录；review UI 只追加 JSONL，天然幂等可审计。

**人工回归基线**：三批人工确认产物固化为指纹化 fixture，CI 可反复验证（含 `--rerun` 真跑模式）。

## 6. 使用方法

统一入口 `python -m data_pipeline.event_pipeline`。完整正式批次**必须用 `run`**；单阶段子命令仅供排查。

### run —— 一条命令完成全部门禁

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline run `
  data\validation\NEW-BATCH-clinical-readable.jsonl `
  --raw-source-jsonl data\validation\NEW-BATCH-raw.jsonl `
  --output-dir data\derived\event_pipeline_NEW_BATCH
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `source_jsonl`（位置） | — | 临床可读（或 raw schema）admission JSONL |
| `--raw-source-jsonl` | 必填 | 原始 JSONL，供上游等价审计 |
| `--output-dir` | 必填 | 正式输出目录（不得已存在） |
| `--batch-size` | 5000 | 正式批大小 |
| `--replay-batch-size` | 777 | 复跑批大小，**必须与上面不同** |
| `--limit` | 无 | 只处理前 N 个 admission（冒烟用） |
| `--work-dir` | 系统临时区 | 审计 DuckDB 落盘工作目录（大批次建议指到大盘） |

### resume —— 从已完成的 cleaning 检查点续跑

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline resume `
  data\derived\.event_pipeline_NEW_BATCH.tmp-ab12cd `
  data\validation\NEW-BATCH-clinical-readable.jsonl `
  --raw-source-jsonl data\validation\NEW-BATCH-raw.jsonl `
  --output-dir data\derived\event_pipeline_NEW_BATCH
```

（staging 目录名必须是 `.{输出名}.tmp-` 前缀且与输出同父；参数同 run。）

### clean / normalize —— 单阶段排查

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline clean INPUT.jsonl `
  --output-dir OUTPUT\cleaning --batch-size 5000 --limit 100

.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline normalize `
  OUTPUT\cleaning\cleaned_events.parquet `
  OUTPUT\cleaning\term_inventory.parquet `
  --output-dir OUTPUT\normalization
```

### view —— 只读浏览器

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline view `
  data\derived\event_pipeline_NEW_BATCH `
  --source-jsonl data\validation\NEW-BATCH-clinical-readable.jsonl `
  --port 8765            # --no-browser 不自动开页；--check 只验目录打印摘要
```

（接受单独 cleaning 目录或完整 workflow 目录；后者含 normalization/review 共 9 个数据集。）

### review / review-ui / review-master —— 人工审阅闭环

```powershell
# 生成审阅包（默认输出到 <event_directory>\review）
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline review `
  data\derived\event_pipeline_NEW_BATCH `
  --samples-per-stratum 3 --top-mappings-per-entity 10

# 打开单批审阅窗口（自动定位 review/ 子目录）
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline review-ui `
  data\derived\event_pipeline_NEW_BATCH --port 8766

# 跨批合并 + 100 条试审（至少两批）
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline review-master `
  data\test_1000_0812\event_pipeline_output `
  data\test_1000_0812_2\event_pipeline_output `
  --output-dir data\derived\normalization_review_master
```

审阅包自带 `review_app.py`，也可直接 `python review\review_app.py` 运行。人工决定只追加进 `normalization_review_annotations.jsonl`。

### regression —— 人工回归基线

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline regression verify
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline regression verify --rerun --batch random_1000_a
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline regression capture --batch sample_100   # 仅人工确认后执行
```

### 单元测试

```powershell
.\.venv\Scripts\python.exe -m unittest -v `
  tests.test_event_pipeline tests.test_event_source_catalog `
  tests.test_event_terminology tests.test_event_audit_storage `
  tests.test_event_cleaning_regression tests.test_event_normalization_review `
  tests.test_event_pipeline_viewer tests.test_event_review_app `
  tests.test_event_review_consolidation
```

（9 个测试文件分别覆盖 workflow 全链路、目录合同、术语规则、审计存储、回归基线、审阅包生成、查看器、审阅窗口、跨批合并；均为 `unittest.TestCase`，也可用 pytest 运行，如 `E:\Anaconda3\python.exe -m pytest tests/test_event_pipeline.py -q`。）

## 7. 设计取舍与已知限制

- **封闭世界登记**：任何新表必须先登记 `SOURCE_CATALOG`（含角色、键、时间策略、理由），否则输入直接被拒。换来的是全量可对账，代价是接入新源需改合同并升 `SOURCE_CATALOG_VERSION`/SHA-256。
- **确定性优先于召回**：归一化宁可 `unresolved` 进 review queue 也不猜（仅 2 条人工复核过的文本同义词）；订单时间宁可为空也不用 prescription.starttime 顶替（防泄漏）。大量 unresolved 是设计意图，由人工审阅闭环消化。
- **时间不猜测**：缺时间就 null + `AVAILABLE_TIME_UNKNOWN`，绝不填充；这使部分事件 `time_resolution_status` 长期为 partially_resolved/unresolved。
- **休眠合同**：schema 里 `administrative_group_recorded`、`clinical_datetime_recorded`、`medication_ingredient_administered` 等 event_kind 当前没有任何 active 源产出（对应表分别是 context/support 角色，transformer 已实现待接线）；`icu.datetimeevents` 显式搁置。`icu.chartevents`、`hosp.omr` 在上游就被排除（`UPSTREAM_EXCLUDED_SOURCES`）。
- **`--limit` 改变输出内容**：limit 参与 cleaning run_id，limit 与非 limit 产物不可互换；审计上游等价要求 raw 与临床可读两份 JSONL 行集合一致。
- **审计成本**：cleaning 审计对每个事件做 raw_row_ref 回查与独立重算，全量 cohort 下 CPU/IO 可观（已用字节偏移索引、DuckDB 落盘、SQLite 磁盘去重控制内存），大批次建议 `--work-dir` 指向大容量临时盘。
- **review 包与 workflow 解耦**：`review` 是 workflow 之后的显式步骤，审阅结论（追加式 JSONL）目前不自动回写 `REVIEWED_TEXT_MAPPINGS`；确定性纠正必须回规则层改代码、升 `MAPPING_VERSION` 并重跑，保证可复现链条不断。
- **跨批合并强一致**：同一冻结键在不同批次语义不一致即整体失败（不自动仲裁），要求各批使用同一冻结术语版本跑归一化。
- **依赖重量**：pyarrow + duckdb + jsonschema 为硬依赖；viewer/review-ui 仅监听 127.0.0.1，不适合多用户远程使用。
