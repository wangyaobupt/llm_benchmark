# MIMIC 原始住院归档 10,000例 EDA

> 生成时间：2026-08-10T09:57:17

## 核心规模

| 指标 | 数值 |
|---|---:|
| 住院记录 | 10,000 |
| 唯一患者 | 8,160 |
| JSONL体积 | 3.166 GiB |
| 平均每次住院 | 332.0 KiB |
| P50 / P95 / P99 | 125.9 / 1195.4 / 3380.5 KiB |
| 最大单次住院 | 22.49 MiB |

## 冠状动脉疾病谱样本

筛选定义：ICD-9 410-414 / ICD-10 I20-I25。编码仅用于离线队列识别。

| 指标 | 数值 |
|---|---:|
| 样本内相关住院 | 1,938 |
| 样本内相关患者 | 1,611 |
| 平均每次住院 | 498.5 KiB |
| P50 / P95 | 210.8 / 1715.1 KiB |

## 模块覆盖

| 模块 | 非空住院比例 |
|---|---:|
| `mimic_iv_hosp` | 100.00% |
| `mimic_iv_note` | 68.73% |
| `mimic_iv_icu` | 15.08% |
| `mimic_iv_ed` | 37.93% |

## 逐表统计

| 表 | 总行数 | 非空住院 | 覆盖率 | 平均行数/住院 |
|---|---:|---:|---:|---:|
| `mimic_iv_hosp.patients` | 10,000 | 10,000 | 100.00% | 1.00 |
| `mimic_iv_hosp.admissions` | 10,000 | 10,000 | 100.00% | 1.00 |
| `mimic_iv_hosp.transfers` | 36,712 | 9,999 | 99.99% | 3.67 |
| `mimic_iv_hosp.services` | 10,843 | 10,000 | 100.00% | 1.08 |
| `mimic_iv_hosp.labevents` | 1,580,399 | 8,134 | 81.34% | 158.04 |
| `mimic_iv_hosp.microbiologyevents` | 33,833 | 3,625 | 36.25% | 3.38 |
| `mimic_iv_hosp.poe` | 963,535 | 9,858 | 98.58% | 96.35 |
| `mimic_iv_hosp.poe_detail` | 157,630 | 9,794 | 97.94% | 15.76 |
| `mimic_iv_hosp.pharmacy` | 326,592 | 8,403 | 84.03% | 32.66 |
| `mimic_iv_hosp.prescriptions` | 372,592 | 8,403 | 84.03% | 37.26 |
| `mimic_iv_hosp.emar` | 769,462 | 5,381 | 53.81% | 76.95 |
| `mimic_iv_hosp.emar_detail` | 1,565,496 | 5,381 | 53.81% | 156.55 |
| `mimic_iv_hosp.diagnoses_icd` | 115,525 | 9,990 | 99.90% | 11.55 |
| `mimic_iv_hosp.procedures_icd` | 15,638 | 5,170 | 51.70% | 1.56 |
| `mimic_iv_hosp.hcpcsevents` | 3,447 | 2,733 | 27.33% | 0.34 |
| `mimic_iv_hosp.drgcodes` | 13,842 | 7,166 | 71.66% | 1.38 |
| `mimic_iv_icu.icustays` | 1,686 | 1,508 | 15.08% | 0.17 |
| `mimic_iv_icu.datetimeevents` | 190,122 | 1,497 | 14.97% | 19.01 |
| `mimic_iv_icu.ingredientevents` | 268,287 | 1,349 | 13.49% | 26.83 |
| `mimic_iv_icu.inputevents` | 204,568 | 1,350 | 13.50% | 20.46 |
| `mimic_iv_icu.outputevents` | 99,793 | 1,469 | 14.69% | 9.98 |
| `mimic_iv_icu.procedureevents` | 14,730 | 1,348 | 13.48% | 1.47 |
| `mimic_iv_ed.edstays` | 3,808 | 3,793 | 37.93% | 0.38 |
| `mimic_iv_ed.triage` | 3,808 | 3,793 | 37.93% | 0.38 |
| `mimic_iv_ed.vitalsign` | 19,643 | 3,709 | 37.09% | 1.96 |
| `mimic_iv_ed.diagnosis` | 7,791 | 3,781 | 37.81% | 0.78 |
| `mimic_iv_ed.medrecon` | 34,737 | 3,024 | 30.24% | 3.47 |
| `mimic_iv_ed.pyxis` | 20,660 | 3,179 | 31.79% | 2.07 |
| `mimic_iv_note.discharge` | 6,059 | 6,059 | 60.59% | 0.61 |
| `mimic_iv_note.discharge_detail` | 3,446 | 3,446 | 34.46% | 0.34 |
| `mimic_iv_note.radiology` | 21,212 | 5,689 | 56.89% | 2.12 |
| `mimic_iv_note.radiology_detail` | 56,995 | 5,688 | 56.88% | 5.70 |

## 原始时间字段完整性

| 字段 | 非空 | 空值 | 空值率 |
|---|---:|---:|---:|
| `mimic_iv_ed.edstays.intime` | 3,808 | 0 | 0.00% |
| `mimic_iv_ed.edstays.outtime` | 3,808 | 0 | 0.00% |
| `mimic_iv_ed.medrecon.charttime` | 34,737 | 0 | 0.00% |
| `mimic_iv_ed.pyxis.charttime` | 20,660 | 0 | 0.00% |
| `mimic_iv_ed.vitalsign.charttime` | 19,643 | 0 | 0.00% |
| `mimic_iv_hosp.admissions.admittime` | 10,000 | 0 | 0.00% |
| `mimic_iv_hosp.admissions.deathtime` | 222 | 9,778 | 97.78% |
| `mimic_iv_hosp.admissions.dischtime` | 10,000 | 0 | 0.00% |
| `mimic_iv_hosp.admissions.edouttime` | 7,027 | 2,973 | 29.73% |
| `mimic_iv_hosp.admissions.edregtime` | 7,027 | 2,973 | 29.73% |
| `mimic_iv_hosp.emar.charttime` | 769,462 | 0 | 0.00% |
| `mimic_iv_hosp.emar.scheduletime` | 768,896 | 566 | 0.07% |
| `mimic_iv_hosp.emar.storetime` | 769,462 | 0 | 0.00% |
| `mimic_iv_hosp.hcpcsevents.chartdate` | 3,447 | 0 | 0.00% |
| `mimic_iv_hosp.labevents.charttime` | 1,580,399 | 0 | 0.00% |
| `mimic_iv_hosp.labevents.storetime` | 1,571,662 | 8,737 | 0.55% |
| `mimic_iv_hosp.microbiologyevents.chartdate` | 33,833 | 0 | 0.00% |
| `mimic_iv_hosp.microbiologyevents.charttime` | 33,833 | 0 | 0.00% |
| `mimic_iv_hosp.microbiologyevents.storedate` | 33,569 | 264 | 0.78% |
| `mimic_iv_hosp.microbiologyevents.storetime` | 33,489 | 344 | 1.02% |
| `mimic_iv_hosp.patients.dod` | 2,617 | 7,383 | 73.83% |
| `mimic_iv_hosp.pharmacy.entertime` | 326,592 | 0 | 0.00% |
| `mimic_iv_hosp.pharmacy.expirationdate` | 472 | 326,120 | 99.86% |
| `mimic_iv_hosp.pharmacy.starttime` | 326,119 | 473 | 0.14% |
| `mimic_iv_hosp.pharmacy.stoptime` | 324,671 | 1,921 | 0.59% |
| `mimic_iv_hosp.pharmacy.verifiedtime` | 326,483 | 109 | 0.03% |
| `mimic_iv_hosp.poe.ordertime` | 963,535 | 0 | 0.00% |
| `mimic_iv_hosp.prescriptions.starttime` | 372,119 | 473 | 0.13% |
| `mimic_iv_hosp.prescriptions.stoptime` | 371,917 | 675 | 0.18% |
| `mimic_iv_hosp.procedures_icd.chartdate` | 15,638 | 0 | 0.00% |
| `mimic_iv_hosp.services.transfertime` | 10,843 | 0 | 0.00% |
| `mimic_iv_hosp.transfers.intime` | 36,712 | 0 | 0.00% |
| `mimic_iv_hosp.transfers.outtime` | 26,713 | 9,999 | 27.24% |
| `mimic_iv_icu.datetimeevents.charttime` | 190,122 | 0 | 0.00% |
| `mimic_iv_icu.datetimeevents.storetime` | 190,122 | 0 | 0.00% |
| `mimic_iv_icu.icustays.intime` | 1,686 | 0 | 0.00% |
| `mimic_iv_icu.icustays.outtime` | 1,686 | 0 | 0.00% |
| `mimic_iv_icu.ingredientevents.endtime` | 268,287 | 0 | 0.00% |
| `mimic_iv_icu.ingredientevents.starttime` | 268,287 | 0 | 0.00% |
| `mimic_iv_icu.ingredientevents.storetime` | 268,287 | 0 | 0.00% |
| `mimic_iv_icu.inputevents.endtime` | 204,568 | 0 | 0.00% |
| `mimic_iv_icu.inputevents.starttime` | 204,568 | 0 | 0.00% |
| `mimic_iv_icu.inputevents.storetime` | 204,568 | 0 | 0.00% |
| `mimic_iv_icu.outputevents.charttime` | 99,793 | 0 | 0.00% |
| `mimic_iv_icu.outputevents.storetime` | 99,793 | 0 | 0.00% |
| `mimic_iv_icu.procedureevents.endtime` | 14,730 | 0 | 0.00% |
| `mimic_iv_icu.procedureevents.starttime` | 14,730 | 0 | 0.00% |
| `mimic_iv_icu.procedureevents.storetime` | 14,730 | 0 | 0.00% |
| `mimic_iv_note.discharge.charttime` | 6,059 | 0 | 0.00% |
| `mimic_iv_note.discharge.storetime` | 6,059 | 0 | 0.00% |
| `mimic_iv_note.radiology.charttime` | 21,212 | 0 | 0.00% |
| `mimic_iv_note.radiology.storetime` | 21,212 | 0 | 0.00% |

## 最大单次住院记录

| subject_id | hadm_id | 体积 MiB |
|---|---|---:|
| `17299293` | `21067433` | 22.49 |
| `17536222` | `26728411` | 22.23 |
| `18102151` | `28712213` | 14.46 |
| `11830663` | `26201467` | 11.69 |
| `16304286` | `23490839` | 11.42 |
| `10850048` | `22784596` | 11.24 |
| `11491355` | `25397562` | 10.98 |
| `12457358` | `29246116` | 10.72 |
| `14836177` | `28102452` | 10.56 |
| `16294509` | `29057858` | 10.27 |
| `17629414` | `27617072` | 10.22 |
| `14610595` | `21381296` | 9.93 |
| `10138761` | `27536140` | 9.48 |
| `14634306` | `24969636` | 8.89 |
| `16897045` | `24708605` | 8.75 |
| `16130199` | `26785202` | 8.64 |
| `10347675` | `26643356` | 8.63 |
| `19059849` | `22349879` | 7.82 |
| `13270755` | `20412909` | 7.75 |
| `11411781` | `25420493` | 7.75 |

## 完整性

- Schema失败记录：0
- 出现 `chartevents` 的记录：0
- 未知顶层字段：{}
- 父子孤立行：{"poe_detail": 0, "emar_detail": 0, "ed.triage": 0, "ed.vitalsign": 0, "ed.diagnosis": 0, "ed.medrecon": 0, "ed.pyxis": 0, "discharge_detail": 0, "radiology_detail": 0}

## 分片

| 分片 | 记录数 | 体积 GiB |
|---:|---:|---:|
| 0 | 1,000 | 0.306 |
| 1 | 1,000 | 0.321 |
| 2 | 1,000 | 0.372 |
| 3 | 1,000 | 0.294 |
| 4 | 1,000 | 0.300 |
| 5 | 1,000 | 0.317 |
| 6 | 1,000 | 0.320 |
| 7 | 1,000 | 0.295 |
| 8 | 1,000 | 0.323 |
| 9 | 1,000 | 0.318 |
