# MIMIC-IV POE 可观察医嘱时间线解析器

## 目标与命名边界

本模块把 admission 级原始 JSONL 中的 `poe` 医嘱解析为逐事件 JSONL，服务于后续临床决策时间线构建。输出称为“可观察医嘱时间线”，不称为完整 EHR 审计历史。

原因是 MIMIC 官方说明 POE 表示提供者下达或操作医嘱，不证明医嘱已经执行；MIMIC 数据整理还移除了 audit trails。完整证据边界见 [MIMIC-IV v3.x POE 官方语义与时间线解析边界](../reference/mimic-iv-poe-official-evidence.md)。

## 输入与关联

输入必须是 `mimic-admission-raw` admission 级 JSONL，每行至少包含：

- `mimic_iv_hosp.poe`
- `mimic_iv_hosp.poe_detail`
- `mimic_iv_hosp.prescriptions`
- `mimic_iv_hosp.pharmacy`

解析器以官方主键 `poe_id` 连接 POE 明细和处方；处方与药房严格使用 `pharmacy_id` 连接。`pharmacy.poe_id` 只用于药房行与 POE 的直接归属及一致性检查，不替代 `pharmacy_id`，也不允许“只有一个候选行”时猜测连接。解析器同时校验各表重复携带的 `subject_id`、`hadm_id`、`poe_seq`，冲突会直接报错，不会静默拼接。

各来源的作用如下：

| 来源 | 用途 | 不允许的推断 |
|---|---|---|
| `poe` | 下达时间、主/子类型、事务代码、状态和前后医嘱链接 | 不把 `Inactive` 解释为已经执行或执行完成 |
| `poe_detail` | EAV 属性，例如收治科室、复苏意愿、给药途径 | 不把空值解释为否定或正常 |
| `prescriptions` | 药名、剂量、途径、计划起止时间 | 不把处方当作实际给药 |
| `pharmacy` | 处方频次、疗程等补充属性 | 不把药房状态当作床旁执行结果 |

POE 的 `poe_id`、`poe_seq`、`subject_id`、`ordertime`、`order_type` 是必填字段。解析器还要求 admission 归档顶层 `subject_id/hadm_id` 存在，并验证 POE 与归档边界一致；缺失或冲突直接报错。`poe_id` 不符合 `subject_id-poe_seq` 时保留事件，但添加 `poe_id_format_mismatch`。

`poe_detail.field_name` 是开放的 EAV 属性，不使用封闭白名单。已知字段生成中文标签，未知字段保留原值并进入 `unmapped_detail_field_counts`。每条 detail 另带 `documentation_status`：官方页面截至 v2.2 已列出的字段为 `documented_v2_2`；当前 v3.1 样本额外观察到的 `Route` 为 `observed_extension`；其余为 `unclassified`。该状态描述文档覆盖范围，不判断字段是否合法。

## 动作与关系链

解析器将三个字面明确、且可由显式链接校验的事务值映射为：

| 原值 | 派生动作 | 中文显示 |
|---|---|---|
| `New` | `create` | 新开 |
| `Change` | `change` | 变更 |
| `D/C` | `discontinue` | 停止 |

官方还列出 `Co`、`H`、`T`，但没有解释其业务语义。因此这些值输出为 `action=uninterpreted`，保留 `action_raw`，并添加 `official_transaction_semantics_unresolved`，不得猜译。只有不在官方六值枚举中的非空值才使用 `unknown_transaction_type`；空值使用 `missing_transaction_type`。

关系链优先使用：

- `discontinue_of_poe_id`：当前事件指向前驱医嘱；
- `discontinued_by_poe_id`：当前事件指向后继医嘱。

输出会检查目标是否存在、双向链接是否一致、类别是否一致、前驱时间是否晚于当前事件，并生成 `chain_root_poe_id` 和 `chain_position`。

## 事件输出结构

每行输出一个按 `(ordertime, poe_seq, poe_id)` 稳定排序的事件：

```json
{
  "event_time": "2154-02-06 09:26:50",
  "poe_id": "19487795-4172",
  "action": "change",
  "action_raw": "Change",
  "display_text_zh": "变更用药医嘱，Oxycodone ...",
  "content_specificity": "entity_specific",
  "resolution_sources": ["poe", "prescriptions", "pharmacy"],
  "medication_resolution": {
    "medication_count": 1,
    "with_drug": 1,
    "with_dose": 1,
    "with_route": 1,
    "with_frequency": 1
  },
  "order_content": {},
  "incremental_information": {
    "comparison_basis": "linked_predecessor",
    "added_facts": [],
    "removed_facts": [],
    "clinical_changes": [],
    "summary_zh": "给药频次：Q12H → QAM",
    "observable_content_change": true
  },
  "relations": {
    "chain_complete": true
  },
  "quality_flags": [],
  "provenance": {
    "current": {},
    "comparison": {}
  }
}
```

`provenance.current` 保留当前事件的参与源行；发生前驱比较时，`provenance.comparison` 保存前驱 POE 及其关联源行。药房 ID 等审计标识保留在来源中，但不计为临床增量。

### 内容具体度与解析来源

`content_specificity` 描述输出具体到什么程度，不代表临床置信度：

- `entity_specific`：存在具体处方药物；
- `attribute_enriched`：没有处方药物，但有 POE_DETAIL 属性；
- `subtype_only`：只有明确 `order_subtype`；
- `category_only`：只有医嘱主类别，无法知道具体项目。

`resolution_sources` 显式列出当前显示内容使用的 `poe`、`poe_detail`、`prescriptions`、`pharmacy`。`medication_resolution` 分别统计有药名、剂量、途径和频次的药物数量，避免把“字段更多”误写成“置信度更高”。

例如只有 `order_type=Lab` 时，只能输出“新开检验医嘱”，并标记 `category_only_no_specific_order_content`；不能猜测具体检验项目。

### 主要质量标志

| 标志 | 含义 |
|---|---|
| `category_only_no_specific_order_content` | 只有医嘱类别，没有具体医嘱内容 |
| `change_without_observable_delta` | 源数据标为变更，但可见字段没有临床内容差异 |
| `unresolved_predecessor` / `unresolved_successor` | 显式关系指向的 POE 不在当前 admission 记录中 |
| `nonreciprocal_predecessor_link` | 前后关系没有双向一致 |
| `nonreciprocal_successor_link` | 当前行的后继没有反向指回当前 POE |
| `predecessor_category_mismatch` | 前驱与当前医嘱类别不同 |
| `predecessor_time_after_current_event` | 前驱下达时间晚于当前事件 |
| `official_transaction_semantics_unresolved` | 官方合法事务代码，但官方未解释业务语义 |
| `unknown_transaction_type` | 不在官方枚举中的事务代码 |
| `missing_transaction_type` | 事务代码缺失 |
| `unresolved_pharmacy_id` | 处方携带的 `pharmacy_id` 在当前归档中找不到 |
| `pharmacy_poe_id_conflict` | 精确匹配的药房行指向另一个 POE，因此未用于补充处方 |
| `ambiguous_medication_pairing` | 前后均有多条同名同类型药物，不能可靠逐字段配对 |
| `unmapped_detail_field` | 尚未配置中文标签的新 EAV 属性 |

## 批量运行

在项目根目录运行：

```powershell
python -m poe_timeline `
  data\validation\mimic-admission-raw-coronary-sample-100.jsonl `
  --output data\validation\mimic-admission-raw-coronary-sample-100-poe-timeline.jsonl `
  --report docs\reports\mimic-poe-timeline-sample-metrics.json
```

用 `--limit N` 做小批验证。输入按行流式读取，事件与报告均先写入各自目标目录的临时文件；两者都成功生成后，再分别原子替换目标文件。两个目标文件不是跨文件系统事务，消费者应同时核对报告中的 schema、输入路径和事件计数。

## 向临床决策时间线推进

当前层回答“何时下达、变更或停止了什么可见医嘱”。下一层应按证据类型连接实际结果，但不能混为同一事件：

1. POE：意图或计划；
2. `prescriptions/pharmacy`：药物处方计划；
3. `emar/emar_detail`：实际给药记录；
4. `labevents/microbiologyevents`：检验采集与结果；
5. radiology note：影像报告；
6. ICU procedure/input events：操作和治疗执行；
7. discharge note：回顾性总结，必须防止时间泄漏。

最终时间线需同时保留 `event_time`、证据来源、意图/执行/结果阶段、可见性时间与原始行，才能用于临床决策过程建模。
