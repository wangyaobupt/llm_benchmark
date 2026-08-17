# 数据层处理模式（代码级说明）

> 依据 `data_pipeline/` 实际代码，说明数据层每一步的处理模式与关键实现。
> 定位：实现细节说明；配合 [`raw-archive-cleaning-standardization.md`](raw-archive-cleaning-standardization.md)（分层设计）与 [`../reports/data-layer-completeness-audit.md`](../reports/data-layer-completeness-audit.md)（完整性审计）阅读。
> 核心代码边界：`data_pipeline/event_pipeline/`（清洗/标准化/审计/编排），上游 `mimic_raw_archive/`、`clean_clinical_archive/`，下游 `event_aggregation/`。

## 0. 模块与依赖方向

```text
event_contracts           契约（Arrow/JSON schema、状态枚举）
      ↑
event_cleaning → event_normalization    清洗 → 标准化
      ↑                ↑
      └── event_quality                 独立审计（不自证）
                ↑
            workflow                    唯一编排入口
```

依赖严格单向；`event_cleaning` 不依赖 normalization；`event_quality` 不调用 transformer / 归一化规则来证明实现自身正确。

分层（自上游到下游）：

```text
mimic_raw_archive   ① 原始归档     只保留原始字段，不改写源记录
clean_clinical_archive  字典解码 + POE 解析
event_cleaning      ② 清洗层       可用性 / 质量 / 文本结构
event_normalization ③ 标准化层     术语 / 单位 / 代码映射
event_quality       ④ 独立审计     验收 + 回归 + 复现
event_aggregation   ⑤ 无损聚合     回连原文 + 源行血缘
```

---

## 1. 契约层：单事件 `ClinicalEvent`

`event_contracts/schemas/clinical-event.schema.json` 定义一条事件 = **41 个 required 字段**，`additionalProperties:false`（键不允许漂移）。字段按语义分组：

| 组 | 字段 | 说明 |
|---|---|---|
| 身份 | `event_id`、`entity_id`、`source_row_id`、`subject_id`、`hadm_id`、`encounter_id` | id 用固定格式：`evt:[0-9a-f]{24}` / `ent:…` / `src:…` |
| 事件语义 | `event_kind`（27 枚举）、`assertion`、`lifecycle_action`、`status` | `assertion` ∈ present/absent/possible/unknown/not_applicable |
| **时间四元组** | `event_time`、`source_available_time`、`available_time`、`recorded_time` | 显式区分「发生 / 源可见 / 有效可见 / 记录」 |
| 时间状态 | `time_resolution_status`、`time_precision`、`time_policy_id`、`time_resolution_reasons` | resolved/partially_resolved/unresolved；subsecond/second/date/unknown |
| 后验标记 | `evidence_phase` | `source_event` / `post_hoc` / `administrative_end` |
| 概念 | `source_concept_id`、`concept_id`、`preferred_name`、`source_label`、`entity_type`、`normalization_status` | `normalization_status` ∈ mapped/unresolved/not_applicable |
| 值 | `value_numeric`/`value_text`/`value_structured_json`/`unit`/`abnormal_flag` + `normalized_value_*`/`normalized_unit`/`unit_normalization_status` | 原始值与归一化值并存 |
| 溯源 | `source_module`/`source_table`/`source_array_index`/`jsonl_line_number`/`raw_row_ref`/`source_action` | `source_table` 形如 `hosp.labevents` |
| 质量 | `quality_flags`（28 枚举）、`supporting_source_row_ids`、`supporting_raw_row_refs` | 如 `AVAILABLE_BEFORE_EVENT_TIME`、`UNRESOLVED_POE_ID`、`RELATION_CYCLE` |

`event_kind` 覆盖症状/生命体征/医嘱/检验/给药/转科/手术/文书等 27 种事件；`evidence_phase` 决定该事件能否进前瞻题干。

---

## 2. 清洗层：`SourceSpec` + `Transformer` 模式

### 2.1 封闭式 33 表目录（`source_catalog.py`）

每张输入表登记为一个 `SourceSpec`（`event_cleaning/models.py` 的 frozen dataclass）：

```python
@dataclass(frozen=True)
class SourceSpec:
    module, table, origin                 # 模块 / 表名 / raw|derived
    role: SourceRole                      # event | support | context | excluded
    fact_owner: str | None
    supports: tuple[str, ...]
    identity_strategy: IdentityStrategy   # native_key | composite_key | canonical_row_hash_with_occurrence
    native_key_fields: tuple[str, ...]
    time_policy: str                      # 指向 TIME_POLICIES 的 policy_id
    evidence_phase: str | None
    transformer_name: str | None
    inclusion_reason: str | None
    exclusion_reason: str | None
    required: bool = True
```

33 张表分三类：**21 事实源**（生成事件）、**6 support**（只提供原生键证据、须关联到事实源）、**6 context**（不重复生成事实）。`source_reconciliation.json` 逐表对账角色；任一行未分类 / support 未关联 / 未登记表 / derived 计数漂移 → 阻断 normalization。

### 2.2 Transformer 签名：一进多出

`transformers/registry.py` 一行收集全部实现：

```python
TRANSFORMERS = {name: v for name, v in globals().items()
                if name.startswith("transform_") and callable(v)}
```

统一签名（`models.py`）：

```python
Transformer = Callable[[SourceRow, AdmissionContext], list[dict]]
```

**输入一条源行 + 上下文 → 输出 0..n 条事件 dict**。按临床域拆成 ED / laboratory / orders / medications / diagnoses_procedures / icu / notes 等模块，共 26 个 `transform_*`（`transform_labevent`、`transform_poe`、`transform_emar`、`transform_transfer`…）。

### 2.3 身份策略与溯源

```python
IdentityStrategy = Literal["native_key", "composite_key", "canonical_row_hash_with_occurrence"]
```

优先原生主键 → 无唯一键时用「行内容哈希 + 重复出现序号」。不删除原始重复行，只标记 `exact_duplicate_group`。溯源引用格式固定：

```python
raw_row_ref = f"{input_name}#L{jsonl_line_number}/{module}.{table}[{source_array_index}]"
```

### 2.4 时间语义：每表一条 `TimePolicy`

`TIME_POLICIES`（`source_catalog.py`）对每张表声明三个时间从哪来、缺失怎么办。示例：

```python
# 检验 / eMAR / 放射 / ICU 输出：可见时间 = max(发生, 存库)
TimePolicy("chart_store_v2",
    "charttime", "available=max(event_time,storetime)", "storetime",
    "keep_missing_store_time_null_and_flag; explain_and_clamp_inversion")

# POE 医嘱时间线：缺订单时间即拒绝
TimePolicy("poe_timeline_v1",
    "event_time", "event_time", "null",
    "reject_missing_order_time_when_semantics_require_it")

# 出院 ICD 诊断：后验、无时间
TimePolicy("post_hoc_no_time_v1",
    "null", "null", "null", "keep_null_and_mark_post_hoc")

# ICU 区间事件：完成前不可见
TimePolicy("icu_interval_completion_v2",
    "starttime", "available=max(event_time,endtime,storetime)", "storetime",
    "use_source_completion_bound")
```

**模式**：时间绝不静默填补；缺失统一 `flag + null`；可用性早于发生则 clamp 并记入 `time_resolution_reasons`。

---

## 3. 标准化层：冻结映射 + 一致性门禁 + 原子发布

### 3.1 冻结映射（`terminology.py`，零 LLM）

```python
MAPPING_VERSION = "event-terminology/1.1.0"
REVIEWED_TEXT_MAPPINGS = {("symptom", "chest pain"): ("symptom:chest_pain", "Chest pain", "reviewed-synonym"), ...}
UNIT_ALIASES = { "mm hg": "mmHg", "mg/dl": "mg/dL", "l": "L", ... }   # ~50 条
```

`resolve_term()` 判定链：**source-code 优先**（NDC 须 11 位、GSN 须 6 位，否则 `invalid-source-code` → unresolved）→ 人工审核文本映射 → 否则 `unresolved`。**不猜测、不兜底**。

### 3.2 关键门禁：映射表与事件应用必须一致

`event_normalization/pipeline.py` 先在 `term_inventory` 上**预计算**每类术语的映射（键 = `entity_type + source_concept_id + normalized_source_label + unit`），再逐事件应用并校验：

```python
if (normalized["concept_id"] != mapping["concept_id"]
    or normalized["normalization_status"] != mapping["normalization_status"]
    or normalized["normalized_unit"] != mapping["normalized_unit"]
    or normalized["unit_normalization_status"] != mapping["unit_normalization_status"]
    or mapping_rule != mapping["mapping_rule"]):
    raise EventPipelineError("MAPPING_APPLICATION_MISMATCH", event_id)
```

即「映射表是权威，事件层算出不一样就失败」，保证规则与应用永不漂移。`normalization_status` 只允许 `mapped/unresolved/not_applicable`；`unresolved` 不算错，但不得进入要求唯一答案的题目。

### 3.3 原子发布

```python
temporary = tempfile.mkdtemp(prefix=f".{output_directory.name}.tmp-", ...)
... 写三份 parquet + manifest ...
os.replace(temporary, output_directory)   # 全通过才原子改名
# 异常：关 writer、remove_temporary、raise —— 不留半成品
```

输出：`normalized_events.parquet` / `normalization_mappings.parquet` / `normalization_review_queue.parquet` + `normalization_manifest.json`（含 run_id、输入 SHA-256、计数、状态分布、输出 SHA-256）。

---

## 4. 编排层：`workflow.py` 固定顺序 + fail-closed + 复跑

固定 8 步（`event_pipeline/README.md`）：

1. 校验输入文件与输出边界；
2. cleaning / 事件化；
3. cleaning 独立验收；
4. 只有 cleaning 通过才执行 normalization；
5. normalization 独立验收；
6. 用另一 batch size（默认 5000 vs 777）复跑 cleaning + normalization；
7. 比较所有数据文件 SHA-256、run_id、计数；
8. 全部通过后 `os.replace` 原子发布正式目录。

`workflow_manifest.json` 只在两层审计 + 复跑全过后才出现；任一步失败返回非零、不留正式输出目录。

产物目录：

```text
event_pipeline_<BATCH>/
├── cleaning/     cleaned_events.parquet / cleaning_rejected.parquet /
│                 term_inventory.parquet / encounter_manifest.parquet /
│                 source_reconciliation.json / run_manifest.json
├── normalization/ normalized_events.parquet / normalization_mappings.parquet /
│                 normalization_review_queue.parquet / normalization_manifest.json
├── quality/      cleaned-events-acceptance-audit.json /
│                 normalized-events-acceptance-audit.json / reproducibility-report.json
├── review/       （显式执行 review 后生成）
└── workflow_manifest.json
```

---

## 5. 质量层：独立审计（不调用 transformer 自证）

`event_quality/` 独立全量复算，不 import transformer / 归一化规则：

- **cleaning audit**：复算 33 表角色、raw/derived 计数、supporting lineage、encounter manifest、身份、时间、逐表对账；
- **normalization audit**：验证**除 8 个归一化字段外所有事件事实不变**（标准化只填概念/单位、不改事实）；
- **regression.py**：回归基线需人工确认后才允许 `regression capture`；
- **reproducibility.py**：两次运行独立计算 SHA-256 比对。

---

## 6. 审阅层：只读 + 追加式决定

- `review`：重算当前 cleaning/normalization 哈希，按 `source_table × event_kind × normalization_status` 确定性分层抽样，生成审阅包（只读输入、独立输出）。
- `review-ui`：本地窗口（127.0.0.1），人工决定**追加写** `normalization_review_annotations.jsonl`，不改 Parquet/CSV。
- `review-master`：跨批按冻结键（`entity_type + source_concept_id + normalized_source_label + source_unit + mapping_version`）去重，建立固定 100 条试审（七类互斥、按总事件影响降序）。
- 任何确定性纠正**回规则层改代码重跑**，不直接改归一化 Parquet。

---

## 7. 上游归档 / 下游聚合

- **`mimic_raw_archive/`**：按住院聚合 HOSP/ED/ICU/Note 四模块，产出原始 JSONL + 字段来源清单 + manifest，不改写源记录（108,833 次住院、46,062 患者、218 分片、32 表）。
- **`clean_clinical_archive/`**：字典解码（`d_labitems`/`d_icd_*`/`d_hcpcs` 等大字典）与 POE 解析，保留医嘱生命周期与原生连接。
- **`event_aggregation/`**：把标准化事件回连完整原文 + 源行血缘，产出 `processed_events` / `raw_source_records` / `traceable_events` 三份 Parquet（1,241,918 源记录、757,036 处理后事件、43,551 自由文本源记录），作为下游唯一正文入口。

---

## 附：关键代码位置索引

| 层 | 文件 |
|---|---|
| 契约 | `data_pipeline/event_pipeline/event_contracts/schemas/clinical-event.schema.json`、`event_contracts/schemas.py`、`event_contracts/statuses.py` |
| 清洗模型 | `event_pipeline/event_cleaning/models.py`（SourceSpec/TimePolicy/SourceRow/AdmissionContext） |
| 33 表目录 | `event_pipeline/event_cleaning/source_catalog.py`（SOURCE_CATALOG + TIME_POLICIES） |
| transformer | `event_pipeline/event_cleaning/transformers/*.py`、`transformers/registry.py` |
| 清洗主流程 | `event_pipeline/event_cleaning/pipeline.py`、`event_cleaning/validation.py` |
| 身份/时间 | `event_pipeline/event_cleaning/ids.py`、`event_cleaning/time_resolver.py` |
| 标准化规则 | `event_pipeline/event_normalization/terminology.py` |
| 标准化主流程 | `event_pipeline/event_normalization/pipeline.py`、`event_normalization/io.py` |
| 编排 | `event_pipeline/workflow.py`、`event_pipeline/__main__.py` |
| 审计/回归/复现 | `event_pipeline/event_quality/{audit_cleaning,audit_normalization,regression,reproducibility}.py` |
| 审阅 | `event_pipeline/event_quality/{review_normalization,consolidate_review}.py`、`event_pipeline/event_viewer/review_app.py` |
| 上游归档 | `data_pipeline/mimic_raw_archive/{extractor,cohort,selection,schema,manifest}.py` |
| 字典/POE | `data_pipeline/clean_clinical_archive/{decoder,pipeline}.py`、`clean_clinical_archive/poe/parser.py` |
| 聚合 | `data_pipeline/event_aggregation/pipeline.py` |
