# MIMIC-IV 3.1 文本字段清单

> 来源：本地 `mimic-iv-3.1` CSV 表头与官方 MIMIC-IV 文档
> 核查日期：2026-08-04
> 安全边界：本清单只记录字段名和语义，不包含任何患者级字段值。

## 1. 文本类型定义

| 等级 | 定义 | 是否属于原始病历正文 |
|---|---|---:|
| T0 | 医生、护士或其他临床人员连续书写的自然语言文书 | 是 |
| T1 | 自由输入或半结构化的临床结果、备注、属性值 | 否 |
| T2 | 药物、检查、操作、诊断等短文本名称 | 否 |
| T3 | 科室、状态、类别、单位等受控词汇或枚举 | 否 |
| ID | 去标识化标识符或代码，本身没有临床文本语义 | 否 |

本地 MIMIC-IV 3.1 中 **T0 数量为零**。以下字段均为 T1—T3；完整临床文书需另行下载 MIMIC-IV-Note。

## 2. `hosp` 模块

| 表 | 文本/字符串字段 | 类型 | 主要用途与限制 |
|---|---|---:|---|
| `admissions` | `admission_type`, `admission_location`, `discharge_location`, `insurance`, `language`, `marital_status`, `race` | T3 | 队列分层和就诊语境；`discharge_location` 是结局后信息 |
| `d_hcpcs` | `category`, `long_description`, `short_description` | T2/T3 | HCPCS 术语映射 |
| `d_icd_diagnoses` | `icd_code`, `long_title` | ID/T2 | ICD-9/10 诊断代码与名称 |
| `d_icd_procedures` | `icd_code`, `long_title` | ID/T2 | ICD-9/10 操作代码与名称 |
| `d_labitems` | `label`, `fluid`, `category` | T2/T3 | 化验项目、标本和类别字典 |
| `diagnoses_icd` | `icd_code` | ID | 无正文；需连接 `d_icd_diagnoses` 获得名称；属于出院后编码 |
| `drgcodes` | `drg_type`, `drg_code`, `description` | ID/T2/T3 | DRG 分组和描述；属于后验结算信息 |
| `emar` | `emar_id`, `poe_id`, `pharmacy_id`, `enter_provider_id`, `medication`, `event_txt` | ID/T2/T3 | 药物和执行事件；eMAR 不是完整 EMR 文本 |
| `emar_detail` | `administration_type`, `barcode_type`, `reason_for_no_barcode`, `complete_dose_not_given`, `dose_due`, `dose_due_unit`, `dose_given`, `dose_given_unit`, `will_remainder_of_dose_be_given`, `product_amount_given`, `product_unit`, `product_code`, `product_description`, `product_description_other`, `prior_infusion_rate`, `infusion_rate`, `infusion_rate_adjustment`, `infusion_rate_adjustment_amount`, `infusion_rate_unit`, `route`, `infusion_complete`, `completion_interval`, `new_iv_bag_hung`, `continued_infusion_in_other_location`, `restart_interval`, `side`, `site`, `non_formulary_visual_verification` | T1/T2/T3 | 细粒度给药属性；不少字段是受控状态或数值字符串，不能直接当自然语言语料 |
| `hcpcsevents` | `hcpcs_cd`, `short_description` | ID/T2 | HCPCS 事件及短描述 |
| `labevents` | `value`, `valueuom`, `flag`, `priority`, `comments` | T1/T3 | 结果、单位、异常标记和备注；`value` 可能是数值字符串，也可能是非数值结果 |
| `microbiologyevents` | `spec_type_desc`, `test_name`, `org_name`, `quantity`, `ab_name`, `dilution_text`, `dilution_comparison`, `interpretation`, `comments` | T1/T2/T3 | 标本—检测—微生物—药敏关系；适合关系抽取和标准化 |
| `omr` | `result_name`, `result_value` | T1/T2 | 门诊测量的属性—值表示；不是门诊病历正文 |
| `patients` | `gender`, `anchor_year_group` | T3 | 人口学分层和年代区间 |
| `pharmacy` | `medication`, `proc_type`, `status`, `route`, `frequency`, `disp_sched`, `infusion_type`, `sliding_scale`, `duration_interval`, `expiration_unit`, `dispensation` | T2/T3 | 药房处理和用药计划；不等于实际给药 |
| `poe` | `poe_id`, `order_type`, `order_subtype`, `transaction_type`, `discontinue_of_poe_id`, `discontinued_by_poe_id`, `order_provider_id`, `order_status` | ID/T2/T3 | 医嘱类型、状态和版本链 |
| `poe_detail` | `poe_id`, `field_name`, `field_value` | ID/T1/T2 | 医嘱附加字段的 EAV 表；`field_value` 是最值得审计的半结构化文本之一 |
| `prescriptions` | `drug_type`, `drug`, `formulary_drug_cd`, `gsn`, `ndc`, `prod_strength`, `form_rx`, `dose_val_rx`, `dose_unit_rx`, `form_val_disp`, `form_unit_disp`, `route` | ID/T1/T2/T3 | 处方药名、规格、剂量和途径；属于计划，不代表已执行 |
| `procedures_icd` | `icd_code` | ID | 无正文；需连接 `d_icd_procedures` |
| `provider` | `provider_id` | ID | 只有去标识化人员标识，无临床文本 |
| `services` | `prev_service`, `curr_service` | T3 | 医疗服务线转科时间线 |
| `transfers` | `eventtype`, `careunit` | T3 | 院内转运和病区轨迹 |

## 3. `icu` 模块

| 表 | 文本/字符串字段 | 类型 | 主要用途与限制 |
|---|---|---:|---|
| `caregiver` | `caregiver_id` | ID | 只有去标识化人员标识 |
| `chartevents` | `value`, `valueuom` | T1/T3 | 数值、评分、设备状态和床旁短文本；必须连接 `d_items` 解释 `itemid` |
| `d_items` | `label`, `abbreviation`, `linksto`, `category`, `unitname`, `param_type` | T2/T3 | ICU 项目字典和数据类型语义 |
| `datetimeevents` | `value`, `valueuom` | T1/T3 | 被记录为日期/时间的临床事件 |
| `icustays` | `first_careunit`, `last_careunit` | T3 | ICU 单元类型和转科语境 |
| `ingredientevents` | `amountuom`, `rateuom`, `statusdescription` | T3 | 输入液体/药物成分的单位和状态；需连接 `d_items` |
| `inputevents` | `amountuom`, `rateuom`, `ordercategoryname`, `secondaryordercategoryname`, `ordercomponenttypedescription`, `ordercategorydescription`, `totalamountuom`, `statusdescription` | T2/T3 | 输注、液体和用药输入类别及状态 |
| `outputevents` | `valueuom` | T3 | 输出量单位；项目名称来自 `d_items` |
| `procedureevents` | `valueuom`, `location`, `locationcategory`, `ordercategoryname`, `ordercategorydescription`, `statusdescription` | T2/T3 | ICU 操作的位置、类别和状态 |

## 4. 可用于文本处理的优先级

### 第一优先：T1 半结构化临床文本

- `poe_detail.field_name/field_value`
- `labevents.value/comments`
- `microbiologyevents` 的标本、检测、菌名、药敏和 `comments`
- `omr.result_name/result_value`
- `icu/chartevents.value` + `d_items.label`

适合：实体标准化、属性—值抽取、关系抽取、时间线重建和结构化到文本的忠实生成。

### 第二优先：T2 临床名称

- 药品、剂量、规格、途径；
- ICD/HCPCS/DRG 术语；
- 化验、微生物和 ICU 项目名称。

适合：术语归一化、编码映射、检索和标签描述。不能把字典名称当作医生诊断原文。

### 第三优先：T3 工作流状态

- 入出院、科室、服务线；
- 医嘱和给药状态；
- 操作类别、位置和单位。

适合：医疗流程建模和事件序列，不适合独立 NLP 语料训练。

## 5. 处理规则

1. 保留原始字段和值，不在抽取阶段让 LLM 改写。
2. 每个文本片段保留 `source_table`、源主键、`charttime/storetime` 和提取版本。
3. 区分“计划”“执行”“结果”和“出院后编码”，不能只按字符串合并。
4. UNKNOWN/未记录不能转换为阴性。
5. `comments` 和 `field_value` 仍属于受限患者数据，不能提交 Git 或发送到普通外部 API。
6. 模板化病例文本必须同时保留机器可读事件层，避免后续无法追溯生成内容。

## 6. 结论

MIMIC-IV 3.1 的核心价值是结构化 EHR 与大量短文本/半结构化字段，而不是完整临床文书。合理路线是：

```text
MIMIC-IV 3.1 结构化事件
        +
MIMIC-IV-Note 原始出院/放射文本
        +
ED 主诉、CXR、ECG、ECHO 等扩展模态
        ↓
可追溯的病例事件层与任务样本层
```
