# RWD Benchmark 数据画像报告 (EDA)

> 生成时间：2026-08-06 00:58 ｜ 数据来源：MIMIC-IV v3.1


## 0. 数据总览

| 指标 | 原始版 (raw) | 清洗版 (cleaned) |
|---|---|---|
| 行数 | 11687 | 11687 |
| 列数 | 17 | 17 |
| 文件大小 | 266.0 MB | 246.9 MB |

### 各列非空率

| # | 字段 | 类型 | 非空数 | 缺失数 | 缺失率 |
|---:|---|---|---:|---:|---:|
| 1 | `subject_id` | Scalar | 11687 | 0 | 0.0% |
| 2 | `hadm_id` | Scalar | 11687 | 0 | 0.0% |
| 3 | `age_at_encounter` | Scalar | 11687 | 0 | 0.0% |
| 4 | `sex` | Scalar | 11687 | 0 | 0.0% |
| 5 | `chief_complaint` | Text | 11530 | 157 | 1.3% |
| 6 | `history_of_present_illness` | Text | 11176 | 511 | 4.4% |
| 7 | `past_medical_history` | Text | 11227 | 460 | 3.9% |
| 8 | `medications_on_admission` | Text | 10255 | 1432 | 12.3% |
| 9 | `investigation_orders` | JSON | 11303 | 384 | 3.3% |
| 10 | `investigation_reports` | JSON | 11687 | 0 | 0.0% |
| 11 | `primary_icd_code` | Scalar | 11687 | 0 | 0.0% |
| 12 | `primary_diagnosis_name` | Scalar | 11687 | 0 | 0.0% |
| 13 | `primary_icd_version` | Scalar | 11687 | 0 | 0.0% |
| 14 | `other_diagnoses` | JSON | 11587 | 100 | 0.9% |
| 15 | `medication_prescriptions` | JSON | 11665 | 22 | 0.2% |
| 16 | `procedures` | JSON | 6892 | 4795 | 41.0% |
| 17 | `discharge_record` | Text | 0 | 11687 | 100.0% |

## 1. 人口学画像

### 年龄

| 统计量 | 值 |
|---|---|
| 样本数 | 11687 |
| 均值 | 61.5 |
| 标准差 | 18.0 |
| 最小值 | 18 |
| P25 | 50 |
| 中位数 | 63 |
| P75 | 75 |
| 最大值 | 102 |
| <18 异常 | 0 |

### 性别

- **M**: 6022 (51.5%)
- **F**: 5665 (48.5%)

### 患者与就诊次数

| 指标 | 值 |
|---|---|
| 独立患者数 | 5328 |
| 人均就诊次数 (均值) | 2.19 |
| 就诊1次的患者 | 3171 (59.5%) |
| 就诊≥2次的患者 | 2157 (40.5%) |
| 最多就诊次数 | 51 |

## 2. 诊断分布

### ICD 版本

- **ICD-ICD-9-CM**: 7368 (63.0%)
- **ICD-ICD-10-CM**: 4319 (37.0%)

### Top 25 主诊断

| # | 诊断名称 | 数量 | 占比 |
|---:|---|---:|---:|
| 1 | Acute kidney failure, unspecified | 160 | 1.4% |
| 2 | Encounter for antineoplastic chemotherapy | 155 | 1.3% |
| 3 | Coronary atherosclerosis of native coronary artery | 145 | 1.2% |
| 4 | Urinary tract infection, site not specified | 136 | 1.2% |
| 5 | Sepsis, unspecified organism | 123 | 1.1% |
| 6 | Other chest pain | 107 | 0.9% |
| 7 | Subendocardial infarction, initial episode of care | 99 | 0.8% |
| 8 | Unspecified septicemia | 99 | 0.8% |
| 9 | Pneumonia, organism unspecified | 97 | 0.8% |
| 10 | Acute pancreatitis | 92 | 0.8% |
| 11 | Syncope and collapse | 85 | 0.7% |
| 12 | Acute on chronic diastolic heart failure | 76 | 0.7% |
| 13 | Other postoperative infection | 75 | 0.6% |
| 14 | Non-ST elevation (NSTEMI) myocardial infarction | 72 | 0.6% |
| 15 | Hypertensive heart and chronic kidney disease with heart fai… | 64 | 0.5% |
| 16 | Cellulitis and abscess of leg, except foot | 63 | 0.5% |
| 17 | Acute on chronic systolic heart failure | 60 | 0.5% |
| 18 | Atrial fibrillation | 56 | 0.5% |
| 19 | Aortic valve disorders | 52 | 0.4% |
| 20 | Alcohol withdrawal | 51 | 0.4% |
| 21 | Unspecified intestinal obstruction | 51 | 0.4% |
| 22 | Fever, unspecified | 49 | 0.4% |
| 23 | Cerebral artery occlusion, unspecified with cerebral infarct… | 47 | 0.4% |
| 24 | Intestinal infection due to Clostridium difficile | 47 | 0.4% |
| 25 | Cerebral aneurysm, nonruptured | 43 | 0.4% |

> 独立主诊断名称共 **2891** 种


### 其他诊断 (other_diagnoses) 数量分布

| 统计量 | 值 |
|---|---|
| 有其他诊断的就诊 | 11523 (98.6%) |
| 平均数量 | 11.7 |
| 中位数 | 10 |
| 最大值 | 38 |

## 3. 文本字段：原始 vs 清洗

### 非空率对比

| 字段 | 原始非空 | 原始非空率 | 清洗非空 | 清洗非空率 |
|---|---:|---:|---:|---:|
| `chief_complaint` | 11687 | 100.0% | 11530 | 98.7% |
| `history_of_present_illness` | 11593 | 99.2% | 11176 | 95.6% |
| `past_medical_history` | 11489 | 98.3% | 11227 | 96.1% |
| `medications_on_admission` | 10766 | 92.1% | 10255 | 87.7% |
| `discharge_record` | 0 | 0.0% | 0 | 0.0% |

### 原始字符长度分布

| 字段 | 均值 | 中位数 | P90 | 最大值 |
|---|---:|---:|---:|---:|
| `chief_complaint` | 110 | 82 | 175 | 6407 |
| `history_of_present_illness` | 1403 | 1295 | 2557 | 11187 |
| `past_medical_history` | 391 | 242 | 833 | 8002 |
| `medications_on_admission` | 395 | 309 | 820 | 3862 |
| `discharge_record` | - | - | - | - |

### 清洗后 JSON 实体数量分布

| 字段 | 有实体的就诊 | 平均实体数 | 中位数 | 最大值 |
|---|---:|---:|---:|---:|
| `chief_complaint` | 11530 (98.7%) | 2.1 | 2 | 20 |
| `history_of_present_illness` | 11176 (95.6%) | 7.3 | 6 | 64 |
| `past_medical_history` | 11227 (96.1%) | 8.9 | 8 | 47 |
| `medications_on_admission` | 10255 (87.7%) | 8.1 | 7 | 46 |

## 4. 结构化 JSON 字段

### 项数分布

| 字段 | 有数据的就诊 | 平均项数 | 中位数 | P90 | 最大值 |
|---|---:|---:|---:|---:|---:|
| `investigation_orders` | 11303 (96.7%) | 1.0 | 1 | 1 | 2 |
| `investigation_reports` | 11352 (97.1%) | 45.7 | 40 | 83 | 256 |
| `other_diagnoses` | 11587 (99.1%) | 11.7 | 10 | 22 | 38 |
| `medication_prescriptions` | 11665 (99.8%) | 21.3 | 19 | 37 | 128 |
| `procedures` | 6892 (59.0%) | 1.7 | 1 | 5 | 28 |

### 检查医嘱 (investigation_orders) Top 15 类型

| # | 类型 | 数量 |
|---:|---|---:|
| 1 | Lab | 11309 |

### investigation_reports lab/radiology breakdown

| metric | laboratory | radiology |
|---|---:|---:|
| visits with data | 11065 (94.7%) | 9365 (80.1%) |
| mean items | 43.3 | 2.4 |
| median | 38 | 2 |
| max | 231 | 32 |

> WARNING: investigation_orders.poe_detail non-empty in only 1/11687 (0.01%) visits.


### 处方 (medication_prescriptions) Top 15 药物

| # | 药物 | 出现次数 | 就诊占比 |
|---:|---|---:|---:|
| 1 | sodium chloride 0.9%  flush | 10677 | 91.4% |
| 2 | acetaminophen | 8661 | 74.1% |
| 3 | heparin | 7777 | 66.5% |
| 4 | docusate sodium | 6883 | 58.9% |
| 5 | senna | 6073 | 52.0% |
| 6 | ondansetron | 4761 | 40.7% |
| 7 | aspirin | 4026 | 34.4% |
| 8 | oxycodone (immediate release) | 3994 | 34.2% |
| 9 | insulin | 3938 | 33.7% |
| 10 | magnesium sulfate | 3921 | 33.6% |
| 11 | potassium chloride | 3837 | 32.8% |
| 12 | dextrose 50% | 3586 | 30.7% |
| 13 | glucagon | 3438 | 29.4% |
| 14 | bisacodyl | 3047 | 26.1% |
| 15 | lorazepam | 2945 | 25.2% |

### 手术/操作 (procedures) Top 15

| # | 操作名称 | 数量 |
|---:|---|---:|
| 1 | Venous catheterization, not elsewhere classified | 403 |
| 2 | Insertion of Infusion Device into Superior Vena Cava, P… | 382 |
| 3 | Central venous catheter placement with guidance | 283 |
| 4 | Coronary arteriography using two catheters | 269 |
| 5 | Enteral infusion of concentrated nutritional substances | 268 |
| 6 | Continuous invasive mechanical ventilation for less tha… | 239 |
| 7 | Hemodialysis | 208 |
| 8 | Insertion of endotracheal tube | 205 |
| 9 | Other endoscopy of small intestine | 203 |
| 10 | Procedure on single vessel | 199 |
| 11 | Left heart cardiac catheterization | 187 |
| 12 | Introduction of Nutritional Substance into Upper GI, Vi… | 166 |
| 13 | Percutaneous abdominal drainage | 165 |
| 14 | Extracorporeal circulation auxiliary to open heart surg… | 165 |
| 15 | Injection or infusion of cancer chemotherapeutic substa… | 164 |

## 5. 离院记录 (discharge_record)

| 指标 | 值 |
|---|---|
| 非空就诊数 | 0 (0.0%) |
| 平均字符长度 | nan |
| 中位数 | nan |
| P90 | nan |
| 最大值 | nan |

## 6. 数据质量检查

| 检查项 | 结果 |
|---|---|
| 重复 `hadm_id` | 0 |
| `age` 缺失 | 0 |
| `age` < 18 | 0 |
| `sex` 空值 | 0 |
| `chief_complaint` 空值 | 157 |
| `primary_icd_code` 空值 | 0 |
| `primary_diagnosis_name` 空值 | 0 |
| 非清洗列不一致行（应=0）| 0 |

> ✅ 13 个非清洗列 raw↔cleaned 完全一致

| 行顺序 (hadm_id) 一致 | ✅ 是 |
| 清洗字段 JSON 解析失败 | 0 |

### 缺失率 Top 5

| 字段 | 缺失率 |
|---|---:|
| `discharge_record` | 100.0% |
| `procedures` | 41.0% |
| `medications_on_admission` | 12.3% |
| `history_of_present_illness` | 4.4% |
| `past_medical_history` | 3.9% |

## 7. 关键发现与风险

| 级别 | 发现 | 影响 |
|---|---|---|
| P0 | `discharge_record` 在 raw 和 cleaned 中均为 100% 空 | 题型 5（离院指导）完全无数据来源；抽取阶段 DS 章节解析未提取到 Follow-up Instructions |
| P1 | `investigation_orders.poe_detail` 99.99% 为空 | 检查医嘱仅有分类标签（如 Lab）无明细；题型 1 须依赖 `investigation_reports` |
| P1 | 157 条就诊 `chief_complaint` 为空 | 数据契约规定主诉缺失应排除，但清洗产物中仍保留 |
| P2 | `procedures` 缺失率 41.0% | 41% 就诊无手术/操作记录，影响题型 3 操作类题目 |
| P2 | ICD-9 占 63%、ICD-10 占 37% | 两版编码体系混用，标准化需注意编码映射差异 |
| P3 | 1 位患者最多就诊 51 次 | 长尾分布，评估 LLM 时需注意数据泄漏风险 |

---

## 附：图表清单

- `eda/figures/01_age_sex.png`
- `eda/figures/02_visits_per_patient.png`
- `eda/figures/03_top_diagnoses.png`
- `eda/figures/04_text_length_raw.png`
- `eda/figures/05_entity_count_cleaned.png`
- `eda/figures/06_json_item_counts.png`
- `eda/figures/07_discharge_length.png`