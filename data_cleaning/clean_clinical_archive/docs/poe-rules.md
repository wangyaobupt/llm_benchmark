# POE 可观察医嘱时间线规则

## 证据边界

POE 表示提供者下达或操作医嘱，不证明医嘱已经执行；MIMIC 数据整理还移除了 audit trails。因此输出称为“可观察医嘱时间线”，不称为完整 EHR 审计历史。官方证据见 [MIMIC-IV v3.x POE 官方语义与时间线解析边界](../../../docs/reference/mimic-iv-poe-official-evidence.md)。

## 输入和连接

每个 admission 使用：

- `mimic_iv_hosp.poe`
- `mimic_iv_hosp.poe_detail`
- `mimic_iv_hosp.prescriptions`
- `mimic_iv_hosp.pharmacy`

`poe_id` 连接 POE 明细和处方；处方与药房严格使用 `pharmacy_id` 连接。`pharmacy.poe_id` 只用于直接归属及一致性检查，不替代 `pharmacy_id`，也不允许凭“只有一个候选行”猜测连接。

解析器校验重复携带的 `subject_id`、`hadm_id`、`poe_seq`。POE 的 `poe_id`、`poe_seq`、`subject_id`、`ordertime`、`order_type` 必填，并必须与 admission 顶层标识一致。缺失、重复或冲突立即失败。`poe_id` 不符合 `subject_id-poe_seq` 时保留事件并添加 `poe_id_format_mismatch`。

`poe_detail.field_name` 是开放 EAV 属性，不使用封闭白名单。已知字段生成中文标签；未知字段保留原值并计入 `unmapped_detail_field_counts`。`documentation_status` 只说明官方文档覆盖状态，不判断字段是否合法。

## 动作

| `transaction_type` | `action` | 中文显示 |
|---|---|---|
| `New` | `create` | 新开 |
| `Change` | `change` | 变更 |
| `D/C` | `discontinue` | 停止 |

官方列出但未解释业务语义的 `Co`、`H`、`T` 输出为 `action=uninterpreted`，保留 `action_raw`，并添加 `official_transaction_semantics_unresolved`。不在官方六值枚举中的非空值标记 `unknown_transaction_type`；空值标记 `missing_transaction_type`。

## 关系链

- `discontinue_of_poe_id`：当前事件指向前驱医嘱；
- `discontinued_by_poe_id`：当前事件指向后继医嘱。

解析器检查目标存在、双向链接、类别一致性和时间顺序，并生成 `chain_root_poe_id` 与 `chain_position`。显式链接缺失或冲突只按其具体质量标志表达，不用内容相似度猜补关系。

## 输出语义

事件按 `(ordertime, poe_seq, poe_id)` 稳定排序，写入 `mimic_iv_hosp.poe_timeline`。每个事件保留当前源行的 provenance；进行前驱比较时还保留比较源行。

`content_specificity` 只描述可见内容的具体程度：

- `entity_specific`：存在具体处方药物；
- `attribute_enriched`：没有处方药物，但有 POE_DETAIL 属性；
- `subtype_only`：只有明确 `order_subtype`；
- `category_only`：只有医嘱主类别。

例如只有 `order_type=Lab` 时只能输出“新开检验医嘱”，同时标记 `category_only_no_specific_order_content`，不能猜测具体检验项目。处方不能当作实际给药；药房状态不能当作床旁执行；`Inactive` 也不能解释为执行完成。

## 主要质量标志

| 标志 | 含义 |
|---|---|
| `category_only_no_specific_order_content` | 只有医嘱类别，没有具体内容 |
| `change_without_observable_delta` | 标为变更，但可见字段无临床内容差异 |
| `unresolved_predecessor` / `unresolved_successor` | 显式关系目标不在当前 admission |
| `nonreciprocal_predecessor_link` / `nonreciprocal_successor_link` | 双向关系不一致 |
| `predecessor_category_mismatch` | 前驱与当前类别不同 |
| `predecessor_time_after_current_event` | 前驱时间晚于当前事件 |
| `unresolved_pharmacy_id` | 处方的 `pharmacy_id` 无法匹配 |
| `pharmacy_poe_id_conflict` | 精确匹配的药房行指向另一 POE |
| `ambiguous_medication_pairing` | 多条同名同类型药物不能可靠逐字段配对 |
| `unmapped_detail_field` | 尚未配置中文标签的 EAV 属性 |

## 实现来源

底层规则实现由 `poe_timeline.parse_admission` 唯一维护；本清洗器直接调用它，不复制 POE 解析代码。后续若需判断医嘱是否执行，应另行连接 `emar/emar_detail`、检验结果、影像报告或 ICU 执行事件，不能改写 POE 本身的证据层级。
