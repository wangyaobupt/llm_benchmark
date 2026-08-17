# MIMIC visit archive schema（已废止）

> 本文描述的派生 visit archive 已被 [MIMIC 单次住院原始归档 JSONL schema](mimic-admission-raw-jsonl-schema.md) 取代。新的数据层只保存原始 MIMIC 字段；决策快照改为评测层动态读取规则。本文仅保留为历史记录，不得作为新抽取实现依据。

## 定位

`mimic_visit_archive` 是评测数据层的冻结 Interface。它保存一个 episode 的回顾性完整归档，同时为每类题型提供按决策时点裁剪的快照。完整归档不能直接作为题干输入；题干只能读取已通过未来信息泄漏验证的 snapshot evidence。

当前冻结版本：`1.0.0`。

## 顶层结构

顺序与字段固定为：

1. `metadata`
2. `identifiers`
3. `episode`
4. `demographics`
5. `presentation`
6. `vitals`
7. `orders`
8. `investigations`
9. `diagnoses`
10. `treatments`
11. `care_path`
12. `discharge`
13. `longitudinal_refs`
14. `partition`
15. `decision_snapshots`

字段增删、语义变化或嵌套路径变化必须提升 schema version，并同步修改 `data_pipeline/archived/parquet_to_jsonl/schema.py` 的验证规则。

## 时间语义

- `episode_start_time`：episode 纳入临床轨迹的起点；若住院前有已关联 ED，则取更早的 ED 起点。
- `ed_start_time` / `ed_end_time`：已关联 ED contact 的实际边界。
- `clinical_end_time`：临床过程结束；死亡早于出院时取死亡时间，否则取出院时间。
- `administrative_end_time`：行政出院记录时间。
- `event_time`：事件发生或标本采集/检查执行时间。
- `available_time`：结果或记录在当时可供决策者获知的最早时间。
- `recorded_time`：数据写入或最终记录时间。

实验室结果、微生物、放射、医嘱、处方、药房、eMAR、转科和服务路径必须保留三个事件时间字段。时间未知时保留 `null`，不能用其他时间冒充。

## 同期资料与后验资料

- ED triage 主诉存入 `presentation.triage_chief_complaint`，属于同期资料。
- 出院小结中的主诉、HPI、既往史等存入 `presentation.discharge_summary_retrospective`，整体标记 `evidence_phase=post_hoc`。
- ICD 编码诊断、DRG、出院小结章节均为后验资料，不得进入任何决策快照的可见证据。
- ED diagnosis 是临床 ED 流程记录，是否可见仍由 `available_time <= cutoff_time` 决定。

## 患者隔离

`partition` 使用 `subject_hash_v1` 对 `subject_id` 做稳定散列。默认 20% 患者进入 development，80% 进入 final_test。同一患者的所有 episode 必须在同一分区；冠状动脉疾病谱调试病例只能从 development 中选择。

## 五类决策快照

每条归档生成五个 snapshot：检查选择、临床诊断、治疗处置、转诊科室、离院随访。每个 snapshot 保存：

- `cutoff_time`
- `visible_paths`
- `hidden_outcome`
- `source_event_ids`
- 不复制临床正文的 `evidence` 引用
- `status`

写出前必须对每个 `status=ready` 的快照执行两条 fail-closed 规则：

1. `available_time` 缺失或晚于 `cutoff_time`，拒绝；
2. `evidence_phase=post_hoc`，拒绝。

缺少该题型可观测 outcome 时，snapshot 标记 `excluded_missing_outcome`，不能强行生成题目。
