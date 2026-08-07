# MIMIC-IV 数据库教程

## 概述

MIMIC-IV（Medical Information Mart for Intensive Care IV）是由麻省理工学院（MIT）和贝斯以色列女执事医疗中心（BIDMC）合作开发的公开电子健康记录数据库。该数据库包含2008-2019年间在BIDMC住院的患者的详细临床数据。

> **📋 ETL优先级指南**: 如果您是ETL工程师或需要评估实现哪些表，请参阅 [表优先级指南](priority_guide.md)，该文档根据临床研究需求对表进行了分类，并评估了不实现可选表的影响。

### 数据规模

| 指标 | 住院患者 | ICU患者 | 急诊患者 |
|------|----------|---------|----------|
| 就诊次数 | 431,231 | 73,181 | 425,087 |
| 独立患者数 | 180,733 | 50,920 | ~220,000 |
| 平均年龄 | 58.8岁 | 64.7岁 | - |
| 平均停留天数 | 4.5天 | 11.0天 | - |
| 院内死亡率 | 2.1% | 11.6% | - |

### 扩展数据集

| 数据集 | 记录数 | 说明 |
|--------|--------|------|
| MIMIC-CXR | 377,110 张图像 | 胸部X线影像 |
| MIMIC-IV-ECG | ~800,000 份 | 12导联心电图 |

## 模块化架构

MIMIC-IV采用模块化设计，数据按来源和类型分为六个模块：

```
MIMIC-IV
├── hosp/     # 医院模块 - 全院范围的临床数据
├── icu/      # ICU模块 - 重症监护室床旁数据
├── ed/       # 急诊模块 - 急诊科数据
├── note/     # 笔记模块 - 临床文本记录
├── cxr/      # 胸部X线模块 - 影像数据
└── ecg/      # 心电图模块 - ECG波形数据
```

## 核心标识符

跨表关联的关键标识符：

| 标识符 | 说明 | 唯一性 | 适用模块 |
|--------|------|--------|----------|
| `subject_id` | 患者唯一标识 | 每个患者唯一 | 所有模块 |
| `hadm_id` | 住院唯一标识 | 每次住院唯一 | hosp, icu, note |
| `stay_id` (ICU) | ICU住院标识 | 每次ICU入住唯一 | icu |
| `stay_id` (ED) | 急诊就诊标识 | 每次急诊就诊唯一 | ed |
| `study_id` | 影像/ECG检查标识 | 每次检查唯一 | cxr, ecg |

### 标识符关系

```
患者 (subject_id)
  ├── 住院 (hadm_id) [1:N]
  │     └── ICU入住 (stay_id) [1:N]
  ├── 急诊就诊 (stay_id - ED) [1:N]
  │     └── 可能关联住院 (hadm_id) [N:1]
  ├── 胸部X线检查 (study_id) [1:N]
  └── 心电图检查 (study_id) [1:N]
```

## 时间去标识化

为保护患者隐私，所有日期都经过偏移处理：
- 日期被移至2100年代
- 患者级别的时间偏移确保同一患者的时间间隔保持不变
- 通过 `anchor_year`、`anchor_age`、`anchor_year_group` 字段可推算真实年份范围

## 模块详情

### HOSP模块（医院模块）

包含全院范围的临床和管理数据：

| 类别 | 数据表 | 说明 |
|------|--------|------|
| 患者追踪 | [patients](hosp/patients.md), [admissions](hosp/admissions.md), [transfers](hosp/transfers.md) | 患者基本信息和院内流转 |
| 行政管理 | [services](hosp/services.md), [poe](hosp/poe.md), [poe_detail](hosp/poe_detail.md) | 服务科室和医嘱 |
| 计费编码 | [diagnoses_icd](hosp/diagnoses_icd.md), [procedures_icd](hosp/procedures_icd.md), [drgcodes](hosp/drgcodes.md), [hcpcsevents](hosp/hcpcsevents.md) | 诊断和操作编码 |
| 检验检查 | [labevents](hosp/labevents.md), [microbiologyevents](hosp/microbiologyevents.md), [omr](hosp/omr.md) | 实验室和微生物学检验 |
| 药物 | [prescriptions](hosp/prescriptions.md), [pharmacy](hosp/pharmacy.md), [emar](hosp/emar.md), [emar_detail](hosp/emar_detail.md) | 药物处方和给药记录 |
| 维度表 | [d_labitems](hosp/d_labitems.md), [d_icd_diagnoses](hosp/d_icd_diagnoses.md), [d_icd_procedures](hosp/d_icd_procedures.md), [d_hcpcs](hosp/d_hcpcs.md), [provider](hosp/provider.md) | 编码定义表和提供者 |

### ICU模块

包含ICU床旁监护系统（MetaVision）的数据：

| 类别 | 数据表 | 说明 |
|------|--------|------|
| 核心 | [icustays](icu/icustays.md) | ICU入住记录 |
| 事件 | [chartevents](icu/chartevents.md), [inputevents](icu/inputevents.md), [outputevents](icu/outputevents.md), [procedureevents](icu/procedureevents.md), [ingredientevents](icu/ingredientevents.md), [datetimeevents](icu/datetimeevents.md) | 床旁记录事件 |
| 维度表 | [d_items](icu/d_items.md), [caregiver](icu/caregiver.md) | 项目定义表和护理人员 |

### ED模块（急诊模块）

包含急诊科的临床数据：

| 数据表 | 说明 |
|--------|------|
| [edstays](ed/edstays.md) | 急诊就诊记录（核心表） |
| [triage](ed/triage.md) | 分诊评估（生命体征、ESI分级、主诉） |
| [vitalsign](ed/vitalsign.md) | 急诊期间生命体征 |
| [diagnosis](ed/diagnosis.md) | 急诊诊断（ICD编码） |
| [medrecon](ed/medrecon.md) | 用药核对（入院前用药） |
| [pyxis](ed/pyxis.md) | 急诊发药记录 |

### NOTE模块（笔记模块）

包含去标识化的临床文本记录：

| 数据表 | 说明 |
|--------|------|
| [discharge](note/discharge.md), [discharge_detail](note/discharge_detail.md) | 出院小结 |
| [radiology](note/radiology.md), [radiology_detail](note/radiology_detail.md) | 放射学报告 |

### CXR模块（胸部X线模块）

包含胸部X线影像及元数据：

| 数据文件 | 说明 |
|----------|------|
| [概述](cxr/README.md) | CXR模块概述 |
| cxr-record-list | 图像记录列表 |
| cxr-study-list | 检查记录列表 |
| cxr-provider-list | 医疗提供者列表 |
| DICOM影像 | 实际的胸部X线图像 |

### ECG模块（心电图模块）

包含12导联心电图波形数据：

| 数据表 | 说明 |
|--------|------|
| [概述](ecg/README.md) | ECG模块概述 |
| [record_list](ecg/record_list.md) | ECG记录列表 |
| [machine_measurements](ecg/machine_measurements.md) | 机器自动测量值 |
| [waveform_note_links](ecg/waveform_note_links.md) | 波形与报告关联 |

## 表间关系图

```
                         ┌─────────────┐
                         │  patients   │
                         │ (subject_id)│
                         └──────┬──────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
 ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
 │ admissions  │         │   edstays   │         │ cxr/ecg     │
 │  (hadm_id)  │         │  (stay_id)  │         │ (study_id)  │
 └──────┬──────┘         └──────┬──────┘         └─────────────┘
        │                       │
        │                       ├─────────────┬─────────────┐
        │                       │             │             │
        │                       ▼             ▼             ▼
        │                ┌───────────┐ ┌───────────┐ ┌───────────┐
        │                │  triage   │ │ diagnosis │ │  pyxis    │
        │                └───────────┘ └───────────┘ └───────────┘
        │
        ├───────────────┬───────────────┬───────────────┐
        │               │               │               │
        ▼               ▼               ▼               ▼
 ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
 │  transfers  │ │  icustays   │ │  labevents  │ │  discharge  │
 │(transfer_id)│ │  (stay_id)  │ │(labevent_id)│ │  (note_id)  │
 └─────────────┘ └──────┬──────┘ └─────────────┘ └─────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
 ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
 │ chartevents │ │ inputevents │ │outputevents │
 └─────────────┘ └─────────────┘ └─────────────┘
```

## ETL映射指南

在将本地医院数据映射到MIMIC-IV格式时，请注意：

1. **患者标识**: 确保每个患者有唯一的 `subject_id`
2. **住院标识**: 每次住院分配唯一的 `hadm_id`
3. **急诊标识**: 急诊使用独立的 `stay_id` 序列
4. **时间处理**: 保持时间的相对关系，可进行偏移处理
5. **编码系统**: 使用标准编码系统（ICD-9/10, LOINC, NDC等）
6. **单位标准化**: 统一计量单位（注意华氏度/摄氏度转换）

## 完整表清单

### HOSP模块（22张表）
patients, admissions, transfers, services, poe, poe_detail, diagnoses_icd, procedures_icd, drgcodes, hcpcsevents, labevents, microbiologyevents, omr, prescriptions, pharmacy, emar, emar_detail, d_labitems, d_icd_diagnoses, d_icd_procedures, d_hcpcs, provider

### ICU模块（9张表）
icustays, chartevents, inputevents, outputevents, procedureevents, ingredientevents, datetimeevents, d_items, caregiver

### ED模块（6张表）
edstays, triage, vitalsign, diagnosis, medrecon, pyxis

### NOTE模块（4张表）
discharge, discharge_detail, radiology, radiology_detail

### CXR模块（3个数据文件）
cxr-record-list, cxr-study-list, cxr-provider-list

### ECG模块（3张表）
record_list, machine_measurements, waveform_note_links

## 相关资源

- [MIMIC-IV官方文档](https://mimic.mit.edu/)
- [PhysioNet数据下载](https://physionet.org/content/mimic-iv-demo/2.2/)
- [MIMIC-CXR](https://physionet.org/content/mimic-cxr/)
- [MIMIC-IV-ECG](https://physionet.org/content/mimic-iv-ecg/)
- [MIMIC代码仓库](https://github.com/MIT-LCP/mimic-code)
