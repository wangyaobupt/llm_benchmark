# Benchmark 检查选择金标准重建实施计划 v3.1

> 版本：v3.1  
> 日期：2026-08-19  
> 状态：部分落地，合同未冻结（不是从零待执行）  
> 目标：在不复用旧 phenotype / 旧 V2 金标准语义的前提下，基于 MIMIC-IV 重建可审计、可复现、时间不泄漏的 investigation selection benchmark。  
> 本版依据：v3 原计划 + 对真实聚合样本 `hadm-26691544-aggregated-complete.json` 的压力测试结果。  
> 仓库落地对照：根目录 [`BenchMark-进展梳理.md`](../../BenchMark-进展梳理.md)。不另起 `evaluation_pipeline/contracts|time|grouping` 平行树；CLI 对到现有 `data_pipeline/investigation_selection` 与 `evaluation_pipeline`。

---

# 0. 执行结论

本轮不允许直接进入 TF-IDF、Lift、规则挖掘或题目生成。

必须按以下顺序执行：

```text
W0 旧链失效
↓
W1 核心研究合同冻结
↓
W2 encounter clock + event grouping schema
├─ W3a safe snapshot
├─ W3b discharge NER（并行，不阻塞）
└─ W4 investigation episode + candidate catalog
      ↓
    catalog-lock
      ↓
W5 coronary decision corpus
      ↓
1000 例 integration audit
      ↓
corpus freeze
├─ W6a retrieval method check
└─ W7a statistical method check
      ↓
W8 multi-diagnosis expansion
      ↓
新增 subjects exposure/split 扩展
      ↓
重新 W2–W5
      ↓
W6b / W7b expanded formal refit + validation
      ↓
W9 question candidates + clinical review
      ↓
W10 one-shot final test + release
```

任何阶段未通过对应 gate，不得向下游推进。

科学顺序不变。执行方式改为：**以现有模块为底做合同对齐**，不要按第 20 节目录从零重写。仓库已有而尚未过关的事实：

| 工作包 | 仓库现状 | 本版仍要求 |
|---|---|---|
| W0 | legacy manifest、legacy gate、phenotype formal 拒绝已存在 | 文档与语义拒绝测试与 P0 对齐；旧 134 题不得送审 |
| W1 | `protocol.yaml` 可校验，但是 draft | 冻 `conditional_order_choice`、`evidence_window_basis`、availability policy；只锁 protocol-core |
| W2 | `encounter_clock.py` / `source_grouping.py` 有合成测试；event 仍是 `1.2.0` | grouping 改 `chain_root_poe_id` + 真实 `specimen_id`；先做派生投影，不先重跑 27M 事件 |
| W3a | `evaluation_pipeline.snapshot` 已有字段白名单 | 补 recency clock；`event_time < index_time`；禁读 future POE metadata |
| W3b | text_ner_v2 工程在跑，人工双标 = 0 | 保持并行；不得进 formal condition |
| W4 | `episodes.py` 会丢掉 cancel/inactive | 保留历史 create；建 eligibility catalog |
| W5 / audit | 无真实 corpus | 用现成 1,000 例聚合做 6 张审计表 |
| W6 / W7 | retrieval / ranking 原语已写 | 只当离线函数；corpus freeze 前不算方法验证 |

---

# 1. 本版必须解决的 P0 问题

## P0-1：明确 order task 的研究构念

本版主任务固定为：

```yaml
decision_semantics: conditional_order_choice
```

含义：

> 已知在该时点发生了一次符合 eligibility 的 investigation ordering action，预测同一冻结 target 定义下观察到的 investigation candidate / candidate set。

本版**不允许**将该任务描述为：

> “预测医生下一步是否会开检查”。

因为 order decision node 本身由 order action 触发。

如未来要研究真正的 prospective decision opportunity，必须另开任务：

```yaml
decision_semantics: prospective_decision_opportunity
```

且其 decision node 必须与 target 独立产生。

---

## P0-2：safe snapshot 必须字段级 fail-closed

任何 formal query/snapshot 不允许直接读取完整 event payload。

特别禁止：

- `raw_record_json`
- `clinical_readable_record_json`
- future-derived POE relation
- successor / predecessor chain metadata
- chain completion
- retrospective final status
- discharge / post-hoc diagnosis
- target-derived字段

formal snapshot 只能读取冻结后的安全字段投影。

---

## P0-3：POE 生命周期按 chain，不按 poe_id

定义：

```text
poe_id
= action-level row identifier

poe_chain_root_id
= lifecycle-level identifier

investigation_episode_id
= benchmark-level investigation episode identifier
```

POE episode grouping 必须按：

```text
chain_root_poe_id
```

不能按单个 `poe_id`。

---

## P0-4：available-time 与 event-time 分开

任何正式 evidence 必须同时满足：

```text
event_time < index_time
AND
available_time <= index_time
```

对“最近信息窗口”的下界，不再统一使用 event_time。

新增：

```yaml
evidence_window_basis
```

用于明确每类 evidence 的 recency clock。

---

## P0-5：clinical_ordered 不是 investigation track

`clinical_ordered` 仅代表 POE source container。

是否进入 investigation benchmark 必须经过冻结：

```text
investigation-order-eligibility.yaml
```

不能依据 `event_kind == clinical_ordered` 直接入选。

---

## P0-6：FDR family 与 joint support 分离

FDR 前只允许：

- condition 边际 support
- candidate 边际 support
- 结构性合法性过滤

不得按：

- joint support
- lift
- p-value
- direction

预筛选 hypothesis family。

`joint >= 10` 改为 FDR 后 release gate。

---

## P0-7：W8 后必须重新跑正式 W6/W7

多诊断扩展会改变：

- corpus
- vocabulary
- IDF
- candidate frequency
- FDR family
- rule counts
- validation universe

因此 W8 后不能直接进入 W9。

必须：

```text
W8
→ expanded W5
→ W6b
→ W7b
→ W9
```

---

# 2. 真实样本对合同的直接影响

真实样本：

```text
hadm_id = 26691544
event_count = 13,782
source_record_count = 27,985
```

该样本暴露出以下必须修订的问题：

1. `clinical_ordered` 中包含大量 Medication / General Care / IV therapy 等非检查类 order。
2. POE lifecycle 会横跨多个 `poe_id`。
3. `status=Inactive` 不能解释为“该历史 order 从未发生”。
4. event payload 中可能已经包含未来 lifecycle 信息。
5. Lab 的 `charttime` 与 `storetime` 不同，医生可见时间应以结果 availability 为准。
6. ED triage / vitals 存在 event_time 或来源事实，但 `available_time` 可能为空。
7. Lab raw record 中存在 `specimen_id`，但当前 event 顶层 contract 尚未正式暴露 grouping 字段。
8. Imaging order 可能只有 modality/subtype 粒度，不能反向臆造 body site / exact exam。

因此本版优先修复：

```text
safe snapshot
+
POE lifecycle
+
evidence clock
+
candidate eligibility
```

之后才允许统计。

---

# 3. 锁文件设计

原单一 protocol lock 改为三层。

## 3.1 protocol-core-lock.json

由 W1 生成。

包含：

```yaml
decision_semantics
decision_node_policy
query_window
target_window
burst_window
evidence_window_basis
availability_policy
split_policy
exposure_policy
FDR_family_policy
support_thresholds
bootstrap_policy
metric_definitions
reason_codes_version
```

不包含：

- candidate catalog hash
- panel definition hash
- final feature vocabulary hash

因为这些要到 W4/W5 后才能冻结。

---

## 3.2 catalog-lock.json

由 W4 生成。

绑定：

```yaml
investigation_order_eligibility_hash
candidate_catalog_hash
panel_definitions_hash
candidate_specificity_policy_hash
normalization_mapping_hash
```

---

## 3.3 run-lock.json

由 W5 生成。

绑定：

```yaml
protocol_core_lock_hash
catalog_lock_hash
event_schema_hash
snapshot_schema_hash
split_manifest_hash
exposure_registry_hash
input_manifest_hash
decision_schema_hash
```

W6–W10 只能读取匹配的 run-lock。

---

# 4. W0 — 旧 V2 / 旧语义彻底失效

## 目标

确保任何旧题、旧 rule、旧 phenotype、旧 order 语义都无法进入新链。

## 必须修改

### 4.1 失效对象

全部标记 invalid：

- 旧 V2 134 candidate questions
- 旧 formal rules
- 旧 phenotype features
- discharge ICD 作为 prospective condition/evidence
- full-hospital target window
- post-hoc sidecar
- `clinical_ordered == investigation`
- `poe_id == order episode`
- `Inactive == invalid historical order`
- `event_time < index 即可见`

### 4.2 新增 manifest

建议新增：

```text
artifacts/legacy-invalidation-manifest.json
```

内容至少：

```json
{
  "legacy_v2_questions": "invalid",
  "legacy_rules": "invalid",
  "legacy_phenotype": "invalid",
  "invalidated_semantics": [
    "clinical_ordered_is_investigation",
    "poe_id_is_complete_order_episode",
    "terminal_inactive_means_order_never_happened",
    "event_time_only_visibility"
  ]
}
```

## 执行建议

代码搜索：

```powershell
rg "phenotype|clinical_ordered|poe_id|Inactive|event_time" data_pipeline evaluation_pipeline tests versions
```

任何旧入口改为 fail-closed：

```python
raise LegacyContractError(...)
```

## 新增测试

```text
test_legacy_v2_cannot_enter_release_chain
test_legacy_phenotype_import_rejected
test_legacy_clinical_order_semantics_rejected
test_legacy_poe_episode_semantics_rejected
```

## 输出

```text
legacy-invalidation-manifest.json
legacy-code-reference-audit.tsv
```

## Gate W0

必须全部满足：

- old gold count = 0
- old candidate cannot be loaded by new pipeline
- old phenotype package not referenced
- invalid semantics documented

---

# 5. W1 — 核心研究合同冻结

## 目标

冻结 task、decision node、窗口、visibility、split、FDR、metric semantics。

---

## 5.1 决策任务

主任务：

```yaml
decision_semantics: conditional_order_choice
```

### imaging_order

```yaml
index_time: investigation_order_episode.initial_order_time
target_burst_minutes: 15
query_lookback_hours: 4
```

target：

> 与 index action 属于相同冻结 comparison class、且位于 target burst 内的 observed investigation order candidate set。

### clinical_order

只允许通过 investigation eligibility catalog 的 order。

### generic_lab_order

只保留 MIMIC 能真实支持的 generic Lab ordering semantics。

禁止从 labevents + 时间邻近关系虚构 specific lab order。

### lab_result_proxy

固定为 result-proxy task。

例如主分析：

```yaml
query_window_hours: 4
target_window_hours: 24
```

---

## 5.2 evidence visibility

正式规则：

```text
event_time < index_time
AND
available_time <= index_time
AND
evidence_phase not in {post_hoc, administrative_end}
AND
normalization / source policy permits
AND
split policy permits
```

unknown time 默认 reject。

---

## 5.3 recency clock

新增配置：

```yaml
evidence_window_basis:
  laboratory_resulted: available_time
  imaging_reported: available_time
  microbiology_resulted: available_time
  vital_measured: event_time
  imaging_ordered: available_time
  laboratory_ordered: available_time
  clinical_ordered: available_time
```

正式 recency 条件：

```text
recency_clock(event) >= query_start
```

注意：

```text
result-like facts
```

允许：

```text
event_time < query_start
但 available_time >= query_start
```

只要：

```text
available_time <= index_time
```

---

## 5.4 availability policy

主分析建议：

```yaml
availability_policy:
  resolved: allow
  chart_store_v2: allow
  poe_timeline_v1: allow
  triage_no_time_v1: reject
  chart_only_v1: reject_main
```

若后续 source audit 证明 charttime 可作为保守 proxy，另建 sensitivity：

```yaml
sensitivity:
  chart_only_v1:
    available_time_proxy: event_time
    label: charttime_proxy
```

不得静默修改主分析。

---

## 5.5 主/敏感性窗口

主分析：

```yaml
query_hours: 4
target_hours: 24
burst_minutes: 15
```

敏感性：

```yaml
query_hours: [2, 4, 8]
target_hours: [12, 24, 48]
burst_minutes: [5, 15, 30]
```

---

## 5.6 tie policy

固定：

```yaml
multilabel_when_tied: true
mcq_requires_unique_statistical_advantage: true
```

无唯一答案：

```text
REFUSE_UNIQUE_ANSWER
```

不得为了生成 MCQ 人工打破 tie。

---

## 5.7 split / exposure

规则：

- subject-level split
- 目标比例 70/15/15
- 旧 development subject 保持 development
- 任何已接触旧 validation/final 的 subject 只能 audit-only
- 只有 `previous_exposure=none` 可进入新 validation/final
- final subject 不参与：
  - vocabulary
  - IDF
  - catalog
  - threshold
  - prompt
  - ranking method
  - rule selection

---

## 5.8 FDR policy

预过滤：

```yaml
condition_subjects_min: 50
candidate_subjects_min: 30
```

完整 family 建立后：

```yaml
BH_q_max: 0.05
```

FDR 后：

```yaml
joint_subjects_min: 10
bootstrap_subject_iterations: 1000
direction_stability_min: 0.80
validation_support_min: 20
```

validation support < 20：

```text
VALIDATION_INCONCLUSIVE
```

---

## 5.9 metric definitions

W1 就要冻结：

- Recall@k
- MRR
- NDCG
- macro average
- head/mid/tail binning
- rare-stable definition
- JSD candidate universe
- tie sorting
- zero-target handling

示例：

```yaml
frequency_bins:
  head: prevalence >= 0.20
  mid: 0.02 <= prevalence < 0.20
  tail: prevalence < 0.02
```

阈值可在执行前调整，但必须在正式结果前冻结。

---

## 输出

```text
protocol-core.yaml
protocol-core-lock.json
exposure-registry.parquet
split-policy.yaml
reason-codes.yaml
```

## 测试

```text
test_result_recency_uses_available_time
test_occurrence_recency_uses_event_time
test_unknown_available_time_rejected
test_joint_support_not_prefdr_filter
test_final_subject_not_used_for_fit
test_mcq_requires_unique_advantage
```

## Gate W1

必须能明确回答：

1. decision node 是什么；
2. target 是什么；
3. query 下界按哪个时间；
4. 可见性按哪个时间；
5. unknown time 如何处理；
6. order task 是否预测“是否开单”。

---

# 6. W2 — encounter clock + event grouping schema

## 目标

建立临床时钟、specimen grouping、POE lifecycle grouping，并升级正式 event contract。

---

## 6.1 encounter clock

独立保留：

```text
ed_intime
ed_outtime
edregtime
edouttime
hospital_admittime
hospital_dischtime
icu_intime
icu_outtime
```

禁止静默：

```text
coalesce(ed_intime, edregtime, admittime)
```

必须显式记录 origin policy。

新增：

```text
encounter_clocks.parquet
```

字段：

```text
subject_id
hadm_id
stay_id
ed_intime
ed_outtime
hospital_admittime
hospital_dischtime
clock_status
clock_reason_code
```

---

## 6.2 event schema vNext

当前 1.2.0 升级为建议：

```text
clinical_event/1.3.0
```

新增顶层字段：

```text
source_group_type
source_group_id
source_group_id_status
source_group_source_key
time_semantics
lineage_visibility_scope
```

不得仅藏在 `value_structured_json`。

---

## 6.3 Lab grouping

对于 `hosp.labevents`：

```text
source_group_type = lab_specimen
source_group_source_key = specimen_id
source_group_id = stable_hash(hadm_id, specimen_id)
source_group_id_status = observed
```

若 specimen_id 缺失：

```text
source_group_id = null
source_group_id_status = missing_in_source
```

不得按 charttime 邻近关系伪造 specimen group。

---

## 6.4 POE grouping

对于 POE timeline：

```text
source_group_type = poe_lifecycle_chain
source_group_source_key = chain_root_poe_id
source_group_id = stable_hash(hadm_id, chain_root_poe_id)
source_group_id_status = derived_from_poe_relation
```

单个 action 保留：

```text
poe_id
poe_seq
predecessor_poe_id
successor_poe_id
chain_position
```

但：

```text
successor
chain_complete
retrospective terminal status
```

必须标记：

```text
lineage_visibility_scope = retrospective_only
```

---

## 6.5 time semantics

至少枚举：

```text
occurrence_time
collection_time_proxy
result_availability_time
order_entry_time
retrospective_record_time
unknown
```

Lab：

```text
charttime -> collection_time_proxy
storetime -> result_availability_time
```

不得将 charttime 命名为 specimen_received_time。

---

## 6.6 full rerun

W2 修改后必须重新生成 normalized events。

禁止在已有成功输出上 in-place 覆盖。

建议目录：

```text
versions/v3_1/events/
```

---

## 输出

```text
clinical_event_schema_1.3.0.json
encounter_clocks.parquet
event_grouping_audit.parquet
event_rebuild_manifest.json
```

## 测试

```text
test_ed_and_hospital_clock_not_coalesced
test_lab_specimen_group_uses_real_specimen_id
test_missing_specimen_id_not_inferred_by_time
test_poe_chain_spans_multiple_poe_ids
test_chain_root_stable
test_future_relation_retrospective_only
test_group_fields_are_top_level
```

## Gate W2

要求：

- event schema validation = 100%
- unexpected event count drift = 0
- unexpected ID drift = 0
- unexpected scientific field drift = 0
- known intentional schema/time changes全部有 manifest

---

# 7. W3a — Safe Snapshot

## 目标

构建 formal benchmark 唯一允许使用的 evidence snapshot adapter。

---

## 7.1 安全字段白名单

formal snapshot 允许：

```yaml
snapshot_safe_fields:
  - event_id
  - subject_id
  - hadm_id
  - encounter_id
  - event_kind
  - event_time
  - available_time
  - time_policy_id
  - time_semantics
  - evidence_phase
  - concept_id
  - preferred_name
  - entity_type
  - normalization_status
  - content_specificity
  - normalized_value_numeric
  - normalized_value_text
  - normalized_unit
  - abnormal_flag
```

---

## 7.2 永久禁止字段

```yaml
snapshot_forbidden_fields:
  - raw_record_json
  - clinical_readable_record_json
  - source_text
  - supporting_raw_row_refs
  - successor_poe_id
  - predecessor_poe_id
  - chain_complete
  - discontinued_by_poe_id
  - retrospective_terminal_status
  - discharge_icd
  - discharge_ner
```

---

## 7.3 visibility function

建议唯一实现：

```python
def is_visible(event, index_time, query_start, policy):
    if event.event_time is None:
        return False, "EVENT_TIME_UNKNOWN"

    if event.event_time >= index_time:
        return False, "EVENT_NOT_PREINDEX"

    if event.available_time is None:
        return False, "AVAILABLE_TIME_UNKNOWN"

    if event.available_time > index_time:
        return False, "NOT_YET_AVAILABLE"

    if event.evidence_phase in {"post_hoc", "administrative_end"}:
        return False, "POST_HOC"

    recency_time = resolve_recency_clock(event, policy)

    if recency_time is None:
        return False, "RECENCY_TIME_UNKNOWN"

    if recency_time < query_start:
        return False, "RECENCY_WINDOW_EXPIRED"

    return True, "INCLUDED"
```

---

## 7.4 必须建立 visibility audit

输出：

```text
visibility_audit.parquet
```

字段：

```text
decision_id
event_id
event_time
available_time
recency_time
recency_time_semantics
included
reason_code
```

---

## 7.5 必须新增 leakage fixtures

### Fixture A：future POE change

```text
00:15 create
00:19 change
snapshot index 00:17
```

断言：

- create 可见
- future change 不可见
- successor 不可见
- future final status 不可见

### Fixture B：Lab delayed availability

```text
19:55 collection proxy
20:56 available
query_start 20:19
index 00:19
```

断言：

- 允许进入 query
- recency basis = available_time

### Fixture C：available time unknown

主分析拒绝。

---

## 输出

```text
snapshot_adapter.py
snapshot_contract.yaml
snapshot_schema.json
visibility_audit.parquet
```

## Gate W3a

任何 formal downstream 代码只能调用：

```text
evaluation_pipeline.snapshot
```

禁止直接扫描 raw event payload。

---

# 8. W3b — Discharge NER

## 目标

保留 retrospective clinical audit 能力，但完全与 formal prospective evidence 隔离。

## 规则

输出实体至少：

```text
span
concept
assertion
section
experiencer
temporal_relation
document_time
model_version
review_status
```

统一：

```text
evidence_phase = post_hoc
```

formal benchmark 禁止使用。

## 人工评审

- 双人标注
- adjudication
- precision
- recall
- agreement

在冻结质量门槛前，不允许把 NER 用于 formal condition。

## 输出

```text
discharge_ner.parquet
discharge_ner_review.parquet
```

## Gate W3b

不阻塞 W4/W5 主链。

---

# 9. W4 — Investigation Episode + Candidate Catalog

## 目标

把 source events 转换为可用于 benchmark 的真实 investigation episodes。

---

# 9A. POE lifecycle folding

## 9A.1 grouping

按：

```text
source_group_id = poe_lifecycle_chain
```

排序：

```text
event_time
poe_seq
stable_source_order
```

---

## 9A.2 action semantics

### create / New

含义：

```text
observed ordering behavior
```

即使最终 terminal status 为 Inactive，也保留历史 create 行为。

### Change

只有发生 observable candidate-content change 时才可能产生新的 candidate state。

如果：

```text
change_without_observable_delta
```

只保留 lifecycle lineage，不新增 target。

### Cancel / Discontinue

只关闭 active interval。

不得反向删除已发生的 create target。

---

## 9A.3 episode schema

建议：

```text
episode_id
subject_id
hadm_id
source_group_id
candidate_id
candidate_class
candidate_specificity
initial_order_time
first_visible_time
last_action_time
terminal_action
terminal_status
was_changed
was_later_cancelled
action_count
source_action_ids
```

---

# 9B. clinical_ordered eligibility

## 原则

`clinical_ordered` 不能直接入候选。

建立：

```text
investigation-order-eligibility.yaml
```

候选状态：

```text
eligible_investigation
monitoring_only
excluded_non_investigation
review_required
```

示例：

```yaml
Cardiology:
  ECG:
    eligibility: eligible_investigation
  Echo:
    eligibility: eligible_investigation

General Care:
  Telemetry:
    eligibility: review_required
  Vitals/Monitoring:
    eligibility: monitoring_only

Medications:
  "*":
    eligibility: excluded_non_investigation

IV therapy:
  "*":
    eligibility: excluded_non_investigation
```

正式 catalog 必须由：

```text
1,000 例 / development 全量 order_type × order_subtype 频数
+
clinical review
```

后冻结。

不得仅依据单例样本冻结 whitelist。

---

# 9C. Imaging

## specificity

新增：

```text
candidate_specificity
```

枚举：

```text
category
subtype
entity
```

例如：

```text
Radiology / CT Scan
→ subtype
```

若 source 没有 body site，不得补成：

```text
CT head
CT chest
CT abdomen
```

MCQ options 必须在相同 specificity 层比较。

---

# 9D. Lab Result Episode

## specimen grouping

同一 specimen 下：

```text
component-level episode
panel-level episode
```

时间：

```text
collection_time_proxy = charttime
first_component_available_time = min(valid storetime)
complete_panel_available_time = max(required component storetime)
```

若 required component storetime 缺失：

```text
panel_complete_time = null
panel_status = incomplete_visibility
```

不得猜。

---

## panel definition

生成：

```text
panel-candidate-report.tsv
```

依据：

- official dictionary
- specimen co-occurrence
- component frequencies

再由临床 review 冻结：

```text
panel-definitions.yaml
```

状态：

```text
complete
partial
extra_component
unknown_panel
```

component / panel / category 统计必须分开。

---

## 输出

```text
investigation_episodes.parquet
candidate_catalog.parquet
investigation-order-eligibility.yaml
panel-definitions.yaml
episode-audit.parquet
catalog-lock.json
```

## 测试

```text
test_create_remains_observed_if_later_inactive
test_change_without_delta_not_new_target
test_cancel_does_not_delete_prior_create
test_medication_order_excluded_from_investigation
test_imaging_specificity_not_inflated
test_same_specimen_components_grouped
test_panel_complete_time_uses_max_required_storetime
```

## Gate W4

必须完成临床 review 后才能生成：

```text
catalog-lock.json
```

---

# 10. W5 — Decision Corpus

## 目标

生成唯一 formal decision-document corpus。

---

## 10.1 decision table

```text
decision_documents.parquet
```

字段至少：

```text
decision_id
subject_id
hadm_id
track
decision_semantics
decision_trigger_type
index_time
query_start
query_end
target_start
target_end
evidence_window_basis
availability_policy_id
candidate_catalog_version
protocol_core_hash
catalog_lock_hash
split_role
```

---

## 10.2 evidence table

```text
decision_evidence.parquet
```

字段：

```text
decision_id
event_id
concept_id
event_time
available_time
recency_time
recency_time_semantics
feature_value
visibility_status
visibility_reason
```

---

## 10.3 target table

```text
decision_targets.parquet
```

字段：

```text
decision_id
target_episode_id
candidate_id
candidate_class
candidate_specificity
target_time
target_rank_tie_group
```

---

## 10.4 zero-target semantics

order-triggered task 中不得将 zero target 解释为：

```text
doctor chose no investigation
```

统一：

```text
zero_target_semantics = no_eligible_same_class_target
```

---

## 10.5 human-readable trace

至少抽取 20 个 end-to-end traces。

每个 trace 必须显示：

```text
Decision
Included evidence
Excluded pre-index evidence
Targets
```

Excluded 原因必须可读，例如：

```text
AVAILABLE_TIME_UNKNOWN
NOT_YET_AVAILABLE
RECENCY_WINDOW_EXPIRED
POST_HOC
NORMALIZATION_UNRESOLVED
FORBIDDEN_FIELD
SPLIT_FORBIDDEN
```

---

## 10.6 determinism

科学 artifact 必须 deterministic。

不要要求包含 runtime timestamp 的 audit 文件 byte-identical。

拆分：

```text
content_manifest.json
execution_record.json
```

其中：

```text
content_manifest.json
```

必须重复运行 hash 一致。

---

## 输出

```text
decision_documents.parquet
decision_evidence.parquet
decision_targets.parquet
decision_manifest.json
content_manifest.json
execution_record.json
run-lock.json
```

## 测试

```text
test_target_never_enters_evidence
test_forbidden_payload_never_enters_snapshot
test_decision_records_recency_semantics
test_zero_target_semantics_explicit
test_run_lock_matches_protocol_and_catalog
test_content_manifest_deterministic
```

## Gate W5

必须完成 1000 例 integration audit，不能直接跑全量正式统计。

---

# 11. 1000 例 Integration Audit

这是 v3.1 新增的强制里程碑。

必须输出以下 6 张表。

---

## 11.1 time-policy-coverage.parquet

维度：

```text
source_module
source_table
event_kind
time_policy_id
```

指标：

```text
N
event_time_known_rate
available_time_known_rate
formal_eligible_rate
reject_reason_distribution
```

---

## 11.2 poe-subtype-audit.parquet

字段：

```text
order_type
order_subtype
event_kind
count
subject_count
eligibility
candidate_class
candidate_specificity
review_status
```

---

## 11.3 poe-lifecycle-audit.parquet

字段：

```text
source_group_id
action_count
poe_id_count
has_change
has_cancel
has_discontinue
has_observable_delta
terminal_status
historical_create_retained
```

---

## 11.4 specimen-audit.parquet

字段：

```text
specimen_group_id
component_count
charttime_count
storetime_known_rate
first_available_time
complete_available_time
panel_status
```

---

## 11.5 decision-evidence-audit.parquet

字段：

```text
decision_id
included_count
excluded_count
excluded_available_unknown
excluded_not_yet_available
excluded_recency
excluded_posthoc
excluded_unresolved
```

---

## 11.6 candidate-frequency-audit.parquet

字段：

```text
track
candidate_class
candidate_specificity
candidate_id
decision_count
subject_count
target_count
prevalence
```

---

## 11.7 Go / No-Go

只有以下全部满足才进入 W6/W7：

- candidate catalog 无明显误分类
- POE lifecycle folding 无结构性错误
- Lab specimen grouping 与 raw key 一致
- snapshot 不读取 future payload
- time exclusion reason 可解释
- zero-target 分布可解释
- 20 个 trace 临床可读
- deterministic content hash 稳定

如失败，只允许返回：

```text
W1 / W2 / W3a / W4 / W5
```

修订。

每次修订必须增加版本号和 change log。

---

# 12. W6 — Retrieval / TF-IDF / BM25

## 目标

比较 retrieval representation，不改变临床 gold semantics。

## 输入

只能读冻结：

```text
run-lock
development decision corpus
```

---

## 12.1 feature whitelist

建立：

```text
retrieval-feature-whitelist.yaml
```

禁止：

- subject/hadm/stay identifiers
- administrative facts
- discharge ICD
- discharge NER
- retrospective POE chain info
- unresolved concepts
- target-derived concepts
- forbidden time semantics

---

## 12.2 representation

比较：

```text
frequency
binary TF-IDF
log-count TF-IDF
BM25
```

IDF：

```text
idf = log((N + 1) / (df + 1)) + 1
```

其中 N 包括所有 eligible development decision docs，包括 zero-target docs。

IDF 只能用 development fit。

---

## 12.3 retrieval leakage control

validation query：

- 只检索 development documents
- same subject neighbor 删除
- 不允许 validation/final 进入 index

---

## 12.4 metrics

冻结：

```text
Recall@k
MRR
NDCG
macro
head/mid/tail
rare-stable
```

negative controls：

```text
random rare labels
shuffled targets
duplicate-row stress test
```

---

## 输出

```text
retrieval_metrics.parquet
retrieval_config_candidates.yaml
retrieval_negative_controls.parquet
retrieval_contribution_traces/
```

## Gate W6a

只在 validation 选 retrieval config。

final 不参与选择。

---

# 13. W7 — Statistical Rule Mining

## 目标

从新版 decision corpus 中产生可复现 statistical rule candidates。

---

## 13.1 2-stage family

顺序固定：

```text
structural legality
↓
marginal support
↓
full hypothesis family
↓
test statistic
↓
BH-FDR
↓
joint support gate
↓
shrinkage
↓
subject bootstrap
↓
validation verification
```

---

## 13.2 2×2 counts

每条 rule 必须保存：

```text
N
n_x
n_y
n_xy
```

N / n_x 包括 zero-target eligible docs。

---

## 13.3 effect measures

输出：

```text
frequency
conditional_probability
lift
log_relative_risk
shrunk_log_relative_risk
Wilson_interval
p_value
q_value
bootstrap_direction_stability
```

主 effect：

```text
shrunk_log_relative_risk
```

---

## 13.4 clustered audit

同时报告：

```text
decision_count
subject_count
```

可增加 sensitivity：

```text
all_decisions
vs
one_subject_one_vote
```

但主分析口径必须预先冻结。

---

## 13.5 validation

validation 只验证冻结 rule。

不得重新：

- 调阈值
- 换 family
- 换 candidate class
- 换窗口
- 换 shrinkage

validation support < 20：

```text
VALIDATION_INCONCLUSIVE
```

---

## 输出

```text
rule_family_manifest.parquet
rule_statistics.parquet
validated_rules.parquet
rule_bootstrap.parquet
validation_report.parquet
```

## Gate W7a

coronary-only W7 只是方法检查，不直接进入 W9 final question generation。

---

# 14. W8 — Multi-Diagnosis Expansion

## 目标

扩展到至少 4 个临床诊断域，测试 candidate / rule 跨域稳定性。

---

## 14.1 预注册诊断域

候选：

- infection / sepsis
- respiratory
- heart failure
- neurologic
- renal / electrolyte
- GI / hepatobiliary
- hematology / oncology

---

## 14.2 入选最低要求

每域：

```yaml
subjects_min: 2000
```

同时必须满足 source suitability：

- usable encounter clock
- usable investigation order
- usable Lab grouping
- sufficient candidate entropy
- acceptable unknown-time rate

不能只按人数选择。

---

## 14.3 diagnosis family 只能用于 cohort / stratification

禁止：

```text
post-hoc ICD diagnosis family
→ prospective query evidence
```

必须测试：

```text
diagnosis_stratum != prospective_feature
```

---

## 14.4 新 subjects split 扩展

新增：

```text
extend_exposure_registry(...)
```

要求：

- 已存在 subject role 永不改变
- previous_exposure != none 的新 subject 不得进入 formal val/final
- 新 subject 按冻结 W1 policy 分配
- 更新 exposure registry hash
- 更新 expanded run-lock

---

## 14.5 域选择

在满足硬门槛后，从合格域中选至少 4 个：

优先：

- candidate distribution 差异大
- data quality 高
- source coverage 高

每域最多抽到：

```text
2 × smallest_domain_subject_count
```

避免大域支配。

---

## 14.6 必须重新跑正式链

对 expanded cohort：

```text
W2
→ W3a
→ W4
→ W5
```

然后：

```text
W6b
→ W7b
```

W6b / W7b 是 formal expanded fit。

W9 只能读取 W7b。

---

## 输出

```text
diagnosis_domain_registry.yaml
expanded_exposure_registry.parquet
expanded_split_manifest.parquet
expanded_decision_corpus/
expanded_retrieval/
expanded_rules/
```

## Gate W8

至少 4 个诊断域通过：

- subject support
- source quality
- candidate diversity
- temporal validity

---

# 15. W6b / W7b — Expanded Formal Refit

## W6b

如果正式 retrieval 依赖 corpus IDF/vocabulary：

- 重新 fit development vocabulary
- 重新 fit IDF
- 重新做 validation method verification

## W7b

- expanded development 上重建完整 FDR family
- expanded validation 上机械验证
- 输出 domain-stratified stats
- pooled 与 domain-specific 方向冲突时显式标记

状态：

```text
POOLED_DOMAIN_CONFLICT
```

不能隐藏。

---

# 16. W9 — Question Candidate + Clinical Review

## 目标

从 expanded validated rules 生成可人工审查的问题候选。

---

## 16.1 输入限制

只能读取：

```text
W7b validated rule IDs
decision lineage
frozen candidate catalog
frozen run-lock
```

禁止读取：

- final statistics
- raw post-hoc answer clues
- unfrozen candidate
- old V2 rule

---

## 16.2 question metadata

每题至少：

```text
question_id
rule_id
decision_semantics
gold_type
track
candidate_class
candidate_specificity
behavioral_target_definition
protocol_hash
catalog_hash
run_hash
review_status
```

---

## 16.3 behavioral vs normative gold

拆分：

```text
behavioral_gold_status
normative_gold_status
```

允许：

```text
behavioral_gold_status = approved
normative_gold_status = unavailable
```

不得把 observed MIMIC behavior 自动写成 clinical best practice。

---

## 16.4 LLM 角色

LLM 只能：

- phrasing
- readability
- option wording normalization

LLM 不允许：

- 选择答案
- 更改统计排序
- 补未观测 body site
- 推断指南 gold
- 引入 target 后信息

---

## 16.5 programmatic validator

必须验证：

- query/target 时间不重叠
- answer 只来自 frozen rule
- unique answer
- same track
- same candidate class
- same candidate specificity
- split 合法
- lineage 完整
- no post-hoc leakage
- hashes 一致

---

## 16.6 人工评审

至少：

1. independent reviewer
2. clinical reviewer

临床 review 项：

- fact correctness
- visibility correctness
- comparison class correctness
- behavioral interpretation correctness
- unique answer
- no normative overclaim

---

## 输出

```text
question_candidates.parquet
question_cards/
programmatic_validation.parquet
independent_review.parquet
clinical_review.parquet
```

## Gold 规则

只有：

```text
programmatic pass
AND
independent review pass
AND
clinical review pass
```

才允许：

```text
behavioral_gold_status = approved
```

gold count 才可增加。

---

# 17. W10 — Final Test + Release

## 目标

在从未参与开发的 subject 上执行一次 formal final test，并冻结 release。

---

## 17.1 release-lock

生成：

```text
release-lock.json
```

绑定：

```text
protocol_core_lock
catalog_lock
expanded_run_lock
split_manifest
exposure_registry
event_schema
snapshot_schema
candidate_catalog
panel_definitions
retrieval_config
statistical_config
question_generator
clinical_review_freeze
```

---

## 17.2 final test

要求：

```text
formal_final_execution_count = 1
```

final test 前不得查看 final metrics。

final test 后不得：

- 换 vocabulary
- 换阈值
- 换 panel
- 换 catalog
- 换问题
- 换 retrieval 方法
- 换 FDR family

失败/inconclusive 也必须保留。

---

## 17.3 deterministic vs runtime artifact

分开：

```text
scientific_artifact_manifest.json
execution_audit.json
```

前者必须 deterministic。

后者允许：

- timestamp
- runtime
- RSS
- host audit

---

## 17.4 release text scan

程序检查 release 文本，禁止：

- 将 Lab proxy 描述为真实 specific lab order
- 将 charttime 描述为 specimen_received_time
- 将 observed behavior 描述为 clinical best
- 将 category-only order 描述为 exact exam
- 将 retrospective diagnosis 描述为 prospective evidence

---

## 输出

```text
final_test_report.parquet
release-lock.json
scientific_artifact_manifest.json
execution_audit.json
benchmark_cards/
repro_commands.md
```

## Gate W10

全部通过才能 release：

```text
reproducibility
split isolation
time leakage audit
semantic consistency
programmatic validation
independent review
clinical review
```

---

# 18. 固定 Reason Codes

本版执行前冻结。

## Encounter

```text
ENCOUNTER_CLOCK_MISSING
ENCOUNTER_CLOCK_AMBIGUOUS
ENCOUNTER_CLOCK_INVERTED
```

## Event / time

```text
EVENT_TIME_UNKNOWN
AVAILABLE_TIME_UNKNOWN
NOT_YET_AVAILABLE
RECENCY_TIME_UNKNOWN
RECENCY_WINDOW_EXPIRED
POST_HOC
ADMINISTRATIVE_END
TIME_POLICY_FORBIDDEN
```

## Specimen

```text
SPECIMEN_GROUP_MISSING
SPECIMEN_SOURCE_INSUFFICIENT
SPECIMEN_AVAILABLE_TIME_INCOMPLETE
```

## POE / order

```text
ORDER_CATEGORY_ONLY
ORDER_NON_INVESTIGATION
ORDER_MONITORING_ONLY
ORDER_CHANGE_NO_OBSERVABLE_DELTA
ORDER_CANCELLED_AFTER_CREATE
ORDER_CHAIN_INCOMPLETE
```

注意：

```text
ORDER_CANCELLED_AFTER_CREATE
```

不是 automatically reject historical behavior。

## Candidate / panel

```text
CANDIDATE_UNRESOLVED
CANDIDATE_CLASS_UNFROZEN
PANEL_UNREVIEWED
PANEL_INCOMPLETE
PANEL_UNKNOWN
```

## Decision

```text
DECISION_INVALID_WINDOW
DECISION_TARGET_OVERLAP
DECISION_SPLIT_FORBIDDEN
DECISION_NO_ELIGIBLE_TARGET
DECISION_FORBIDDEN_PAYLOAD
```

## Statistics

```text
SUPPORT_INSUFFICIENT
FDR_NOT_SIGNIFICANT
BOOTSTRAP_UNSTABLE
VALIDATION_REVERSAL
VALIDATION_INCONCLUSIVE
POOLED_DOMAIN_CONFLICT
```

## Question / review

```text
NO_UNIQUE_ANSWER
CLINICAL_REVIEW_REQUIRED
NORMATIVE_GOLD_UNAVAILABLE
```

---

# 19. 性能与工程约束

目标全量事件规模约：

```text
~27M normalized events
```

必须：

- PyArrow Scanner
- predicate pushdown
- projection pushdown
- stable partitioning
- 不构造全量 `list[dict]`
- fixed Parquet schema
- stable row sort
- deterministic tie ordering
- subject-aware processing
- RSS logging
- explicit memory failure

---

## 19.1 排序

统一 stable sort：

```text
subject_id
hadm_id
event_time
available_time
source_group_id
event_id
```

需要区分 null ordering，必须在 protocol 中固定。

---

## 19.2 浮点

统计：

- integer counts 先保存
- effect size 使用固定公式
- 输出 precision 固定
- tie sort 固定

---

## 19.3 分层测试

```text
synthetic
↓
single HADM regression
↓
1000 admission integration
↓
full development
↓
formal validation
↓
one-shot final
```

---

# 20. 建议代码模块

以下为建议新增结构，不要求必须使用完全相同路径：

```text
evaluation_pipeline/
  contracts/
    protocol_core.py
    event_schema.py
    snapshot_schema.py

  time/
    encounter_clock.py
    visibility.py
    recency_policy.py

  grouping/
    lab_specimen.py
    poe_lifecycle.py

  investigation/
    eligibility.py
    candidate_catalog.py
    episodes.py
    panels.py

  decision/
    enumerate_nodes.py
    build_documents.py
    build_evidence.py
    build_targets.py

  retrieval/
    features.py
    tfidf.py
    bm25.py

  statistics/
    family.py
    counts.py
    fdr.py
    shrinkage.py
    bootstrap.py
    validation.py

  review/
    question_candidates.py
    validators.py
```

---

# 21. 建议配置文件

```text
configs/
  protocol-core.yaml
  availability-policy.yaml
  evidence-window-policy.yaml
  split-policy.yaml
  reason-codes.yaml

  investigation-order-eligibility.yaml
  panel-definitions.yaml
  candidate-specificity.yaml

  retrieval-feature-whitelist.yaml
  retrieval-config.yaml
  statistical-config.yaml
```

---

# 22. 每阶段执行命令模板

以下仅作为 CLI 设计目标。

## W0

```powershell
uv run python -m evaluation_pipeline.audit.invalidate_legacy
```

## W1

```powershell
uv run python -m evaluation_pipeline.contracts.freeze_protocol
```

## W2

```powershell
uv run python -m evaluation_pipeline.time.build_encounter_clocks
uv run python -m evaluation_pipeline.grouping.rebuild_events
```

## W3a

```powershell
uv run python -m evaluation_pipeline.snapshot.validate_contract
```

## W4

```powershell
uv run python -m evaluation_pipeline.investigation.build_episodes
uv run python -m evaluation_pipeline.investigation.build_catalog
```

## W5

```powershell
uv run python -m evaluation_pipeline.decision.build_corpus
```

## Integration audit

```powershell
uv run python -m evaluation_pipeline.audit.integration_1000
```

## W6

```powershell
uv run python -m evaluation_pipeline.retrieval.evaluate
```

## W7

```powershell
uv run python -m evaluation_pipeline.statistics.mine_rules
```

## W8

```powershell
uv run python -m evaluation_pipeline.multidomain.expand
```

## W9

```powershell
uv run python -m evaluation_pipeline.review.build_questions
```

## W10

```powershell
uv run python -m evaluation_pipeline.release.final_test
```

实际 CLI 名称可按现有仓库结构调整，但每个命令必须有对应 manifest。

---

# 23. 每日执行优先级

## 第一阶段：只做 P0

顺序：

```text
1. W0 invalidation
2. W1 task / time / visibility contract
3. W2 top-level grouping schema
4. W3a safe snapshot
5. W4 POE lifecycle + eligibility
```

期间禁止开始：

- TF-IDF
- Lift
- FDR
- question generation

---

## 第二阶段：1000 例重建

目标：

```text
W2–W5 全部跑通
+
6 张 integration audit 表
+
20 个 readable traces
```

这一步通过后才允许：

```text
corpus freeze
```

---

## 第三阶段：方法验证

```text
W6a
W7a
```

目标是确认方法代码正确，而不是产生最终 gold。

---

## 第四阶段：多诊断正式扩展

```text
W8
→ expanded W2–W5
→ W6b
→ W7b
```

---

## 第五阶段：reviewable benchmark

```text
W9
```

仍然：

```text
gold = 0
```

直到 clinical review 真正批准。

---

## 第六阶段：formal release

```text
W10
```

---

# 24. 强制 Stop Conditions

出现以下任一情况必须停止下游：

1. snapshot 能读到 future-derived POE metadata。
2. clinical_ordered 仍直接作为 investigation candidate。
3. POE episode 仍按 poe_id 聚合。
4. terminal Inactive 仍会删除历史 create。
5. Lab specimen 通过时间邻近关系伪造。
6. `charttime` 被命名为 specimen_received_time。
7. available_time unknown 被静默替换。
8. W1 lock 中仍要求绑定 W4 尚未生成的 catalog。
9. FDR family 在 joint support 后才定义。
10. W8 新 subjects 没有进入 exposure registry。
11. W8 后没有重新 W6/W7。
12. final subject 参与任何 fit / selection。
13. behavioral gold 被描述为 normative clinical gold。
14. 任何题目没有完整 source → decision → rule → question lineage。

---

# 25. 最终验收矩阵

| 模块 | 必须通过 |
|---|---|
| W0 | 旧 V2 / phenotype /旧语义不可进入 |
| W1 | task/time/split/FDR/metric 全冻结 |
| W2 | clock 与 grouping contract 正确 |
| W3a | future leakage = 0 |
| W3b | post-hoc NER 与 formal evidence 隔离 |
| W4 | POE chain、Lab specimen、candidate catalog 正确 |
| W5 | decision/evidence/target 可追溯 |
| Integration | 6 audit tables + 20 traces 通过 |
| W6 | retrieval 只用 development fit |
| W7 | FDR family 与 validation 流程正确 |
| W8 | ≥4 诊断域 + split/exposure 合法 |
| W6b/W7b | expanded formal refit 完成 |
| W9 | programmatic + independent + clinical review |
| W10 | one-shot final + release lock |

---

# 26. Definition of Done

项目只有满足以下全部条件才算完成：

- 旧 V2 不可能进入新 benchmark。
- 旧 phenotype 不被复用。
- 每个 decision 有明确 index。
- 每条 evidence 可证明在 index 时已经可见。
- event occurrence 与 result availability 被分开处理。
- 不伪造 specimen_received_time。
- 不从 Lab result 推断 specific Lab order。
- generic_lab_order 与 lab_result_proxy 分开。
- POE lifecycle 按 chain 处理。
- `clinical_ordered` 经过 investigation eligibility catalog。
- terminal inactive 不会抹掉历史 ordering action。
- imaging 不超过 source specificity。
- panel 不重复计数、不删除 component lineage。
- TF-IDF / BM25 / rule statistics 均只在冻结 development 上 fit。
- FDR family 未被 joint-support cherry-pick。
- validation 只机械验证冻结规则。
- 至少 4 个诊断域正式进入 expanded corpus。
- W8 后完成正式 W6b/W7b。
- final test 从未用于 tuning。
- programmatic / independent / clinical review 均通过。
- behavioral gold 与 normative gold 明确分开。
- gold count 只统计人工批准项目。
- 所有 release artifacts 有 hash 和可复现命令。
- formal final test 只执行一次。

---

# 27. 本轮立即执行清单

下一步从以下 10 项继续。已有骨架的项是「对齐合同」，不是「从零实现」：

```text
[x] 1. 提交 W0 legacy invalidation（manifest + formal 入口拒绝已落地；语义拒绝测试仍需补）
[ ] 2. 冻结 decision_semantics=conditional_order_choice
[ ] 3. 冻结 evidence_window_basis
[ ] 4. 冻结 main availability policy
[ ] 5. event schema 升级为顶层 source_group 字段（先派生投影，不先全量重跑）
[ ] 6. 实现 poe_lifecycle_chain grouping（现实现按 poe_id，必须改）
[ ] 7. 实现 lab_specimen grouping（禁止用时间邻近补 specimen）
[ ] 8. formal snapshot 改为字段级 safe projection（补 recency clock）
[ ] 9. 生成 1000 例 order_type × subtype 审计
[ ] 10. 临床 review 后冻结 investigation eligibility catalog
```

这 10 项全部完成前，不进入 W6/W7。retrieval / ranking 代码保持离线原语，不得当成已完成的方法验证。

---

# 28. 版本变更说明：v3 → v3.1

本版相对 v3 的关键修改：

1. 明确 order 主任务为 conditional order choice。
2. 新增 evidence window basis。
3. 强化 event_time / available_time 双时钟语义。
4. POE lifecycle 从 poe_id 改为 chain_root。
5. terminal inactive 不再删除历史 ordering behavior。
6. clinical_ordered 降级为 source container。
7. safe snapshot 改为字段级 projection。
8. future-derived lifecycle metadata 标记 retrospective-only。
9. Lab specimen grouping 直接升级为顶层 event contract。
10. imaging 增加 candidate specificity。
11. W1 protocol lock 拆为 protocol-core / catalog / run 三层。
12. joint support 移到 FDR 后。
13. 新增强制 1000 例 integration audit。
14. W3 拆为 W3a snapshot 与 W3b discharge NER。
15. W8 新增 exposure-registry extension。
16. W8 后强制 W6b / W7b formal expanded refit。
17. behavioral gold / normative gold 明确分离。
18. deterministic scientific artifact 与 runtime audit 分离。

---

**执行原则：先保证“当时看到了什么”与“当时做了什么”定义正确，再讨论统计关联和题目质量。**
