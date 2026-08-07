# MIMIC-IV Episode 聚合输出字段映射文档

> 本文档说明 `G:\Projects\医疗数据集评测-MIMIC\outputs\episodes\` 下各 Parquet
> 输出表的每一字段如何对应 MIMIC-IV 官方源表及其原始列。
>
> 源数据库版本：MIMIC-IV 3.1（hosp + icu）、MIMIC-IV-ED 2.2、MIMIC-IV-Note 2.2

---

## 1. 源表速查

本项目锁定 41 张原始 CSV.GZ，按模块分组如下。

### MIMIC-IV 3.1 / hosp（22 张）

| key | 源路径 | 官方表名 |
|-----|--------|----------|
| patients | mimic-iv-3.1/hosp/patients.csv.gz | patients |
| admissions | mimic-iv-3.1/hosp/admissions.csv.gz | admissions |
| transfers | mimic-iv-3.1/hosp/transfers.csv.gz | transfers |
| services | mimic-iv-3.1/hosp/services.csv.gz | services |
| labevents | mimic-iv-3.1/hosp/labevents.csv.gz | labevents |
| d_labitems | mimic-iv-3.1/hosp/d_labitems.csv.gz | d_labitems |
| microbiologyevents | mimic-iv-3.1/hosp/microbiologyevents.csv.gz | microbiologyevents |
| omr | mimic-iv-3.1/hosp/omr.csv.gz | omr |
| poe | mimic-iv-3.1/hosp/poe.csv.gz | poe |
| poe_detail | mimic-iv-3.1/hosp/poe_detail.csv.gz | poe_detail |
| pharmacy | mimic-iv-3.1/hosp/pharmacy.csv.gz | pharmacy |
| prescriptions | mimic-iv-3.1/hosp/prescriptions.csv.gz | prescriptions |
| emar | mimic-iv-3.1/hosp/emar.csv.gz | emar |
| emar_detail | mimic-iv-3.1/hosp/emar_detail.csv.gz | emar_detail |
| diagnoses_icd | mimic-iv-3.1/hosp/diagnoses_icd.csv.gz | diagnoses_icd |
| d_icd_diagnoses | mimic-iv-3.1/hosp/d_icd_diagnoses.csv.gz | d_icd_diagnoses |
| procedures_icd | mimic-iv-3.1/hosp/procedures_icd.csv.gz | procedures_icd |
| d_icd_procedures | mimic-iv-3.1/hosp/d_icd_procedures.csv.gz | d_icd_procedures |
| hcpcsevents | mimic-iv-3.1/hosp/hcpcsevents.csv.gz | hcpcsevents |
| d_hcpcs | mimic-iv-3.1/hosp/d_hcpcs.csv.gz | d_hcpcs |
| drgcodes | mimic-iv-3.1/hosp/drgcodes.csv.gz | drgcodes |
| provider | mimic-iv-3.1/hosp/provider.csv.gz | provider |

### MIMIC-IV 3.1 / icu（8 张）

| key | 源路径 | 官方表名 |
|-----|--------|----------|
| icustays | mimic-iv-3.1/icu/icustays.csv.gz | icustays |
| chartevents | mimic-iv-3.1/icu/chartevents.csv.gz | chartevents |
| datetimeevents | mimic-iv-3.1/icu/datetimeevents.csv.gz | datetimeevents |
| ingredientevents | mimic-iv-3.1/icu/ingredientevents.csv.gz | ingredientevents |
| inputevents | mimic-iv-3.1/icu/inputevents.csv.gz | inputevents |
| outputevents | mimic-iv-3.1/icu/outputevents.csv.gz | outputevents |
| procedureevents | mimic-iv-3.1/icu/procedureevents.csv.gz | procedureevents |
| d_items | mimic-iv-3.1/icu/d_items.csv.gz | d_items |
| caregiver | mimic-iv-3.1/icu/caregiver.csv.gz | caregiver |

### MIMIC-IV-ED 2.2（6 张）

| key | 源路径 | 官方表名 |
|-----|--------|----------|
| edstays | mimic-iv-ed/ed/edstays.csv.gz | edstays |
| triage | mimic-iv-ed/ed/triage.csv.gz | triage |
| vitalsign | mimic-iv-ed/ed/vitalsign.csv.gz | vitalsign |
| ed_diagnosis | mimic-iv-ed/ed/diagnosis.csv.gz | diagnosis |
| medrecon | mimic-iv-ed/ed/medrecon.csv.gz | medrecon |
| pyxis | mimic-iv-ed/ed/pyxis.csv.gz | pyxis |

### MIMIC-IV-Note 2.2（4 张）

| key | 源路径 | 官方表名 |
|-----|--------|----------|
| discharge | mimic-iv-note-2.2/note/discharge.csv.gz | discharge |
| discharge_detail | mimic-iv-note-2.2/note/discharge_detail.csv.gz | discharge_detail |
| radiology | mimic-iv-note-2.2/note/radiology.csv.gz | radiology |
| radiology_detail | mimic-iv-note-2.2/note/radiology_detail.csv.gz | radiology_detail |

---

## 2. episode_index — 病例索引

每行 = 一次临床就诊 episode（住院或独立急诊），768,125 行。

| 输出字段 | 类型 | 来源表 | 官方原始列 | 派生说明 |
|----------|------|--------|-----------|----------|
| episode_id | VARCHAR | 项目生成 | — | 住院：`'H:' + hadm_id`；独立急诊：`'E:' + stay_id` |
| episode_type | VARCHAR | admissions / edstays | — | 住院 = `'hospital'`；独立急诊 = `'emergency_department'` |
| subject_id | BIGINT | admissions.subject_id / edstays.subject_id | subject_id | 原值，无修改 |
| hadm_id | BIGINT | admissions.hadm_id | hadm_id | 独立急诊为 NULL |
| episode_start_time | TIMESTAMP | admissions.admittime / edstays.intime | admittime / intime | 如急诊先于住院且匹配，取急诊 intime |
| clinical_end_time | TIMESTAMP | admissions.dischtime / deathtime / edstays.outtime | dischtime / deathtime / outtime | 有 deathtime 且早于 dischtime 时取 deathtime |
| administrative_end_time | TIMESTAMP | admissions.dischtime | dischtime | 住院行政出院时间 |
| outcome_type | VARCHAR | admissions.hospital_expire_flag / deathtime / edstays.disposition | hospital_expire_flag / deathtime / disposition | 死亡= `'death'`；出院=`'discharge'`；急诊取 disposition |
| linked_ed_contact_count | BIGINT | edstays（COUNT by hadm_id） | stay_id | 该住院关联的急诊接触次数 |
| icu_contact_count | BIGINT | icustays（COUNT by hadm_id） | stay_id | 该住院期间 ICU 转入次数 |
| transfer_contact_count | BIGINT | transfers（COUNT by hadm_id） | transfer_id | 该住院期间科室转移次数 |
| source_versions | VARCHAR | — | — | 固定值 `mimic-iv=3.1;mimic-iv-ed=2.2;mimic-iv-note=2.2` |
| admission_link_status | VARCHAR | edstays LEFT JOIN admissions | — | `matched` / `hadm_not_found_or_subject_mismatch` / `no_hadm_id` |
| candidate_hadm_id | BIGINT | edstays.hadm_id | hadm_id | 急诊记录中携带的 hadm_id（可能不匹配） |
| admission_type | VARCHAR | admissions.admission_type | admission_type | 如 EMERGENCY / URGENT / ELECTIVE 等 |
| admission_location | VARCHAR | admissions.admission_location | admission_location | 如 EMERGENCY ROOM ADMIT 等 |
| discharge_location | VARCHAR | admissions.discharge_location | discharge_location | 如 HOME / SNF / DEAD-EXPIRED 等 |
| hospital_expire_flag | INTEGER | admissions.hospital_expire_flag | hospital_expire_flag | 1 = 院内死亡 |

---

## 3. care_contacts — 诊疗接触点

每行 = 一次 care contact（住院段 / 急诊段 / ICU 段 / 科室转移），3,070,176 行。

| 输出字段 | 类型 | 来源表 | 官方原始列 | 派生说明 |
|----------|------|--------|-----------|----------|
| contact_id | VARCHAR | 项目生成 | — | 前缀标识来源：`IP:` 住院 / `ED:` 急诊 / `ICU:` 重症监护 / `TR:` 转移 |
| episode_id | VARCHAR | 关联 episode_index | — | 该接触归属的 episode |
| subject_id | BIGINT | admissions / edstays / icustays / transfers | subject_id | 原值 |
| contact_type | VARCHAR | — | — | `inpatient` / `emergency_department` / `icu` / `transfer` |
| hadm_id | BIGINT | admissions.hadm_id / edstays.hadm_id | hadm_id | 该接触关联的住院 ID |
| stay_id | BIGINT | edstays.stay_id / icustays.stay_id | stay_id | 急诊 stay_id 或 ICU stay_id |
| transfer_id | BIGINT | transfers.transfer_id | transfer_id | 科室转移 ID |
| start_time | TIMESTAMP | admissions.admittime / edstays.intime / icustays.intime / transfers.intime | — | 接触开始时间 |
| end_time | TIMESTAMP | admissions.dischtime / edstays.outtime / icustays.outtime / transfers.outtime | — | 接触结束时间 |
| link_method | VARCHAR | — | — | 固定 `native_link`（均有原生关联键） |
| source_table | VARCHAR | — | — | 如 `mimic-iv-3.1/hosp/admissions` |
| contact_sequence | BIGINT | ROW_NUMBER | — | episode 内按 start_time 排序序号 |

---

## 4. timeline_events — 时间线事件

每行 = 一个标准化临床事件（化验 / 医嘱 / 给药 / 观察 / 诊断等），238,228,994 行。

| 输出字段 | 类型 | 来源表 | 官方原始列 | 派生说明 |
|----------|------|--------|-----------|----------|
| event_id | VARCHAR | 项目生成 | — | 前缀+原生主键或 MD5 哈希（见下方 event_type 映射表） |
| event_group_id | VARCHAR | 项目生成 | — | 同组事件共享 ID（如同一 charttime 的 ICU 观察批次） |
| episode_id | VARCHAR | 通过关联计算 | — | 原生关联成功 = 对应 episode_id；否则经时间窗唯一匹配或 NULL |
| contact_id | VARCHAR | 通过原生 contact 关联 | — | 对应 care_contacts.contact_id |
| subject_id | BIGINT | 各源表 | subject_id | 原值 |
| event_type | VARCHAR | 项目分类 | — | 标准化事件类型（见下方映射表） |
| event_subtype | VARCHAR | 各源表派生 | — | 事件子类型（如 ICD 版本、药品名、科室名） |
| event_time | TIMESTAMP | 各源表时间列 | charttime / ordertime / starttime / intime 等 | 事件发生时间（可能为 NULL，如诊断编码） |
| available_time | TIMESTAMP | 各源表时间列 | storetime / verifiedtime / ordertime | 信息可用时间（决策时点） |
| recorded_time | TIMESTAMP | 各源表时间列 | storetime | 记录入库时间 |
| start_time | TIMESTAMP | 各源表时间列 | starttime / intime | 持续型事件起始时间 |
| end_time | TIMESTAMP | 各源表时间列 | stoptime / outtime / endtime | 持续型事件结束时间 |
| time_precision | VARCHAR | 项目生成 | — | `timestamp` / `date` / `unknown` / `encounter_start_proxy` / `encounter_end_proxy` |
| status | VARCHAR | 各源表状态列 | event_txt / transaction_type / statusdescription / warning 等 | 事件状态文本 |
| decision_evidence_level | VARCHAR | 项目生成 | — | `observed_decision`（实时记录）/ `post_episode_only`（回顾性编码） |
| link_status | VARCHAR | 关联计算 | — | `native_link`（94.5%）/ `unique_temporal_link`（1.0%）/ `unresolved`（5.5%） |
| normalization_status | VARCHAR | — | — | 固定 `raw_mapped`（原始映射，未做单位标准化） |
| unresolved_reason | VARCHAR | 关联计算 | — | 无法关联时的具体原因（见下方枚举） |
| native_hadm_id | BIGINT | 各源表 | hadm_id | 事件原始携带的 hadm_id（可能为 NULL） |
| native_contact_id | VARCHAR | 项目生成 | — | 事件原始携带的 contact ID（前缀+stay_id 等） |
| candidate_episode_count | BIGINT | 时间窗匹配计算 | — | 当无原生 ID 时，时间窗内匹配到的 episode 数 |
| source_table | VARCHAR | — | — | 如 `mimic-iv-3.1/icu/chartevents` |
| source_version | VARCHAR | — | — | `3.1` 或 `2.2` |

### 4.1 event_type 与官方源表映射

| event_type | 源表（官方） | event_id 前缀 | 原生主键 / 哈希基础 |
|------------|-------------|---------------|---------------------|
| transfer | hosp.transfers | `TRANSFER:` | transfer_id |
| service_transfer | hosp.services | `SERVICE:` (MD5) | subject_id + hadm_id + transfertime + curr_service |
| provider_order | hosp.poe | `POE:` | poe_id |
| pharmacy_order | hosp.pharmacy | `PHARM:` | pharmacy_id |
| prescription | hosp.prescriptions | (MD5) | subject_id + pharmacy_id + poe_seq + drug + starttime |
| medication_administration | hosp.emar | `EMAR:` | emar_id |
| laboratory_panel | hosp.labevents | (MD5) | subject_id + hadm_id + specimen_id + charttime |
| microbiology_specimen | hosp.microbiologyevents | (MD5) | subject_id + hadm_id + micro_specimen_id + chartdate |
| diagnosis_code | hosp.diagnoses_icd + d_icd_diagnoses | (MD5) | subject_id + hadm_id + seq_num + icd_code + icd_version |
| procedure_code | hosp.procedures_icd + d_icd_procedures | (MD5) | subject_id + hadm_id + seq_num + icd_code + icd_version |
| hcpcs_event | hosp.hcpcsevents + d_hcpcs | (MD5) | subject_id + hadm_id + chartdate + seq_num + hcpcs_cd |
| drg_code | hosp.drgcodes | (MD5) | subject_id + hadm_id + drg_type + drg_code |
| ed_triage | ed.triage + ed.edstays | `EDTRIAGE:` | stay_id |
| ed_vital_signs | ed.vitalsign | (MD5) | subject_id + stay_id + charttime |
| ed_diagnosis_code | ed.diagnosis + ed.edstays | (MD5) | subject_id + stay_id + seq_num + icd_code |
| medication_reconciliation | ed.medrecon | (MD5) | subject_id + stay_id + charttime + etc_rn + name |
| ed_medication_dispense | ed.pyxis | (MD5) | subject_id + stay_id + charttime + med_rn + gsn_rn + name |
| icu_observation | icu.chartevents + icu.d_items | `ICUCHART:` (分组) | subject_id + stay_id + charttime（同时间合并为一组） |
| icu_datetime_observation | icu.datetimeevents + icu.d_items | (MD5) | subject_id + stay_id + charttime + itemid + value |
| icu_ingredient_input | icu.ingredientevents + icu.d_items | (MD5) | subject_id + stay_id + orderid + itemid + starttime |
| icu_input | icu.inputevents + icu.d_items | (MD5) | subject_id + stay_id + orderid + itemid + starttime |
| icu_output | icu.outputevents + icu.d_items | (MD5) | subject_id + stay_id + charttime + itemid + value |
| icu_procedure | icu.procedureevents + icu.d_items | (MD5) | subject_id + stay_id + orderid + itemid + starttime |

### 4.2 link_status 枚举

| 值 | 含义 | 占比 |
|----|------|------|
| native_link | 通过 hadm_id / stay_id / transfer_id 等原生 ID 关联到 episode | 94.5% |
| unique_temporal_link | 无原生就诊 ID，但时间窗内唯一匹配到一个 episode | 1.0% |
| unresolved | 无法确定归属 episode（保留在时间线中但 episode_id 为 NULL） | 5.5% |

### 4.3 unresolved_reason 枚举

| 值 | 含义 |
|----|------|
| contact_not_found_or_subject_mismatch | 有 contact_id 但在 care_contacts 中未找到或 subject_id 不匹配 |
| hadm_not_found | 有 hadm_id 但在 admissions 中未找到 |
| subject_hadm_mismatch | hadm_id 存在但 subject_id 不匹配 |
| patient_level_no_encounter_id | 无 hadm_id / stay_id，且不允许时间窗匹配 |
| no_temporal_episode | 无 ID 且时间窗内无任何 episode |
| multiple_temporal_episodes | 无 ID 且时间窗内有多个 episode（无法唯一归属） |

---

## 5. event_items — 事件明细

每行 = 事件内的一条原子数据项（一个化验值 / 一条给药记录 / 一个生命体征），892,146,354 行。

| 输出字段 | 类型 | 来源表 | 官方原始列 | 派生说明 |
|----------|------|--------|-----------|----------|
| item_event_id | VARCHAR | 项目生成 | — | 源表名前缀 + 原生主键 + 物理行号 |
| event_id | VARCHAR | 关联 timeline_events | — | 父事件 ID |
| native_row_key | VARCHAR | 各源表 | — | `列名=值` 格式的原始行标识（如 `labevent_id=12345`） |
| concept_id | VARCHAR | 各源表 | itemid / icd_code / ndc / gsn / hcpcs_cd 等 | 概念标识符（保留原始编码系统） |
| concept_name | VARCHAR | d_labitems / d_items / d_icd_* / 原始列 | label / long_title / medication / short_description 等 | 概念人类可读名称 |
| raw_code | VARCHAR | 各源表 | 同 concept_id 或原始编码 | 原始编码（未映射到标准术语） |
| raw_value | VARCHAR | 各源表 | value / valuenum / dose_val_rx / amount / text 等 | 原始值（保留字符串表示） |
| raw_unit | VARCHAR | 各源表 | valueuom / dose_unit_rx / amountuom / route 等 | 原始单位 |
| normalized_value | DOUBLE | — | — | NULL（当前阶段不做单位标准化） |
| normalized_unit | VARCHAR | — | — | NULL |
| flag | VARCHAR | labevents.flag / chartevents.warning | flag / warning | 异常标记（如 ABNORMAL / FINAL 等） |
| item_ordinal | BIGINT | ROW_NUMBER | — | 同一 event_id 内的明细排序序号 |
| raw_payload | JSON | 各源表完整行 | — | 该明细对应的完整原始行（JSON 序列化，含全部原始列） |
| source_table | VARCHAR | — | — | 如 `mimic-iv-3.1/hosp/labevents` |
| source_version | VARCHAR | — | — | `3.1` 或 `2.2` |

### 5.1 各源表 raw_payload 包含的官方列

| 源表 | raw_payload 字段 |
|------|-----------------|
| labevents | labevent_id, subject_id, hadm_id, specimen_id, itemid, order_provider_id, charttime, storetime, value, valuenum, valueuom, ref_range_lower, ref_range_upper, flag, priority, comments |
| chartevents | subject_id, hadm_id, stay_id, caregiver_id, charttime, storetime, itemid, value, valuenum, valueuom, warning |
| microbiologyevents | microevent_id, subject_id, hadm_id, micro_specimen_id, order_provider_id, chartdate, charttime, spec_itemid, spec_type_desc, test_seq, storedate, storetime, test_itemid, test_name, org_itemid, org_name, isolate_num, quantity, ab_itemid, ab_name, dilution_text, dilution_comparison, dilution_value, interpretation, comments |
| poe_detail | poe_id, poe_seq, subject_id, field_name, field_value |
| emar_detail | subject_id, emar_id, emar_seq, parent_field_ordinal, administration_type, pharmacy_id, barcode_type, reason_for_no_barcode, complete_dose_not_given, dose_due, dose_due_unit, dose_given, dose_given_unit, ... (全部 28 列) |
| inputevents | subject_id, hadm_id, stay_id, caregiver_id, starttime, endtime, storetime, itemid, amount, amountuom, rate, rateuom, orderid, linkorderid, ordercategoryname, ... (全部 24 列) |

---

## 6. documents — 临床文档

每行 = 一份临床文本文档（出院小结 / 放射报告），2,653,148 行。

| 输出字段 | 类型 | 来源表 | 官方原始列 | 派生说明 |
|----------|------|--------|-----------|----------|
| note_id | VARCHAR | discharge.note_id / radiology.note_id | note_id | 原值，全局唯一 |
| subject_id | BIGINT | discharge.subject_id / radiology.subject_id | subject_id | 原值 |
| episode_id | VARCHAR | 关联计算 | — | 原生 hadm_id 匹配或时间窗唯一匹配 |
| contact_id | VARCHAR | — | — | NULL（文档不直接关联到 care_contact） |
| document_type | VARCHAR | — | — | `discharge`（出院小结）/ `radiology`（放射报告） |
| note_type | VARCHAR | discharge.note_type / radiology.note_type | note_type | 原始文档子类型（如 DS / RR 等） |
| note_seq | INTEGER | discharge.note_seq / radiology.note_seq | note_seq | 同一患者同类型的序号 |
| event_time | TIMESTAMP | discharge.charttime / radiology.charttime | charttime | 文档标注的临床时间 |
| available_time | TIMESTAMP | discharge.storetime / radiology.storetime | storetime | 文档入库时间 |
| recorded_time | TIMESTAMP | discharge.storetime / radiology.storetime | storetime | 同 available_time |
| time_precision | VARCHAR | — | — | 固定 `timestamp` |
| text | VARCHAR | discharge.text / radiology.text | text | 完整原文文本（未截断） |
| parent_note_id | VARCHAR | discharge_detail / radiology_detail 中 field_name=`parent_note_id` | — | 该文档是哪份文档的附录 |
| addendum_note_id | VARCHAR | discharge_detail / radiology_detail 中 field_name=`addendum_note_id` | — | 该文档有哪份附录 |
| link_status | VARCHAR | 关联计算 | — | `native_link` / `unique_temporal_link` / `unresolved` |
| unresolved_reason | VARCHAR | 关联计算 | — | `hadm_not_found` / `subject_hadm_mismatch` / `no_temporal_episode` / `multiple_temporal_episodes` |
| native_hadm_id | BIGINT | discharge.hadm_id / radiology.hadm_id | hadm_id | 文档原始携带的 hadm_id |
| candidate_episode_count | BIGINT | 时间窗匹配计算 | — | 无 hadm_id 时时间窗内候选 episode 数 |
| source_table | VARCHAR | — | — | `mimic-iv-note-2.2/note/discharge` 或 `radiology` |
| source_version | VARCHAR | — | — | `2.2` |

---

## 7. evidence_links — 证据锚点

每行 = 一条从原始证据到事件/文档的可追溯链接，901,007,472 行。

| 输出字段 | 类型 | 来源表 | 官方原始列 | 派生说明 |
|----------|------|--------|-----------|----------|
| evidence_link_id | VARCHAR | 项目生成 | — | `EV:` + item_event_id / `DOC:` + MD5 / `NOTEDETAIL:` + MD5 |
| target_type | VARCHAR | — | — | `timeline_event` / `document` |
| target_id | VARCHAR | 关联 | — | event_id 或 note_id |
| evidence_type | VARCHAR | — | — | `structured_row`（结构化明细）/ `text_span`（文本全文）/ `document_metadata`（文档元数据） |
| source_table | VARCHAR | event_items.source_table / documents.source_table | — | 如 `mimic-iv-3.1/hosp/labevents` |
| native_row_key | VARCHAR | event_items.native_row_key | — | 原始行标识 |
| note_id | VARCHAR | documents.note_id | note_id | 仅 document 类型证据有值 |
| section_name | VARCHAR | discharge_detail.field_name / radiology_detail.field_name | field_name | 仅 document_metadata 类型有值（如 `parent_note_id`） |
| character_start | BIGINT | — | — | 文本证据的起始字符位置（结构化证据为 NULL） |
| character_end | BIGINT | LENGTH(text) | — | 文本证据的结束字符位置 |
| relationship_type | VARCHAR | — | — | `supports`（支持事件）/ `contains`（文档包含全文）/ `describes`（元数据描述文档） |
| link_method | VARCHAR | — | — | `inherits_target_link_status`（继承目标事件/文档的关联状态） |

---

## 8. patient_history_refs — 既往史引用

每行 = 一个 episode 的既往史可用性标记，768,125 行。

| 输出字段 | 类型 | 来源表 | 官方原始列 | 派生说明 |
|----------|------|--------|-----------|----------|
| episode_id | VARCHAR | episode_index | — | 当前 episode |
| subject_id | BIGINT | episode_index | subject_id | 患者标识 |
| referenced_type | VARCHAR | — | — | 固定 `patient_timeline_before`（该 episode 前的全部患者历史） |
| referenced_id | VARCHAR | — | — | NULL（引用的是时间线而非单个对象） |
| available_time | TIMESTAMP | episode_index.episode_start_time | — | 既往史截止时间（严格分层边界） |
| history_relation | VARCHAR | — | — | `available_before_episode_start` |

---

## 9. episode_coverage — 资料覆盖度

每行 = 一个 episode 的资料完整性标记，768,125 行。所有布尔字段表示该类型资料是否存在。

| 输出字段 | 类型 | 来源 / 计算逻辑 | 对应官方源表 |
|----------|------|-----------------|-------------|
| episode_id | VARCHAR | episode_index | — |
| has_chief_complaint | BOOLEAN | triage 表中该 episode 有 ≥1 行 chief complaint | ed.triage.chiefcomplaint |
| has_triage_vitals | BOOLEAN | triage 表中该 episode 有 ≥1 行 triage 生命体征 | ed.triage（temperature / heartrate 等） |
| has_serial_vitals | BOOLEAN | timeline_events 中 event_type = `ed_vital_signs` 的行数 > 0 | ed.vitalsign |
| has_laboratory | BOOLEAN | timeline_events 中 event_type = `laboratory_panel` 的行数 > 0 | hosp.labevents |
| has_microbiology | BOOLEAN | timeline_events 中 event_type = `microbiology_specimen` 的行数 > 0 | hosp.microbiologyevents |
| has_radiology | BOOLEAN | documents 中 document_type = `radiology` 的行数 > 0 | note.radiology |
| has_orders | BOOLEAN | timeline_events 中 event_type = `provider_order` 的行数 > 0 | hosp.poe |
| has_prescriptions | BOOLEAN | timeline_events 中 event_type ∈ (`prescription`, `pharmacy_order`) 的行数 > 0 | hosp.prescriptions + hosp.pharmacy |
| has_medication_administration | BOOLEAN | timeline_events 中 event_type = `medication_administration` 的行数 > 0 | hosp.emar |
| has_procedures | BOOLEAN | timeline_events 中 event_type ∈ (`procedure_code`, `icu_procedure`, `hcpcs_event`) 的行数 > 0 | hosp.procedures_icd + icu.procedureevents + hosp.hcpcsevents |
| has_diagnoses | BOOLEAN | timeline_events 中 event_type ∈ (`diagnosis_code`, `ed_diagnosis_code`) 的行数 > 0 | hosp.diagnoses_icd + ed.diagnosis |
| has_disposition | BOOLEAN | edstays 中该 episode 有 disposition 值 | ed.edstays.disposition |
| has_discharge_summary | BOOLEAN | documents 中 document_type = `discharge` 的行数 > 0 | note.discharge |
| laboratory_count | BIGINT | COUNT(event_type=`laboratory_panel`) | hosp.labevents |
| radiology_report_count | BIGINT | COUNT(document_type=`radiology`) | note.radiology |
| native_link_count | BIGINT | COUNT(link_status=`native_link`) | — |
| temporal_link_count | BIGINT | COUNT(link_status=`unique_temporal_link`) | — |
| unresolved_event_count | BIGINT | COUNT(link_status=`unresolved`)（时间窗内） | — |
| first_event_time | TIMESTAMP | MIN(event_time) | — |
| last_event_time | TIMESTAMP | MAX(event_time) | — |

---

## 10. ID 体系总结

```
subject_id（患者）           ← hosp.patients / 全局统一
│
├── hadm_id（住院次）        ← hosp.admissions
│   ├── stay_id（ICU）       ← icu.icustays
│   ├── transfer_id（转移）  ← hosp.transfers
│   ├── pharmacy_id（药嘱）  ← hosp.pharmacy
│   ├── poe_id（医嘱）       ← hosp.poe
│   ├── emar_id（给药）      ← hosp.emar
│   └── note_id（文档）      ← note.discharge / note.radiology
│
├── stay_id（急诊）          ← ed.edstays（与 ICU stay_id 独立编号）
│   └── （edstays.hadm_id 可关联回住院）
│
└── 项目生成 ID
    ├── episode_id:  H:<hadm_id> 或 E:<stay_id>
    ├── contact_id:  IP:<hadm_id> / ED:<stay_id> / ICU:<stay_id> / TR:<transfer_id>
    ├── event_id:    <TYPE>:<原生键> 或 MD5(多列)
    ├── item_event_id: <源表前缀>:<原生键>:<物理行号>
    └── evidence_link_id: EV:<item_event_id> / DOC:<MD5> / NOTEDETAIL:<MD5>
```

> 注意：MIMIC-IV 中 ICU 的 `stay_id` 和 ED 的 `stay_id` 是两套独立编号体系，
> 不会冲突，但语义不同。contact_id 的前缀（`ICU:` vs `ED:`）用于区分。

---

## 11. 补充：omr 表的处理

`omr`（Outpatient Medical Record，门诊病历）表不含 `hadm_id` 或 `stay_id`，
无法直接关联到某次就诊。该表的事件在 pipeline 中作为 `special_unlinked_events`
处理，仅保留 `subject_id` + 时间戳，通过时间窗尝试匹配 episode；如不匹配则
保持 `link_status = 'unresolved'`，不删除。

---

> 本文档基于 MIMIC-IV 3.1 / ED 2.2 / Note 2.2 官方表结构生成。
> 官方文档地址：<https://mimic.mit.edu/docs/iv/modules/hosp/>
