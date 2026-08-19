# MIMIC 单次住院原始归档 JSONL schema

## 1. 目标与边界

数据层输出定义为 `mimic_admission_raw` 1.0.0：一行 JSON 对应一个原生 MIMIC `hadm_id`，保存该次住院可通过原始主外键关联的全部纳入表行。字段名和字段值来自 MIMIC-IV 3.1、MIMIC-IV-ED 2.2 和 MIMIC-IV-Note 2.2，不在本层解析、重命名、标准化、分类或构造决策快照。

本文件说明归档层级、逐表字段组和连接边界。每个字段独立一行的JSON路径、JSON存储类型、MIMIC源类型、空值约束、中文含义、键角色、时间语义、信息阶段和Benchmark使用限制，见[逐字段数据字典](mimic-admission-raw-field-dictionary.md)。该字典从冻结的实际表头自动对账生成，不能用手工字段清单绕过覆盖验证。

本文件说明归档层级、逐表字段组和连接边界。每个字段独立一行的JSON路径、JSON存储类型、MIMIC源类型、空值约束、中文含义、键角色、时间语义、信息阶段和Benchmark使用限制，见[逐字段数据字典](mimic-admission-raw-field-dictionary.md)。该字典从冻结的实际表头自动对账生成，不能用手工字段清单绕过覆盖验证。

本层只做三件事：

1. 以 `subject_id + hadm_id` 建立住院归档；
2. 以原始 `stay_id`、`poe_id + poe_seq`、`emar_id + emar_seq`、`note_id` 连接没有 `hadm_id` 的子表；
3. 按原始数据模块和表名组织 JSON。

禁止使用时间窗口、关键词或临床推断将记录归入某次住院。

## 2. JSONL 顶层字段

```json
{
  "schema": {"name": "mimic_admission_raw", "version": "1.0.0"},
  "subject_id": "10000032",
  "hadm_id": "22595853",
  "mimic_iv_hosp": {},
  "mimic_iv_icu": {},
  "mimic_iv_ed": {},
  "mimic_iv_note": {}
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema` | object | 文件格式标识；不是临床派生字段。固定为 `mimic_admission_raw` 1.0.0。 |
| `subject_id` | string | 来自 `admissions.subject_id`，用于定位患者。 |
| `hadm_id` | string | 来自 `admissions.hadm_id`，一行 JSON 的住院主键。 |
| `mimic_iv_hosp` | object | HOSP 纳入表；键名与原始 CSV 文件名一致。 |
| `mimic_iv_icu` | object | ICU 纳入表；明确不含 `chartevents`。 |
| `mimic_iv_ed` | object | 通过 `edstays.hadm_id` 原生关联的 ED 表。 |
| `mimic_iv_note` | object | 有原生 `hadm_id` 的文书及其 detail 行。 |

所有表键固定存在；没有记录时为 `[]`。表中每个对象的键严格等于原始 CSV 表头，空单元格写为 JSON `null`，不增加 `_event_time`、`evidence_phase`、标准名称或分类字段。

需要区分两种“类型”：原始CSV单元格进入JSONL后保存为字符串或`null`；逐字段数据字典中的`source_type`则记录MIMIC源表的逻辑类型（例如`INTEGER`、`TIMESTAMP`、`VARCHAR`）。类型转换只能发生在后续cleaned sidecar，不能改写本原始归档。

需要区分两种“类型”：原始CSV单元格进入JSONL后保存为字符串或`null`；逐字段数据字典中的`source_type`则记录MIMIC源表的逻辑类型（例如`INTEGER`、`TIMESTAMP`、`VARCHAR`）。类型转换只能发生在后续cleaned sidecar，不能改写本原始归档。

## 3. HOSP 字段

### 3.1 患者与住院

| JSON 路径 | 原始字段 | 字段说明 |
|---|---|---|
| `mimic_iv_hosp.patients[]` | `subject_id`, `gender`, `anchor_age`, `anchor_year`, `anchor_year_group`, `dod` | 患者标识、性别、锚定年龄与年份、年份范围、死亡日期。按 `subject_id` 纳入同一原始患者行。 |
| `mimic_iv_hosp.admissions[]` | `subject_id`, `hadm_id`, `admittime`, `dischtime`, `deathtime`, `admission_type`, `admit_provider_id`, `admission_location`, `discharge_location`, `insurance`, `language`, `marital_status`, `race`, `edregtime`, `edouttime`, `hospital_expire_flag` | 本次住院的原始行政记录、入出院时间、来源去向和院内死亡标志。每个归档必须且只能有一行。 |
| `mimic_iv_hosp.transfers[]` | `subject_id`, `hadm_id`, `transfer_id`, `eventtype`, `careunit`, `intime`, `outtime` | 院内床位或病区流转；保留原始事件类型、care unit 和起止时间。 |
| `mimic_iv_hosp.services[]` | `subject_id`, `hadm_id`, `transfertime`, `prev_service`, `curr_service` | 负责医疗服务的变更时间、前一服务和当前服务。 |

### 3.2 检验与微生物

| JSON 路径 | 原始字段 | 字段说明 |
|---|---|---|
| `mimic_iv_hosp.labevents[]` | `labevent_id`, `subject_id`, `hadm_id`, `specimen_id`, `itemid`, `order_provider_id`, `charttime`, `storetime`, `value`, `valuenum`, `valueuom`, `ref_range_lower`, `ref_range_upper`, `flag`, `priority`, `comments` | 原始检验事件。`charttime/storetime`、文本值/数值、单位、参考范围、异常标记、优先级和备注全部保留，不合并为 panel。 |
| `mimic_iv_hosp.microbiologyevents[]` | `microevent_id`, `subject_id`, `hadm_id`, `micro_specimen_id`, `order_provider_id`, `chartdate`, `charttime`, `spec_itemid`, `spec_type_desc`, `test_seq`, `storedate`, `storetime`, `test_itemid`, `test_name`, `org_itemid`, `org_name`, `isolate_num`, `quantity`, `ab_itemid`, `ab_name`, `dilution_text`, `dilution_comparison`, `dilution_value`, `interpretation`, `comments` | 标本、检测、培养菌、分离株和药敏原始行；一个 specimen 可能对应多行，禁止聚合去重。 |

### 3.3 医嘱、药房、处方与给药

| JSON 路径 | 原始字段 | 字段说明 |
|---|---|---|
| `mimic_iv_hosp.poe[]` | `poe_id`, `poe_seq`, `subject_id`, `hadm_id`, `ordertime`, `order_type`, `order_subtype`, `transaction_type`, `discontinue_of_poe_id`, `discontinued_by_poe_id`, `order_provider_id`, `order_status` | 原始 provider order 行，包括新增/变更/停止关系与状态。 |
| `mimic_iv_hosp.poe_detail[]` | `poe_id`, `poe_seq`, `subject_id`, `field_name`, `field_value` | 通过 `subject_id + poe_id + poe_seq` 连接到本次住院 POE 的 EAV 明细；不改写 field name/value。 |
| `mimic_iv_hosp.pharmacy[]` | `subject_id`, `hadm_id`, `pharmacy_id`, `poe_id`, `starttime`, `stoptime`, `medication`, `proc_type`, `status`, `entertime`, `verifiedtime`, `route`, `frequency`, `disp_sched`, `infusion_type`, `sliding_scale`, `lockout_interval`, `basal_rate`, `one_hr_max`, `doses_per_24_hrs`, `duration`, `duration_interval`, `expiration_value`, `expiration_unit`, `expirationdate`, `dispensation`, `fill_quantity` | 药房处理、核验、给药途径、频次、输注和调剂信息。 |
| `mimic_iv_hosp.prescriptions[]` | `subject_id`, `hadm_id`, `pharmacy_id`, `poe_id`, `poe_seq`, `order_provider_id`, `starttime`, `stoptime`, `drug_type`, `drug`, `formulary_drug_cd`, `gsn`, `ndc`, `prod_strength`, `form_rx`, `dose_val_rx`, `dose_unit_rx`, `form_val_disp`, `form_unit_disp`, `doses_per_24_hrs`, `route` | 原始处方药名、代码、规格、剂量、剂型、频次和途径。 |
| `mimic_iv_hosp.emar[]` | `subject_id`, `hadm_id`, `emar_id`, `emar_seq`, `poe_id`, `pharmacy_id`, `enter_provider_id`, `charttime`, `medication`, `event_txt`, `scheduletime`, `storetime` | 电子给药记录父行，保存药物、执行状态及计划/记录时间。 |
| `mimic_iv_hosp.emar_detail[]` | `subject_id`, `emar_id`, `emar_seq`, `parent_field_ordinal`, `administration_type`, `pharmacy_id`, `barcode_type`, `reason_for_no_barcode`, `complete_dose_not_given`, `dose_due`, `dose_due_unit`, `dose_given`, `dose_given_unit`, `will_remainder_of_dose_be_given`, `product_amount_given`, `product_unit`, `product_code`, `product_description`, `product_description_other`, `prior_infusion_rate`, `infusion_rate`, `infusion_rate_adjustment`, `infusion_rate_adjustment_amount`, `infusion_rate_unit`, `route`, `infusion_complete`, `completion_interval`, `new_iv_bag_hung`, `continued_infusion_in_other_location`, `restart_interval`, `side`, `site`, `non_formulary_visual_verification` | 通过 `subject_id + emar_id + emar_seq` 连接的完整原始给药明细。只保存这一份原始行，不再同时保存 concept/raw_value/raw_payload 派生副本。 |

### 3.4 编码与操作

| JSON 路径 | 原始字段 | 字段说明 |
|---|---|---|
| `mimic_iv_hosp.diagnoses_icd[]` | `subject_id`, `hadm_id`, `seq_num`, `icd_code`, `icd_version` | 住院 ICD 编码及原始顺序；不派生 primary diagnosis。 |
| `mimic_iv_hosp.procedures_icd[]` | `subject_id`, `hadm_id`, `seq_num`, `chartdate`, `icd_code`, `icd_version` | 住院 ICD 操作编码、顺序和日期。 |
| `mimic_iv_hosp.hcpcsevents[]` | `subject_id`, `hadm_id`, `chartdate`, `hcpcs_cd`, `seq_num`, `short_description` | HCPCS 编码事件及源描述。 |
| `mimic_iv_hosp.drgcodes[]` | `subject_id`, `hadm_id`, `drg_type`, `drg_code`, `description`, `drg_severity`, `drg_mortality` | DRG 类型、编码、描述、严重度和死亡风险。 |

## 4. ICU 字段

| JSON 路径 | 原始字段 | 字段说明 |
|---|---|---|
| `mimic_iv_icu.icustays[]` | `subject_id`, `hadm_id`, `stay_id`, `first_careunit`, `last_careunit`, `intime`, `outtime`, `los` | ICU stay 标识、首末 care unit、起止时间和 LOS。 |
| `mimic_iv_icu.datetimeevents[]` | `subject_id`, `hadm_id`, `stay_id`, `caregiver_id`, `charttime`, `storetime`, `itemid`, `value`, `valueuom`, `warning` | ICU 中以日期/时间为值的原始事件。 |
| `mimic_iv_icu.ingredientevents[]` | `subject_id`, `hadm_id`, `stay_id`, `caregiver_id`, `starttime`, `endtime`, `storetime`, `itemid`, `amount`, `amountuom`, `rate`, `rateuom`, `orderid`, `linkorderid`, `statusdescription`, `originalamount`, `originalrate` | ICU 输入事件的成分、数量、速率、医嘱关系和状态。 |
| `mimic_iv_icu.inputevents[]` | `subject_id`, `hadm_id`, `stay_id`, `caregiver_id`, `starttime`, `endtime`, `storetime`, `itemid`, `amount`, `amountuom`, `rate`, `rateuom`, `orderid`, `linkorderid`, `ordercategoryname`, `secondaryordercategoryname`, `ordercomponenttypedescription`, `ordercategorydescription`, `patientweight`, `totalamount`, `totalamountuom`, `isopenbag`, `continueinnextdept`, `statusdescription`, `originalamount`, `originalrate` | ICU 输液、药物、营养等输入及速率、总量、医嘱类别和状态。 |
| `mimic_iv_icu.outputevents[]` | `subject_id`, `hadm_id`, `stay_id`, `caregiver_id`, `charttime`, `storetime`, `itemid`, `value`, `valueuom` | 尿量、引流等 ICU 输出记录。 |
| `mimic_iv_icu.procedureevents[]` | `subject_id`, `hadm_id`, `stay_id`, `caregiver_id`, `starttime`, `endtime`, `storetime`, `itemid`, `value`, `valueuom`, `location`, `locationcategory`, `orderid`, `linkorderid`, `ordercategoryname`, `ordercategorydescription`, `patientweight`, `isopenbag`, `continueinnextdept`, `statusdescription`, `originalamount`, `originalrate` | ICU 操作、位置、医嘱关系、状态和原始数值。 |

### 明确排除：`chartevents`

`mimic-iv-3.1/icu/chartevents.csv.gz` 不进入 JSONL。该表包含大规模床旁生命体征、呼吸机参数、评分和护理观察。整表排除避免体积失控，也避免在原始数据层通过 itemid 主观区分“监护”和“非监护”。因此输出不提供完整 ICU 生命体征趋势。

## 5. ED 字段

只有 `edstays.subject_id + edstays.hadm_id` 原生匹配本次住院的 ED stay 才纳入；子表再按 `subject_id + stay_id` 连接。

| JSON 路径 | 原始字段 | 字段说明 |
|---|---|---|
| `mimic_iv_ed.edstays[]` | `subject_id`, `hadm_id`, `stay_id`, `intime`, `outtime`, `gender`, `race`, `arrival_transport`, `disposition` | ED 起止时间、人口学副本、到院交通方式和 ED disposition。 |
| `mimic_iv_ed.triage[]` | `subject_id`, `stay_id`, `temperature`, `heartrate`, `resprate`, `o2sat`, `sbp`, `dbp`, `pain`, `acuity`, `chiefcomplaint` | ED 分诊生命体征、疼痛、acuity 和原始主诉。 |
| `mimic_iv_ed.vitalsign[]` | `subject_id`, `stay_id`, `charttime`, `temperature`, `heartrate`, `resprate`, `o2sat`, `sbp`, `dbp`, `rhythm`, `pain` | ED 期间重复生命体征、节律和疼痛。 |
| `mimic_iv_ed.diagnosis[]` | `subject_id`, `stay_id`, `seq_num`, `icd_code`, `icd_version`, `icd_title` | ED ICD 诊断及顺序和源标题。JSON 键使用原始表名 `diagnosis`，不改名为 `ed_diagnosis`。 |
| `mimic_iv_ed.medrecon[]` | `subject_id`, `stay_id`, `charttime`, `name`, `gsn`, `ndc`, `etc_rn`, `etccode`, `etcdescription` | ED 用药核对中的药名、药物代码和治疗类别。 |
| `mimic_iv_ed.pyxis[]` | `subject_id`, `stay_id`, `charttime`, `med_rn`, `name`, `gsn_rn`, `gsn` | ED Pyxis 发药记录。 |

## 6. NOTE 字段

只纳入原始 `hadm_id` 与本次住院匹配的文书；不使用文本时间推断。detail 表通过已纳入的 `note_id + subject_id` 连接。

| JSON 路径 | 原始字段 | 字段说明 |
|---|---|---|
| `mimic_iv_note.discharge[]` | `note_id`, `subject_id`, `hadm_id`, `note_type`, `note_seq`, `charttime`, `storetime`, `text` | 完整原始出院文书；不拆分主诉、HPI 或出院章节。 |
| `mimic_iv_note.discharge_detail[]` | `note_id`, `subject_id`, `field_name`, `field_value`, `field_ordinal` | 出院文书 detail EAV 行及原始顺序。 |
| `mimic_iv_note.radiology[]` | `note_id`, `subject_id`, `hadm_id`, `note_type`, `note_seq`, `charttime`, `storetime`, `text` | 完整原始放射报告；不猜测 exam name。 |
| `mimic_iv_note.radiology_detail[]` | `note_id`, `subject_id`, `field_name`, `field_value`, `field_ordinal` | 放射报告 detail EAV 行及原始顺序。 |

## 7. 不进入单次住院 JSONL 的源表

| 处理 | 表 | 原因 |
|---|---|---|
| 独立公共字典 | `d_labitems`, `d_icd_diagnoses`, `d_icd_procedures`, `d_hcpcs`, `provider`, `d_items`, `caregiver` | 不是某次住院的患者事件；每条住院重复保存会造成冗余。原表单独保存一次。 |
| 排除 | `chartevents` | 大规模 ICU 床旁监护与护理记录，用户明确排除。 |
| 排除 | `omr` | 没有原生 `hadm_id`；纳入某次住院需要时间推断，违反原始关联原则。 |

## 8. 原始关联规则

| 子表 | 父表 | 原始连接键 |
|---|---|---|
| HOSP 直接表 | `admissions` | `subject_id + hadm_id` |
| `patients` | `admissions` | `subject_id` |
| `poe_detail` | `poe` | `subject_id + poe_id + poe_seq` |
| `emar_detail` | `emar` | `subject_id + emar_id + emar_seq` |
| `edstays` | `admissions` | `subject_id + hadm_id` |
| ED 子表 | 已纳入 `edstays` | `subject_id + stay_id` |
| ICU 表 | `admissions` | `subject_id + hadm_id`；同时保留原始 `stay_id` |
| NOTE 主表 | `admissions` | `subject_id + hadm_id` |
| NOTE detail | 对应已纳入文书 | `subject_id + note_id` |

父记录不存在、subject 冲突或只能时间推断的记录不进入住院 JSONL，并在聚合质量报告中计数。

## 9. 顺序、空值与完整性

- 每张表的行按原始字段组成的 canonical JSON 字符串稳定排序；行顺序不被解释为临床顺序。
- 原始重复行不删除；完全相同的两行仍保存两次。
- CSV 空单元格写为 JSON `null`，其他值保持源字符串，不做数值或时间类型转换。
- 每个输出行必须有且仅有一条 `admissions`。
- `chartevents`、派生字段和未知字段出现时验证失败。
- 数据层不生成 development/final_test；患者隔离清单属于评测层外部 manifest。
