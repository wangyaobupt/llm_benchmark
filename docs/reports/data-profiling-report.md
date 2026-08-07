# 数据画像报告（Episode 聚合层）

> 自动生成，仅含汇总计数、分布与分位数，不含患者级数据。

## 维度 1：Episode 资料覆盖度

### 各数据类型覆盖率（占 768,125 个 episode 的百分比）

| 数据类型 | 有此数据的 episode 数 | 覆盖率 |
|---|---:|---:|
| 主诉 (has_chief_complaint) | 424,490 | 55.3% |
| 分诊生命体征 (has_triage_vitals) | 408,782 | 53.2% |
| 连续生命体征 (has_serial_vitals) | 407,675 | 53.1% |
| 化验 (has_laboratory) | 628,847 | 81.9% |
| 微生物 (has_microbiology) | 323,068 | 42.1% |
| 放射报告 (has_radiology) | 437,901 | 57.0% |
| 医嘱 (has_orders) | 538,615 | 70.1% |
| 处方 (has_prescriptions) | 463,328 | 60.3% |
| 用药执行 (has_medication_administration) | 292,429 | 38.1% |
| 操作 (has_procedures) | 418,715 | 54.5% |
| 诊断 (has_diagnoses) | 767,352 | 99.9% |
| 处置 (has_disposition) | 424,512 | 55.3% |
| 出院小结 (has_discharge_summary) | 331,732 | 43.2% |

### 每 episode 拥有的数据类型数量分布

| 类型数 | episode 数 | 占比 |
|---:|---:|---:|
| 0 | 48 | 0.0% |
| 1 | 392 | 0.1% |
| 2 | 2,108 | 0.3% |
| 3 | 9,845 | 1.3% |
| 4 | 28,279 | 3.7% |
| 5 | 109,201 | 14.2% |
| 6 | 157,374 | 20.5% |
| 7 | 148,778 | 19.4% |
| 8 | 106,721 | 13.9% |
| 9 | 31,381 | 4.1% |
| 10 | 22,362 | 2.9% |
| 11 | 39,320 | 5.1% |
| 12 | 63,953 | 8.3% |
| 13 | 48,363 | 6.3% |

## 维度 2：Episode 规模与时长

临床时长（小时）：min=-23, P25=7.0, P50=38.0, P75=101.0, max=12373
- 异短 episode（<1 小时）：2,817
- 异长 episode（>365 天）：1

## 维度 3：时间逻辑一致性

available_time 早于 episode_start 的事件（时间倒挂）：3,575,351
event_time 晚于 clinical_end_time 的事件：1,245,315

## 维度 4：文本完整性

- 总文档数：2,653,148
- 空文本文档：0（0.00%）

### 文本长度分布（按文档类型）

| 类型 | 数量 | P10 | P50 | P90 | 均值 |
|---|---:|---:|---:|---:|---:|
| discharge | 331,793 | 5,676 | 9,847 | 16,159 | 10,551 |
| radiology | 2,321,355 | 378 | 781 | 2,566 | 1,159 |

- 同一 episode 有多份出院小结的 episode 数：0

## 维度 5：数值与单位

- 有 raw_value 但 normalized_value 为 NULL（归一化失败）：429,191,108（53.8% of 797,845,508）

### raw_unit top 15

| raw_unit | 数量 |
|---|---:|
| (NULL) | 442,068,950 |
| mg | 39,232,175 |
| mL | 37,429,205 |
| mmHg | 34,642,251 |
| % | 34,090,370 |
| mg/dL | 30,774,454 |
| mEq/L | 26,618,467 |
| K/uL | 13,888,780 |
| insp/min | 12,999,774 |
| bpm | 10,582,283 |
| g/dL | 8,100,401 |
| IU/L | 7,317,393 |
| Date | 7,153,915 |
| fL | 6,383,256 |
| sec | 5,547,573 |

## 维度 6：链接质量

### unresolved_reason 分布（timeline_events）

| reason | 数量 |
|---|---:|
| no_temporal_episode | 7,369,355 |
| patient_level_no_encounter_id | 4,333,527 |
| contact_not_found_or_subject_mismatch | 408,978 |
| subject_hadm_mismatch | 493 |
| multiple_temporal_episodes | 258 |

## 维度 7：事件类型分布

| event_type | 数量 | unresolved 数 | unresolved 率 |
|---|---:|---:|---:|
| provider_order | 52,212,109 | 95 | 0.0% |
| medication_administration | 42,808,593 | 1,417,704 | 3.3% |
| icu_observation | 22,728,285 | 0 | 0.0% |
| prescription | 20,292,611 | 0 | 0.0% |
| pharmacy_order | 17,847,567 | 47 | 0.0% |
| laboratory_panel | 17,503,481 | 6,609,618 | 37.8% |
| icu_ingredient_input | 14,253,480 | 0 | 0.0% |
| icu_input | 10,953,713 | 0 | 0.0% |
| icu_datetime_observation | 9,979,761 | 0 | 0.0% |
| diagnosis_code | 6,364,488 | 0 | 0.0% |
| icu_output | 5,359,395 | 0 | 0.0% |
| medication_reconciliation | 2,987,342 | 0 | 0.0% |
| outpatient_measurement_group | 2,916,137 | 2,916,137 | 100.0% |
| transfer | 2,413,581 | 408,978 | 16.9% |
| microbiology_specimen | 1,924,289 | 760,032 | 39.5% |
| ed_medication_dispense | 1,586,053 | 0 | 0.0% |
| ed_vital_signs | 1,564,610 | 0 | 0.0% |
| ed_diagnosis_code | 899,050 | 0 | 0.0% |
| procedure_code | 859,655 | 0 | 0.0% |
| icu_procedure | 808,706 | 0 | 0.0% |
| drg_code | 761,856 | 0 | 0.0% |
| service_transfer | 593,071 | 0 | 0.0% |
| ed_triage | 425,087 | 0 | 0.0% |
| hcpcs_event | 186,074 | 0 | 0.0% |

## 维度 8：患者维度基数核对

- episode_index distinct subject_id：302,861
- 每患者 episode 数：min=1, P50=1.0, P90=5.0, max=360

---

**画像完成。** 根据以上分布判断是否需要数据清洗及清洗重点。