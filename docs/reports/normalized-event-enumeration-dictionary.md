# Normalize 住院事件枚举字段字典

本字典基于本地住院记录 `hadm_id=28234402` 的 835 条 normalize 后事件生成。
它解释的是字段允许出现的分类值，不是临床 Gold 标准，也不代表这些取值在所有住院记录中一定完整出现。

## 1. `event_kind`

事件的主要语义类型。`condition_recorded_post_hoc` 和 `procedure_recorded_post_hoc` 属于此字段的枚举值，不是独立的布尔字段。

| 枚举值 | 含义 | 当前次数 |
|---|---|---:|
| `condition_recorded_post_hoc` | 事后记录的疾病、诊断或临床条件；不能直接证明该信息在事件发生当时已经可用。 | 27 |
| `vital_measured` | 生命体征被测量或记录。 | 26 |
| `triage_acuity_recorded` | 急诊分诊严重程度或 acuity 被记录。 | 1 |
| `symptom_reported` | 患者症状被报告或记录。 | 1 |
| `patient_transferred` | 患者发生转科、转运或护理单元变更。 | 5 |
| `medication_reconciled` | 用药清单或既往用药完成核对。 | 23 |
| `medication_dispensed` | 药物被发放或配发。 | 9 |
| `procedure_recorded_post_hoc` | 事后记录的操作或手术；不等同于实时操作执行记录。 | 1 |
| `laboratory_ordered` | 实验室检查被开立。 | 40 |
| `imaging_ordered` | 影像学检查被开立。 | 6 |
| `imaging_reported` | 影像学检查报告被记录或发布。 | 4 |
| `clinical_ordered` | 临床医嘱被开立，但当前记录未细化为实验室或影像订单。 | 197 |
| `service_changed` | 临床服务或责任科室发生变更。 | 1 |
| `medication_order_status_recorded` | 药物医嘱状态被记录。 | 86 |
| `medication_ordered` | 药物医嘱被开立。 | 99 |
| `laboratory_resulted` | 实验室检查结果被记录。 | 268 |
| `output_measured` | 患者输出量被测量或记录，例如尿量。 | 16 |
| `input_administered` | 液体、药物或其他输入被给予并记录。 | 17 |
| `procedure_performed` | 操作或治疗过程被执行并记录。 | 5 |
| `microbiology_resulted` | 微生物学检查结果被记录。 | 2 |
| `document_recorded` | 临床文书或文档被记录。 | 1 |

## 2. `lifecycle_action`

订单或临床对象在生命周期中的动作。该字段为空通常表示事件不是可拆分生命周期的订单动作。

| 枚举值 | 含义 | 当前次数 |
|---|---|---:|
| `create` | 创建或开立。 | 298 |
| `change` | 对已有订单或对象进行修改。 | 29 |
| `discontinue` | 停止、撤销或终止。 | 15 |
| `null` | 没有可识别的生命周期动作，或该事件不适用。 | 493 |

## 3. `status`

来源系统提供的原始状态。它保留源系统语义，不能直接当作统一的“是否有效”标签。

| 枚举值 | 含义 | 当前次数 |
|---|---|---:|
| `ED` | 急诊相关状态。 | 1 |
| `admit` | 入院。 | 1 |
| `transfer` | 转科或转运。 | 2 |
| `discharge` | 出院。 | 1 |
| `Inactive` | 来源系统标记为非活动。 | 243 |
| `Discontinued via patient discharge` | 因患者出院而停止。 | 33 |
| `Inactive (Due to a change order)` | 因变更医嘱而变为非活动。 | 16 |
| `Expired` | 已过期。 | 11 |
| `Discontinued` | 已停止。 | 26 |
| `FinishedRunning` | 已完成运行。 | 16 |
| `Stopped` | 已停止运行。 | 3 |
| `ChangeDose/Rate` | 剂量或速率发生变化。 | 2 |
| `Paused` | 暂停。 | 1 |
| `null` | 来源没有状态，或当前事件不适用。 | 479 |

## 4. `assertion`

事件对临床事实的断言状态。

| 枚举值 | 含义 | 当前次数 |
|---|---|---:|
| `present` | 该事件所表示的事实在记录中存在。 | 835 |

## 5. `evidence_phase`

事件在证据链中的时间/来源阶段。

| 枚举值 | 含义 | 当前次数 |
|---|---|---:|
| `source_event` | 来自原始记录中的源事件。 | 806 |
| `post_hoc` | 事后记录、回填或由后验文书产生的事件。 | 29 |

## 6. `time_resolution_status`

事件时间能否从来源数据中可靠解析。

| 枚举值 | 含义 | 当前次数 |
|---|---|---:|
| `resolved` | 时间已可靠解析。 | 742 |
| `partially_resolved` | 只获得部分时间信息，存在推导或精度限制。 | 58 |
| `unresolved` | 无法可靠确定事件时间。 | 35 |

## 7. `time_precision`

事件时间的精度。

| 枚举值 | 含义 | 当前次数 |
|---|---|---:|
| `second` | 精确到秒。 | 799 |
| `date` | 只有日期，没有可靠的时分秒。 | 1 |
| `unknown` | 时间精度无法确定。 | 35 |

## 8. `time_policy_id`

生成事件时间和可用时间时所使用的版本化时间策略。后缀 `_v1`、`_v2` 表示策略版本，不应当跨版本直接混用。

| 枚举值 | 含义 | 当前次数 |
|---|---|---:|
| `post_hoc_no_time_v1` | 事后记录且来源没有可靠事件时间。 | 27 |
| `triage_no_time_v1` | 分诊记录的时间策略。 | 8 |
| `transfer_intime_v1` | 使用转科入科时间。 | 5 |
| `chart_only_v1` | 以 chart 时间为主要依据。 | 52 |
| `post_hoc_chartdate_v1` | 事后记录使用 chartdate。 | 1 |
| `poe_timeline_v1` | 使用医嘱时间线。 | 243 |
| `radiology_chart_store_v2` | 影像报告按 chart/store 时间处理。 | 4 |
| `service_transfer_v1` | 服务转移时间策略。 | 1 |
| `pharmacy_workflow_v1` | 药房流程时间策略。 | 86 |
| `prescription_poe_link_v1` | 处方与医嘱时间线关联策略。 | 99 |
| `chart_store_v2` | 使用 chart/store 时间。 | 270 |
| `icu_output_chart_store_v2` | ICU 输出记录的 chart/store 时间策略。 | 16 |
| `icu_interval_completion_v2` | ICU 区间记录使用完成时间。 | 22 |
| `discharge_post_hoc_v2` | 出院后验记录时间策略。 | 1 |

## 9. `entity_type`

事件所对应的临床实体类型。

| 枚举值 | 含义 | 当前次数 |
|---|---|---:|
| `coded_clinical_concept` | 编码化临床概念，当前未细分为更具体实体。 | 28 |
| `vital_sign` | 生命体征。 | 26 |
| `triage_acuity` | 急诊分诊 acuity。 | 1 |
| `symptom` | 症状。 | 1 |
| `care_unit` | 护理或住院单元。 | 5 |
| `medication` | 药物。 | 217 |
| `laboratory_test` | 实验室检查。 | 308 |
| `imaging_study` | 影像学检查。 | 6 |
| `imaging_report` | 影像学报告。 | 4 |
| `medication_order_category` | 药物医嘱类别。 | 128 |
| `clinical_service` | 临床服务或科室。 | 1 |
| `clinical_order` | 一般临床医嘱。 | 69 |
| `icu_item` | ICU 记录项目。 | 38 |
| `microbiology_test` | 微生物学检查。 | 2 |
| `clinical_document` | 临床文书。 | 1 |

## 10. `normalization_status`

来源概念是否成功映射到标准化概念。

| 枚举值 | 含义 | 当前次数 |
|---|---|---:|
| `mapped` | 已成功映射到标准化概念。 | 484 |
| `unresolved` | 尚未得到可靠标准化概念。 | 351 |

## 11. `content_specificity`

事件内容的具体程度。

| 枚举值 | 含义 | 当前次数 |
|---|---|---:|
| `entity_specific` | 已具体到明确的临床实体或检查项目。 | 671 |
| `category_only` | 只有大类，缺少具体实体。 | 98 |
| `subtype_only` | 只有亚型信息，缺少完整上位实体。 | 44 |
| `attribute_enriched` | 在实体基础上还包含额外属性。 | 22 |

## 12. `abnormal_flag`

来源系统对结果是否异常的标记。

| 枚举值 | 含义 | 当前次数 |
|---|---|---:|
| `abnormal` | 来源标记为异常。 | 84 |
| `normal` | 来源标记为正常。 | 161 |
| `null` | 没有异常标记或该事件不适用。 | 590 |

## 13. `unit_normalization_status`

数值单位是否完成标准化。

| 枚举值 | 含义 | 当前次数 |
|---|---|---:|
| `mapped` | 原始单位已映射到标准单位。 | 307 |
| `not_applicable` | 该事件没有适用的数值单位。 | 528 |

## 14. `source_action`

来源数据中的原始动作字段，不等同于 normalize 后的 `lifecycle_action`。

| 枚举值 | 含义 | 当前次数 |
|---|---|---:|
| `create` | 来源记录中的创建动作。 | 199 |
| `change` | 来源记录中的变更动作。 | 29 |
| `discontinue` | 来源记录中的停止动作。 | 15 |
| `null` | 来源没有动作值。 | 592 |

## 使用边界

- `status=Inactive` 只表示来源系统状态，不表示该事件没有发生，也不等于临床上“不应选择”。
- `event_kind=condition_recorded_post_hoc` 表示事后记录的条件事件；它不能作为事件发生前可见的证据。
- `normalization_status=unresolved` 表示概念映射不足，不能自动解释为某个具体检查或治疗。
- `post_hoc`、`available_time` 和 `time_resolution_status` 应结合使用，判断某条记录在预测时点是否可用。
- 本文件中的次数只反映当前 `hadm_id=28234402` 样本，不是全库分布。
