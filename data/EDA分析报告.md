# MIMIC-IV RWD Benchmark — 全量 EDA 报告

> 数据源: `rwd_benchmark_visits.jsonl` (27.37 GB, 320,267 条 visit)
> 生成时间: 2026-08-07

---

## 1. 总览

| 指标 | 数值 |
|---|---|
| 总 visit 数 | 320,267 |
| 文件大小 | 27.37 GB |
| 平均每条 | 90 KB |
| 年龄 (均值/中位) | 61.7 / 63 |
| 性别 (F/M) | 163,476 / 156,791 (51.0% / 49.0%) |
| Triage 覆盖 | 145,607 (45.5%) |
| ICU 入住 | 62,886 (19.6%) |
| DRG 覆盖 | 274,250 (85.6%) |
| 检验项目/visit | 均值 51.8, 中位 50 |
| 合并症/visit | 均值 11.6, 中位 10 |

## 2. 人口学

| 年龄段 | 人数 | 占比 |
|---|---|---|
| 18-29 | 19,674 | 6.1% |
| 30-44 | 39,088 | 12.2% |
| 45-59 | 77,139 | 24.1% |
| 60-74 | 98,428 | 30.7% |
| 75+ | 85,938 | 26.8% |

**入院类型 Top 5:**

- EW EMER.: 138,973 (43.4%)
- OBSERVATION ADMIT: 49,635 (15.5%)
- EU OBSERVATION: 31,069 (9.7%)
- SURGICAL SAME DAY ADMISSION: 28,871 (9.0%)
- URGENT: 28,715 (9.0%)

## 3. 生命体征

| 指标 | n | 填充率 | 均值 | 中位 | 范围 |
|---|---|---|---|---|---|
| 体温(°F) | 135,645 | 42.4% | 98.1 | 98 | 0-978 |
| 心率 | 138,709 | 43.3% | 86.6 | 85 | 8-1228 |
| 呼吸频率 | 137,144 | 42.8% | 18.1 | 18 | 1-1820 |
| 血氧(%) | 137,137 | 42.8% | 97.9 | 98 | 0-9322 |
| 收缩压 | 138,431 | 43.2% | 134.5 | 132 | 1-19734 |
| 舒张压 | 138,093 | 43.1% | 78.1 | 75 | 0-74810 |
| ESI | 145,543 | 45.4% | 2.3 | 2 | 1-5 |

> Triage 仅 ED 就诊有数据，非 ED 入院无 triage 属数据结构性特征。

## 4. 叙事文本

| 字段 | 填充率 | 中位长度 | 最大长度 |
|---|---|---|---|
| 主诉 | 320,267 (100.0%) | 19 | 8,635 |
| 现病史 | 316,608 (98.9%) | 1,299 | 19,717 |
| 既往史 | 304,858 (95.2%) | 240 | 21,778 |
| 入院用药 | 302,066 (94.3%) | 310 | 26,568 |
| 过敏史 | 320,267 (100.0%) | 61 | 927 |
| 体格检查 | 301,756 (94.2%) | 810 | 14,018 |
| 出院小结全文 | 320,267 (100.0%) | 9,879 | 58,596 |
| 住院经过 | 0 (0.0%) | 0 | 0 |
| 出院指导 | 0 (0.0%) | 0 | 0 |

## 5. 诊断

**ICD 版本:** ICD-9-CM 203,803 (63.6%), ICD-10-CM 116,464 (36.4%)

**合并症:** 每条 visit 0-56 个其他诊断，均值 11.6，中位 10

**主诊断 Top 15:**

| # | 诊断名称 | 人数 | 占比 |
|---|---|---|---|
| 1 | Acute kidney failure, unspecified | 4,671 | 1.46% |
| 2 | Encounter for antineoplastic chemotherapy | 4,403 | 1.37% |
| 3 | Coronary atherosclerosis of native coronary artery | 3,835 | 1.20% |
| 4 | Urinary tract infection, site not specified | 3,751 | 1.17% |
| 5 | Pneumonia, organism unspecified | 3,239 | 1.01% |
| 6 | Other chest pain | 3,073 | 0.96% |
| 7 | Sepsis, unspecified organism | 2,860 | 0.89% |
| 8 | Unspecified septicemia | 2,760 | 0.86% |
| 9 | Subendocardial infarction, initial episode of care | 2,590 | 0.81% |
| 10 | Syncope and collapse | 2,421 | 0.76% |
| 11 | Acute pancreatitis | 2,393 | 0.75% |
| 12 | Acute on chronic diastolic heart failure | 2,061 | 0.64% |
| 13 | Atrial fibrillation | 1,996 | 0.62% |
| 14 | Non-ST elevation (NSTEMI) myocardial infarction | 1,917 | 0.60% |
| 15 | Other postoperative infection | 1,869 | 0.58% |

## 6. 检查检验

**实验室检验:** 每条 visit 0-247 个项目，均值 51.8

**最常见检验 Top 15:**

| # | 检验名称 | 出现次数 |
|---|---|---|
| 1 | Hematocrit | 300,867 |
| 2 | Hemoglobin | 298,936 |
| 3 | Platelet Count | 298,679 |
| 4 | White Blood Cells | 298,555 |
| 5 | MCHC | 298,439 |
| 6 | MCH | 298,436 |
| 7 | MCV | 298,436 |
| 8 | Red Blood Cells | 298,436 |
| 9 | RDW | 298,435 |
| 10 | Glucose | 298,361 |
| 11 | Creatinine | 298,012 |
| 12 | Urea Nitrogen | 296,865 |
| 13 | Potassium | 296,573 |
| 14 | Sodium | 296,160 |
| 15 | Chloride | 296,086 |


**微生物学:** 195,119 条 visit 有记录 (60.9%)

Top 5 标本类型: BLOOD CULTURE(462,999), URINE(415,971), SPUTUM(134,844), SWAB(107,877), STOOL(104,976)

Top 5 病原体: ESCHERICHIA COLI(177,081), STAPH AUREUS COAG +(105,193), KLEBSIELLA PNEUMONIAE(59,648), PSEUDOMONAS AERUGINOSA(42,050), STAPHYLOCOCCUS, COAGULASE NEGATIVE(31,925)


**影像报告:** 264,265 条 visit 有记录 (82.5%)

Top 5 检查类型: CHEST (PORTABLE AP)(39,213), CHEST (PA AND LAT)(25,095), CHEST RADIOGRAPH(14,388), CT HEAD W/O CONTRAST(12,441), CT HEAD W/O CONTRAST Q111 CT HEAD(11,253)

## 7. 治疗处置

| 类别 | 有记录 visit 数 | 覆盖率 | 每visit均值 |
|---|---|---|---|
| 处方 | 319,712 | 99.8% | 44.4 |
| 药房医嘱 | 319,712 | 99.8% | 39.0 |
| 给药记录 | 153,284 | 47.9% | 73.1 |
| 操作ICD | 187,305 | 58.5% | 1.8 |

**最常处方药物 Top 10:**

- Insulin: 565,939
- 0.9% Sodium Chloride: 537,938
- Sodium Chloride 0.9%  Flush: 471,481
- Potassium Chloride: 434,178
- Acetaminophen: 393,457
- Furosemide: 307,011
- Heparin: 293,559
- 5% Dextrose: 274,347
- Magnesium Sulfate: 266,312
- Docusate Sodium: 254,935

## 8. 去向与转科

**出院去向 Top 5:**

- HOME: 126,932 (39.6%)
- HOME HEALTH CARE: 70,609 (22.0%)
- UNKNOWN: 46,087 (14.4%)
- SKILLED NURSING FACILITY: 41,187 (12.9%)
- REHAB: 10,240 (3.2%)

**入院来源 Top 5:**

- EMERGENCY ROOM: 170,866 (53.4%)
- PHYSICIAN REFERRAL: 80,355 (25.1%)
- TRANSFER FROM HOSPITAL: 32,589 (10.2%)
- WALK-IN/SELF REFERRAL: 10,559 (3.3%)
- CLINIC REFERRAL: 8,554 (2.7%)

**主要负责科室 Top 8:**

- MED: 138,736
- SURG: 32,987
- CMED: 29,556
- OMED: 20,716
- NMED: 17,940
- ORTHO: 16,660
- NSURG: 10,611
- CSURG: 9,897


**转科路径:** 每条 visit 均值 3.8 步，最大 24 步

## 9. 图表索引

| 编号 | 文件 | 内容 |
|---|---|---|
| 01 | demographics.png | 人口学特征（年龄/性别/入院类型/年龄段） |
| 02 | vitals.png | 生命体征分布（7项指标+心律） |
| 03 | narrative.png | 叙事文本长度分布（9个字段） |
| 04 | diagnoses.png | 诊断分析（ICD版本/合并症/Top20） |
| 05 | investigations.png | 检查检验（检验项目/微生物/影像） |
| 06 | microbiology_radiology.png | 微生物与影像（标本/病原体/检查类型） |
| 07 | treatments.png | 治疗处置（5类记录+Top20药物） |
| 08 | disposition.png | 去向转科（出院/入院/科室/DRG/ICU） |
| 09 | completeness.png | 数据完整性矩阵（20字段填充率） |
| 10 | correlation.png | Visit级指标相关性热力图 |
| 11 | data_density.png | 数据密度与年龄趋势 |
| 12 | disease_chapters.png | ICD章节分布总览 |
| 13 | chapter_by_age.png | 章节×年龄堆叠条形图 |
| 14 | chapter_by_sex.png | 章节×性别对比图 |
| 15 | top_dx_per_chapter.png | 各章节Top5具体诊断 |
| 16 | comorbidity.png | 合并症分布+Top20 |
| 17 | top50_diagnoses.png | 主诊断Top50 |
| 18 | chapter_age_heatmap.png | 章节×年龄热力图 |
