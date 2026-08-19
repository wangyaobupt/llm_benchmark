# MIMIC-IV 全模块字段解析

> **生成日期**: 2026-08-07
> **数据版本**: MIMIC-IV v3.1 (hosp/icu) + MIMIC-IV-ED v2.2 (ed) + MIMIC-IV-Note v2.2 (note)
> **数据位置**: `data/RawData/mimic-iv-3.1/`, `data/RawData/mimic-iv-ed/`, `data/RawData/mimic-iv-note-2.2/`
> **Schema来源**: `mimic_reference/` 官方中文 schema 文档

---

## 一、数据库概述

MIMIC-IV（Medical Information Mart for Intensive Care IV）是 MIT 与 BIDMC 合作开发的公开电子健康记录数据库，涵盖 2008-2019 年间 BIDMC 的住院、急诊和 ICU 患者。采用模块化设计，数据按来源分为四个核心模块：

| 模块 | 目录 | 表数 | 数据来源 | 说明 |
|------|------|------|----------|------|
| **hosp** | `mimic-iv-3.1/` (根目录) | 22 | 全院信息系统 | 患者追踪、诊断操作编码、检验、药物、医嘱等全院范围临床数据 |
| **icu** | `mimic-iv-3.1/icu/` | 9 | MetaVision ICU信息系统 | ICU床旁监护、输液、排出量、操作等床旁数据 |
| **note** | `mimic-iv-note-2.2/note/` | 4 | 临床文本系统 | 出院小结和放射学报告等去标识化临床文本 |
| **ed** | `mimic-iv-ed/ed/` | 6 | 急诊科信息系统 | 急诊就诊、分诊评估、生命体征、诊断、用药等急诊数据 |

### 数据规模

| 指标 | 数值 |
|------|------|
| 住院就诊次数 | 431,231 |
| ICU 入住次数 | 73,181 |
| 急诊就诊次数 | 425,087 |
| 独立患者数 | 180,733 (住院) / 50,920 (ICU) / ~220,000 (急诊) |
| 平均住院天数 | 4.5 天 (全院) / 11.0 天 (ICU) |
| 院内死亡率 | 2.1% (全院) / 11.6% (ICU) |

### 核心标识符

| 标识符 | 说明 | 适用模块 | 备注 |
|--------|------|----------|------|
| `subject_id` | 患者唯一标识 | 全部 | 每个患者唯一，跨所有模块 |
| `hadm_id` | 住院唯一标识 | hosp, icu, note | 取值 2000000-2999999 |
| `stay_id` (ICU) | ICU 入住标识 | icu | 与 ED 的 stay_id 独立 |
| `stay_id` (ED) | 急诊就诊标识 | ed | 与 ICU 的 stay_id 独立 |
| `note_id` | 文档唯一标识 | note | 由 subject_id + note_type + note_seq 组成 |
| `transfer_id` | 院内转移标识 | hosp | 每次物理位置转移唯一 |
| `pharmacy_id` | 药房记录标识 | hosp | 连接 prescriptions, emar, pharmacy |
| `poe_id` | 医嘱标识 | hosp | 连接 poe, prescriptions, emar |
| `itemid` | 检验/测量项目标识 | hosp(icd), icu | 分别关联 d_labitems / d_items |
| `specimen_id` | 标本标识 | hosp | 同一标本多项检验共享 |
| `orderid` / `linkorderid` | 输液医嘱标识 | icu | 关联输液及其成分 |
| `provider_id` | 医疗提供者标识 | hosp | 以 P 开头，去标识化 |
| `caregiver_id` | 护理人员标识 | icu | 整数，去标识化 |

### 跨模块表间关系

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
        │                       ├──────────┬──────────┐
        │                       ▼          ▼          ▼
        │                ┌──────────┐ ┌──────────┐ ┌──────────┐
        │                │  triage  │ │diagnosis │ │  pyxis   │
        │                └──────────┘ └──────────┘ └──────────┘
        │
        ├───────────┬───────────┬───────────┐
        ▼           ▼           ▼           ▼
 ┌────────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐
 │ transfers  │ │icustays │ │discharge │ │labevents │
 │(transfer_id)│ │(stay_id)│ │(note_id) │ │          │
 └────────────┘ └────┬────┘ └──────────┘ └──────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
 ┌────────────┐ ┌────────────┐ ┌─────────────┐
 │chartevents │ │inputevents │ │outputevents │
 └────────────┘ └────────────┘ └─────────────┘
```

---

## 二、HOSP 模块（医院模块）

> 共 22 张表。

| 表名 | 说明 |
|------|------|
| [`patients`](#patients-表) | 患者基本信息 |
| [`admissions`](#admissions-表) | 住院记录 |
| [`transfers`](#transfers-表) | 院内物理位置转移 |
| [`services`](#services-表) | 医疗服务科室 |
| [`diagnoses_icd`](#diagnoses_icd-表) | 诊断编码 |
| [`d_icd_diagnoses`](#d_icd_diagnoses-表) | 诊断编码字典 |
| [`procedures_icd`](#procedures_icd-表) | 操作编码 |
| [`d_icd_procedures`](#d_icd_procedures-表) | 操作编码字典 |
| [`drgcodes`](#drgcodes-表) | DRG分组 |
| [`hcpcsevents`](#hcpcsevents-表) | HCPCS/CPT计费事件 |
| [`d_hcpcs`](#d_hcpcs-表) | HCPCS编码字典 |
| [`labevents`](#labevents-表) | 实验室检验结果 |
| [`d_labitems`](#d_labitems-表) | 检验项目字典 |
| [`microbiologyevents`](#microbiologyevents-表) | 微生物检验结果 |
| [`omr`](#omr-表) | 在线医疗记录(基本生理测量) |
| [`prescriptions`](#prescriptions-表) | 药物处方 |
| [`pharmacy`](#pharmacy-表) | 药房配药详情 |
| [`emar`](#emar-表) | 电子药物给药记录 |
| [`emar_detail`](#emar_detail-表) | 给药记录详情 |
| [`poe`](#poe-表) | 医嘱录入 |
| [`poe_detail`](#poe_detail-表) | 医嘱详情 |
| [`provider`](#provider-表) | 医疗提供者字典 |

### `patients` 表

**患者基本信息**。`patients` 表是MIMIC-IV中最基础的患者信息表，存储患者的人口统计学信息。每个患者在此表中有且仅有一行记录。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL, 主键 | 患者唯一标识符 |
| `gender` | VARCHAR(1) | NOT NULL | 患者性别 |
| `anchor_age` | INTEGER | NOT NULL | 锚定年龄 |
| `anchor_year` | INTEGER | NOT NULL | 锚定年份（去标识化后的年份） |
| `anchor_year_group` | VARCHAR(255) | NOT NULL | 真实年份范围 |
| `dod` | TIMESTAMP(0) | 可空 | 死亡日期（去标识化） |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| admissions | subject_id | 一对多 |
| transfers | subject_id | 一对多 |
| labevents | subject_id | 一对多 |
| 所有其他临床表 | subject_id | 一对多 |

**注意事项：**

- 此表不包含种族、民族等敏感人口统计信息（这些在admissions表中）
- 死亡日期的一年限制是研究设计时必须考虑的重要因素
- 年龄截断（89岁）会影响老年患者相关的统计分析

---

### `admissions` 表

**住院记录**。`admissions` 表记录患者的住院信息，每次住院对应一行记录。包含入院和出院时间、入院类型、来源和去向等关键信息。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL, 主键 | 住院唯一标识 |
| `admittime` | TIMESTAMP | NOT NULL | 入院时间 |
| `dischtime` | TIMESTAMP | 可空 | 出院时间 |
| `deathtime` | TIMESTAMP | 可空 | 院内死亡时间 |
| `admission_type` | VARCHAR(40) | NOT NULL | 入院类型 |
| `admit_provider_id` | VARCHAR(10) | 可空 | 接诊医生标识 |
| `admission_location` | VARCHAR(60) | 可空 | 入院前位置 |
| `discharge_location` | VARCHAR(60) | 可空 | 出院去向 |
| `insurance` | VARCHAR(255) | 可空 | 保险类型 |
| `language` | VARCHAR(10) | 可空 | 患者语言 |
| `marital_status` | VARCHAR(30) | 可空 | 婚姻状态 |
| `race` | VARCHAR(80) | 可空 | 种族/民族 |
| `edregtime` | TIMESTAMP | 可空 | 急诊登记时间 |
| `edouttime` | TIMESTAMP | 可空 | 急诊离开时间 |
| `hospital_expire_flag` | SMALLINT | 可空 | 院内死亡标志 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `ELECTIVE` | 择期入院 |
  | `URGENT` | 紧急入院 |
  | `EMERGENCY` | 急诊入院 |
  | `SURGICAL SAME DAY ADMISSION` | 当日手术入院 |
  | `DIRECT EMER.` | 直接急诊入院 |
  | `DIRECT OBSERVATION` | 直接观察 |
  | `EU OBSERVATION` | 急诊观察 |
  | `EW EMER.` | 急诊室急诊 |
  | `OBSERVATION ADMIT` | 观察入院 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| transfers | hadm_id | 一对多 |
| icustays | hadm_id | 一对多 |
| diagnoses_icd | hadm_id | 一对多 |
| procedures_icd | hadm_id | 一对多 |
| labevents | hadm_id | 一对多 |
| prescriptions | hadm_id | 一对多 |

**注意事项：**

- **器官捐献账户**: 部分记录可能是器官捐献相关的特殊账户，可能出现极短甚至负数的住院时长
- **人口统计信息变化**: 同一患者的保险、婚姻状态等可能在不同次住院时有所变化
- **急诊数据**: 并非所有入院都有急诊数据，取决于入院途径

---

### `transfers` 表

**院内物理位置转移**。`transfers` 表记录患者在医院内的物理位置转移信息，追踪患者从入院到出院期间的所有科室流转。`icustays` 表就是从此表派生的。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | 可空 | 住院唯一标识 |
| `transfer_id` | INTEGER | NOT NULL, 主键 | 转移记录唯一标识 |
| `eventtype` | VARCHAR(10) | 可空 | 事件类型 |
| `careunit` | VARCHAR(255) | 可空 | 护理单元/病房类型 |
| `intime` | TIMESTAMP(0) | 可空 | 进入该单元的时间 |
| `outtime` | TIMESTAMP(0) | 可空 | 离开该单元的时间 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `ed` | 急诊科（Emergency Department） |
  | `admit` | 医院入院 |
  | `transfer` | 院内转科 |
  | `discharge` | 出院 |

  | 值 | 说明 |
  |---|---|
  | `Medical Intensive Care Unit (MICU)` | 内科ICU |
  | `Surgical Intensive Care Unit (SICU)` | 外科ICU |
  | `Coronary Care Unit (CCU)` | 冠心病监护室 |
  | `Cardiac Vascular Intensive Care Unit (CVICU)` | 心血管ICU |
  | `Medical/Surgical Intensive Care Unit (MICU/SICU)` | 内外科ICU |
  | `Neuro Intermediate` | 神经科中间病房 |
  | `Neuro Stepdown` | 神经科降级病房 |
  | `Neuro Surgical Intensive Care Unit (Neuro SICU)` | 神经外科ICU |
  | `Trauma SICU (TSICU)` | 创伤外科ICU |
  | `Medicine` | 内科普通病房 |
  | `Surgery` | 外科普通病房 |
  | `Emergency Department` | 急诊科 |
  | `Emergency Department Observation` | 急诊观察 |
  | `Discharge Lounge` | 出院候诊区 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |

**注意事项：**

- 并非所有物理位置都会在此表中记录，主要记录病房级别的转移
- ICU类型的病房是 `icustays` 表的数据来源
- `hadm_id` 为空的记录通常是急诊后未入院的患者
- 同一患者单次住院可能有多次转科记录

---

### `services` 表

**医疗服务科室**。`services` 表记录患者在住院期间接受治疗的医疗服务/科室。一次住院可能由多个科室先后负责治疗。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `transfertime` | TIMESTAMP(0) | NOT NULL | 转科时间 |
| `prev_service` | VARCHAR(20) | 可空 | 前一个服务科室 |
| `curr_service` | VARCHAR(20) | NOT NULL | 当前服务科室 |

**关键字段取值与枚举：**

| 代码 | 全称 | 中文说明 |
|------|------|----------|
| `MED` | Medicine | 内科 |
| `SURG` | Surgery | 外科 |
| `CMED` | Cardiac Medicine | 心内科 |
| `CSURG` | Cardiac Surgery | 心外科 |
| `NSURG` | Neurosurgery | 神经外科 |
| `NMED` | Neurology | 神经内科 |
| `OMED` | Oncology | 肿瘤科 |
| `TRAUM` | Trauma | 创伤外科 |
| `ORTHO` | Orthopedics | 骨科 |
| `TSURG` | Thoracic Surgery | 胸外科 |
| `VSURG` | Vascular Surgery | 血管外科 |
| `GYN` | Gynecology | 妇科 |
| `OBS` | Obstetrics | 产科 |
| `GU` | Genitourinary | 泌尿外科 |
| `ENT` | Ear Nose Throat | 耳鼻喉科 |
| `PSYCH` | Psychiatry | 精神科 |
| `DENT` | Dental | 口腔科 |
| `NB` | Newborn | 新生儿 |
| `NBB` | Newborn Baby | 新生儿（婴儿） |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |

**注意事项：**

- 大部分住院只有一条 `services` 记录
- 科室变更通常发生在病情变化或需要专科会诊时
- `services` 记录的是负责治疗的团队，而非患者的物理位置

---

### `diagnoses_icd` 表

**诊断编码**。`diagnoses_icd` 表存储患者住院期间的诊断编码，使用国际疾病分类（ICD）编码系统。这些诊断由专业编码人员在出院后根据病历记录分配，主要用于医疗费用结算。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `seq_num` | INTEGER | NOT NULL | 诊断序号 |
| `icd_code` | VARCHAR(7) | NOT NULL | ICD诊断编码 |
| `icd_version` | INTEGER | NOT NULL | ICD版本（9或10） |

**主键**: (`subject_id`, `hadm_id`, `seq_num`)

**关键字段取值与枚举：**

  | 编码 | 版本 | 含义 |
  |------|------|------|
  | 41401 | 9 | 冠状动脉粥样硬化 |
  | 5849 | 9 | 急性肾衰竭，未特指 |
  | I2510 | 10 | 动脉粥样硬化性心脏病 |
  | N179 | 10 | 急性肾衰竭，未特指 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| d_icd_diagnoses | icd_code, icd_version | 多对一 |

**注意事项：**

- **seq_num 的局限性**:
- **编码质量**:
- **时间范围**:
- **ICD版本过渡**:

---

### `d_icd_diagnoses` 表

**诊断编码字典**。`d_icd_diagnoses` 是ICD诊断编码的维度表（字典表），为 `diagnoses_icd` 表中的ICD编码提供描述信息。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `icd_code` | CHAR(7) | NOT NULL | ICD诊断编码 |
| `icd_version` | INTEGER | NOT NULL | ICD版本号 |
| `long_title` | VARCHAR(255) | 可空 | 诊断的完整描述 |

**主键**: (`icd_code`, `icd_version`)

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| diagnoses_icd | icd_code, icd_version | 一对多 |

**注意事项：**

- **小数点处理**: ICD编码存储时不含小数点
- **版本差异**: ICD-9和ICD-10是不同的编码体系，不能直接对应
- **编码演变**: 此表包含2008-2019年间有效的所有ICD编码
- **仅CM编码**: 此表仅包含诊断编码（CM），不包含操作编码（PCS）

---

### `procedures_icd` 表

**操作编码**。`procedures_icd` 表存储患者住院期间执行的医疗操作/手术的ICD编码。这些操作编码由专业编码人员在出院后分配，用于医疗费用结算。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `seq_num` | INTEGER | NOT NULL | 操作序号 |
| `chartdate` | DATE | NOT NULL | 操作日期 |
| `icd_code` | VARCHAR(7) | NOT NULL | ICD操作编码 |
| `icd_version` | INTEGER | NOT NULL | ICD版本（9或10） |

**主键**: (`subject_id`, `hadm_id`, `seq_num`)

**关键字段取值与枚举：**

  | 编码 | 版本 | 含义 |
  |------|------|------|
  | 3961 | 9 | 体外膜氧合（ECMO） |
  | 9671 | 9 | 持续机械通气 <96小时 |
  | 5A1955Z | 10 | 呼吸机通气 <24小时 |
  | 02100Z9 | 10 | 冠状动脉旁路移植 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| d_icd_procedures | icd_code, icd_version | 多对一 |

**注意事项：**

- **仅限住院操作**: 此表仅包含医院计费的操作，不包括医生个人计费的操作
- **编码粒度**: ICD操作编码可能不够详细，对于详细研究建议结合其他数据源
- **ICD版本过渡**: ICD-10-PCS的编码粒度远高于ICD-9-PCS

---

### `d_icd_procedures` 表

**操作编码字典**。`d_icd_procedures` 是ICD操作编码的维度表（字典表），为 `procedures_icd` 表中的ICD操作编码提供描述信息。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `icd_code` | CHAR(7) | NOT NULL | ICD操作编码 |
| `icd_version` | INTEGER | NOT NULL | ICD版本号 |
| `long_title` | VARCHAR(255) | 可空 | 操作的完整描述 |

**主键**: (`icd_code`, `icd_version`)

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| procedures_icd | icd_code, icd_version | 一对多 |

**注意事项：**

- **仅PCS编码**: 此表仅包含操作编码（PCS），不包含诊断编码（CM）
- **版本差异**: ICD-10-PCS的编码粒度远高于ICD-9-PCS
- **小数点**: 编码存储时不含小数点

---

### `drgcodes` 表

**DRG分组**。`drgcodes` 表存储住院的诊断相关分组（DRG）编码。DRG是用于医院费用报销的分类系统，将具有相似临床特征和资源消耗的住院病例归为同一组。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `drg_type` | VARCHAR(4) | NOT NULL | DRG编码体系类型 |
| `drg_code` | VARCHAR(10) | NOT NULL | DRG编码 |
| `description` | VARCHAR(195) | 可空 | DRG描述 |
| `drg_severity` | SMALLINT | 可空 | 疾病严重度 |
| `drg_mortality` | SMALLINT | 可空 | 死亡风险等级 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `APR` | All Patient Refined DRG（全患者精细化DRG） |
  | `HCFA` | Health Care Financing Administration（医疗保健筹资管理局）DRG |

  | 值 | 说明 |
  |---|------|
  | 1 | Minor（轻度） |
  | 2 | Moderate（中度） |
  | 3 | Major（重度） |
  | 4 | Extreme（极重度） |

  | 值 | 说明 |
  |---|------|
  | 1 | Minor（低风险） |
  | 2 | Moderate（中等风险） |
  | 3 | Major（高风险） |
  | 4 | Extreme（极高风险） |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |

**注意事项：**

- **一对多关系**: 同一次住院可能有多个DRG编码（不同体系）
- **计费导向**: DRG主要用于计费，可能存在一定的"向上编码"倾向
- **年度更新**: DRG分组逻辑每年可能更新，分析时需考虑版本差异
- **并非所有住院都有**: 部分住院可能没有DRG编码

---

### `hcpcsevents` 表

**HCPCS/CPT计费事件**。`hcpcsevents` 表存储使用HCPCS（Healthcare Common Procedure Coding System）编码的计费事件，主要包含CPT（Current Procedural Terminology）编码的操作和服务。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `chartdate` | DATE | 可空 | 编码对应的日期 |
| `hcpcs_cd` | CHAR(5) | NOT NULL | HCPCS/CPT编码 |
| `seq_num` | INTEGER | NOT NULL | 序号 |
| `short_description` | VARCHAR(180) | 可空 | 编码简短描述 |

**主键**: (`hadm_id`, `seq_num`)

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| d_hcpcs | hcpcs_cd → code | 多对一 |

**注意事项：**

- **医院vs医生计费**: 此表主要是医院计费的HCPCS，不包括所有医生单独计费的服务
- **编码更新**: HCPCS/CPT编码每年更新，分析时注意版本
- **替代cptevents**: 此表替代了MIMIC-III中的 `cptevents` 表

---

### `d_hcpcs` 表

**HCPCS编码字典**。`d_hcpcs` 是HCPCS/CPT编码的维度表（字典表），为 `hcpcsevents` 表中的编码提供描述信息。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `code` | CHAR(5) | NOT NULL, 主键 | HCPCS/CPT编码 |
| `category` | SMALLINT | 可空 | 编码分类 |
| `long_description` | TEXT | 可空 | 完整描述 |
| `short_description` | VARCHAR(180) | 可空 | 简短描述 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| hcpcsevents | hcpcs_cd → code | 一对多 |

**注意事项：**

- **CPT版权**: CPT编码是AMA的注册商标，使用受版权保护
- **年度变化**: 编码和描述每年可能更新
- **不完整**: 此表可能不包含所有HCPCS编码

---

### `labevents` 表

**实验室检验结果**。`labevents` 表存储患者的实验室检验结果，是MIMIC-IV中最重要和最常用的数据表之一。包含血液、尿液等各类标本的检验结果。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `labevent_id` | INTEGER | NOT NULL, 主键 | 检验事件唯一标识 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | 可空 | 住院唯一标识 |
| `specimen_id` | INTEGER | NOT NULL | 标本唯一标识 |
| `itemid` | INTEGER | NOT NULL | 检验项目标识 |
| `order_provider_id` | VARCHAR(10) | 可空 | 开单医生标识 |
| `charttime` | TIMESTAMP(0) | 可空 | 标本采集时间 |
| `storetime` | TIMESTAMP(0) | 可空 | 结果入库时间 |
| `value` | VARCHAR(200) | 可空 | 检验结果（文本） |
| `valuenum` | DOUBLE PRECISION | 可空 | 检验结果（数值） |
| `valueuom` | VARCHAR(20) | 可空 | 计量单位 |
| `ref_range_lower` | DOUBLE PRECISION | 可空 | 参考范围下限 |
| `ref_range_upper` | DOUBLE PRECISION | 可空 | 参考范围上限 |
| `flag` | VARCHAR(10) | 可空 | 异常标志 |
| `priority` | VARCHAR(7) | 可空 | 检验优先级 |
| `comments` | TEXT | 可空 | 备注信息 |

**关键字段取值与枚举：**

  | itemid | 项目名称 |
  |--------|----------|
  | 50912 | 肌酐 (Creatinine) |
  | 50971 | 钾 (Potassium) |
  | 50983 | 钠 (Sodium) |
  | 51221 | 血红蛋白 (Hemoglobin) |
  | 51222 | 血细胞比容 (Hematocrit) |
  | 51265 | 血小板 (Platelet Count) |
  | 51301 | 白细胞 (White Blood Cells) |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| d_labitems | itemid | 多对一 |

**注意事项：**

- **数据量巨大**: 这是MIMIC中最大的表之一，查询时注意性能
- **单位不一致**: 同一检验项目可能存在多种单位，分析前需标准化
- **门诊数据**: `hadm_id` 为空的记录可能来自门诊或无法匹配的检验
- **标本类型**: 同一检验项目在不同标本类型（动脉血、静脉血等）中结果可能不同
- **重复检验**: 同一时间点可能有多次检验，需要根据研究目的选择处理方式

---

### `d_labitems` 表

**检验项目字典**。`d_labitems` 是实验室检验项目的维度表（字典表），为 `labevents` 表中的 `itemid` 提供人类可读的描述信息。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `itemid` | INTEGER | NOT NULL, 主键 | 检验项目唯一标识 |
| `label` | VARCHAR(50) | 可空 | 检验项目名称 |
| `fluid` | VARCHAR(50) | 可空 | 标本类型 |
| `category` | VARCHAR(50) | 可空 | 检验类别 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `Blood` | 血液 |
  | `Urine` | 尿液 |
  | `Cerebrospinal Fluid (CSF)` | 脑脊液 |
  | `Ascites` | 腹水 |
  | `Pleural` | 胸水 |
  | `Joint Fluid` | 关节液 |
  | `Stool` | 粪便 |
  | `Other Body Fluid` | 其他体液 |

  | 值 | 说明 |
  |---|---|
  | `Blood Gas` | 血气分析 |
  | `Chemistry` | 生化检验 |
  | `Hematology` | 血液学检验 |
  | `Coagulation` | 凝血功能 |
  | `Urinalysis` | 尿液分析 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| labevents | itemid | 一对多 |

**注意事项：**

- 同一检验项目在不同标本类型中会有不同的 `itemid`
- 使用 `itemid` 而非 `label` 进行数据分析，因为 `label` 可能有微小变化
- 大多数项目已映射到LOINC编码，便于与外部系统互操作

---

### `microbiologyevents` 表

**微生物检验结果**。`microbiologyevents` 表存储微生物学检验结果，包括细菌培养、病原体鉴定和药物敏感性试验结果。这是研究感染和抗生素使用的关键数据源。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `microevent_id` | INTEGER | NOT NULL, 主键 | 微生物事件唯一标识 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | 可空 | 住院唯一标识 |
| `micro_specimen_id` | INTEGER | NOT NULL | 微生物标本标识 |
| `order_provider_id` | VARCHAR(10) | 可空 | 开单医生标识 |
| `chartdate` | TIMESTAMP(0) | NOT NULL | 记录日期 |
| `charttime` | TIMESTAMP(0) | 可空 | 记录时间 |
| `spec_itemid` | INTEGER | NOT NULL | 标本类型标识 |
| `spec_type_desc` | VARCHAR(100) | NOT NULL | 标本类型描述 |
| `test_seq` | INTEGER | NOT NULL | 测试序号 |
| `storedate` | TIMESTAMP(0) | 可空 | 结果存储日期 |
| `storetime` | TIMESTAMP(0) | 可空 | 结果存储时间 |
| `test_itemid` | INTEGER | 可空 | 测试项目标识 |
| `test_name` | VARCHAR(100) | 可空 | 测试名称 |
| `org_itemid` | INTEGER | 可空 | 微生物标识 |
| `org_name` | VARCHAR(100) | 可空 | 微生物名称 |
| `isolate_num` | SMALLINT | 可空 | 分离株编号 |
| `quantity` | VARCHAR(50) | 可空 | 菌落数量 |
| `ab_itemid` | INTEGER | 可空 | 抗生素标识 |
| `ab_name` | VARCHAR(30) | 可空 | 抗生素名称 |
| `dilution_text` | VARCHAR(10) | 可空 | 稀释度文本 |
| `dilution_comparison` | VARCHAR(20) | 可空 | 稀释度比较符 |
| `dilution_value` | DOUBLE PRECISION | 可空 | 稀释度数值 |
| `interpretation` | VARCHAR(5) | 可空 | 敏感性解读 |
| `comments` | TEXT | 可空 | 备注 |

**关键字段取值与枚举：**

  | spec_type_desc | 说明 |
  |----------------|------|
  | BLOOD CULTURE | 血培养 |
  | URINE | 尿液 |
  | SPUTUM | 痰液 |
  | MRSA SCREEN | MRSA筛查 |
  | STOOL | 粪便 |
  | BRONCHIAL WASHINGS | 支气管冲洗液 |
  | WOUND | 伤口分泌物 |

  | org_name | 说明 |
  |----------|------|
  | STAPHYLOCOCCUS AUREUS | 金黄色葡萄球菌 |
  | ESCHERICHIA COLI | 大肠杆菌 |
  | PSEUDOMONAS AERUGINOSA | 铜绿假单胞菌 |
  | KLEBSIELLA PNEUMONIAE | 肺炎克雷伯菌 |
  | ENTEROCOCCUS | 肠球菌 |
  | CANDIDA ALBICANS | 白色念珠菌 |

  | ab_name | 说明 |
  |---------|------|
  | VANCOMYCIN | 万古霉素 |
  | GENTAMICIN | 庆大霉素 |
  | CIPROFLOXACIN | 环丙沙星 |
  | PIPERACILLIN/TAZO | 哌拉西林/他唑巴坦 |

  | 值 | 含义 |
  |---|------|
  | `S` | 敏感 (Susceptible) |
  | `R` | 耐药 (Resistant) |
  | `I` | 中介 (Intermediate) |
  | `P` | 待定 (Pending) |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |

**注意事项：**

- **阴性培养**: 培养阴性时 `org_name` 为空
- **中间结果**: 此表只包含最终结果，不包含中间报告
- **多重感染**: 同一标本可能培养出多种病原体
- **数据冗余**: 为便于查询，层级较高的信息（如标本、微生物）在下级记录中重复

---

### `omr` 表

**在线医疗记录(基本生理测量)**。`omr`（Online Medical Record，在线医疗记录）表存储患者的基本生理测量数据，包括来自门诊和住院的血压、身高、体重、BMI和肾小球滤过率估算值(eGFR)。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `chartdate` | DATE | NOT NULL | 记录日期 |
| `seq_num` | INTEGER | NOT NULL | 序号 |
| `result_name` | VARCHAR(100) | NOT NULL | 测量项目名称 |
| `result_value` | TEXT | NOT NULL | 测量值 |

**主键**: (`subject_id`, `chartdate`, `seq_num`)

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `Blood Pressure` | 血压 |
  | `Height` | 身高 |
  | `Weight` | 体重 |
  | `BMI (kg/m2)` | 体质指数 |
  | `eGFR` | 估算肾小球滤过率 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |

**注意事项：**

- **非结构化值**: `result_value` 是文本格式，可能需要解析
- **单位变化**: 同一测量项目可能使用不同单位
- **门诊数据**: 包含门诊数据，不仅限于住院
- **基线价值**: 可用于获取患者住院前的基线状态
- **MIMIC-IV新增**: 此表是MIMIC-IV新增的表，MIMIC-III中没有

---

### `prescriptions` 表

**药物处方**。`prescriptions` 表存储医生开具的药物处方信息，包括药物名称、剂量、给药途径和时间等。此表记录的是处方医嘱，而非实际给药记录（实际给药见 `emar` 表）。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `pharmacy_id` | INTEGER | NOT NULL | 药房记录标识 |
| `poe_id` | VARCHAR(25) | 可空 | 医嘱标识 |
| `poe_seq` | INTEGER | 可空 | 医嘱序号 |
| `order_provider_id` | VARCHAR(10) | 可空 | 开单医生标识 |
| `starttime` | TIMESTAMP(3) | 可空 | 处方开始时间 |
| `stoptime` | TIMESTAMP(3) | 可空 | 处方结束时间 |
| `drug_type` | VARCHAR(20) | NOT NULL | 药物成分类型 |
| `drug` | VARCHAR(255) | NOT NULL | 药物名称 |
| `formulary_drug_cd` | VARCHAR(50) | 可空 | 医院药物目录代码 |
| `gsn` | VARCHAR(255) | 可空 | 通用序列号 |
| `ndc` | VARCHAR(25) | 可空 | 国家药品编码 |
| `prod_strength` | VARCHAR(255) | 可空 | 药品规格 |
| `form_rx` | VARCHAR(25) | 可空 | 药品剂型 |
| `dose_val_rx` | VARCHAR(100) | 可空 | 处方剂量值 |
| `dose_unit_rx` | VARCHAR(50) | 可空 | 处方剂量单位 |
| `form_val_disp` | VARCHAR(50) | 可空 | 单次给药量 |
| `form_unit_disp` | VARCHAR(50) | 可空 | 单次给药单位 |
| `doses_per_24_hrs` | REAL | 可空 | 每24小时给药次数 |
| `route` | VARCHAR(50) | 可空 | 给药途径 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `MAIN` | 主要成分 |
  | `BASE` | 基础液体（如生理盐水） |
  | `ADDITIVE` | 添加剂 |

  | 值 | 说明 |
  |---|---|
  | `IV` | 静脉注射 |
  | `PO` | 口服 |
  | `IM` | 肌肉注射 |
  | `SC` | 皮下注射 |
  | `IVPCA` | 静脉患者自控镇痛 |
  | `INH` | 吸入 |
  | `TOP` | 外用 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| pharmacy | pharmacy_id | 一对一 |
| poe | poe_id | 多对一 |
| emar | pharmacy_id | 一对多 |

**注意事项：**

- **处方 vs 给药**: 此表记录处方医嘱，实际给药情况见 `emar` 表
- **多行记录**: 一个输液处方可能有多行（主药、溶媒、添加剂）
- **医院特定编码**: `formulary_drug_cd` 是医院特定编码，不具通用性
- **剂量单位变化**: 同一药物在不同处方中可能使用不同单位

---

### `pharmacy` 表

**药房配药详情**。`pharmacy` 表存储药房配药的详细信息，是 `prescriptions` 表的补充。包含药物的详细给药计划、状态和特殊给药参数（如PCA设置）。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `pharmacy_id` | INTEGER | NOT NULL, 主键 | 药房记录唯一标识 |
| `poe_id` | VARCHAR(25) | 可空 | 医嘱标识 |
| `starttime` | TIMESTAMP(3) | 可空 | 用药开始时间 |
| `stoptime` | TIMESTAMP(3) | 可空 | 用药结束时间 |
| `medication` | TEXT | 可空 | 药物名称 |
| `proc_type` | VARCHAR(50) | NOT NULL | 处方类型 |
| `status` | VARCHAR(50) | 可空 | 处方状态 |
| `entertime` | TIMESTAMP(3) | NOT NULL | 录入时间 |
| `verifiedtime` | TIMESTAMP(3) | 可空 | 审核时间 |
| `route` | VARCHAR(50) | 可空 | 给药途径 |
| `frequency` | VARCHAR(50) | 可空 | 给药频次 |
| `disp_sched` | VARCHAR(255) | 可空 | 配药时间表 |
| `infusion_type` | VARCHAR(15) | 可空 | 输液类型 |
| `sliding_scale` | VARCHAR(1) | 可空 | 滑动比例标志 |
| `lockout_interval` | VARCHAR(50) | 可空 | PCA锁定间隔 |
| `basal_rate` | REAL | 可空 | 基础速率 |
| `one_hr_max` | VARCHAR(10) | 可空 | 每小时最大剂量 |
| `doses_per_24_hrs` | REAL | 可空 | 每日给药次数 |
| `duration` | REAL | 可空 | 持续时间数值 |
| `duration_interval` | VARCHAR(50) | 可空 | 持续时间单位 |
| `expiration_value` | INTEGER | 可空 | 有效期数值 |
| `expiration_unit` | VARCHAR(50) | 可空 | 有效期单位 |
| `expirationdate` | TIMESTAMP(3) | 可空 | 过期日期 |
| `dispensation` | VARCHAR(50) | 可空 | 配发来源 |
| `fill_quantity` | VARCHAR(50) | 可空 | 配发数量 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `IV Piggyback` | 静脉间歇输注 |
  | `Unit Dose` | 单位剂量 |
  | `Continuous Med` | 持续用药 |
  | `IV Push` | 静脉推注 |

  | 值 | 说明 |
  |---|---|
  | `B` | 基础 |
  | `C` | 持续 |
  | `N` | 新袋 |
  | `N1` | 新袋类型1 |
  | `O` | 其他 |
  | `R` | 替换 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| prescriptions | pharmacy_id | 一对一 |
| emar | pharmacy_id | 一对多 |
| poe | poe_id | 多对一 |

**注意事项：**

- **并非所有处方**: 不是所有 `prescriptions` 记录都有对应的 `pharmacy` 记录
- **详细信息补充**: 此表提供比 `prescriptions` 更详细的给药参数
- **时间一致性**: 注意与 `prescriptions` 表中时间的一致性

---

### `emar` 表

**电子药物给药记录**。`emar`（Electronic Medicine Administration Record，电子药物给药记录）表记录药物的实际给药情况。与 `prescriptions` 表（记录处方）不同，此表记录的是药物实际被给予患者的时间和状态。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | 可空 | 住院唯一标识 |
| `emar_id` | VARCHAR(25) | NOT NULL, 主键 | 给药记录唯一标识 |
| `emar_seq` | INTEGER | NOT NULL | 给药序号 |
| `poe_id` | VARCHAR(25) | NOT NULL | 医嘱标识 |
| `pharmacy_id` | INTEGER | 可空 | 药房记录标识 |
| `enter_provider_id` | VARCHAR(10) | 可空 | 录入人员标识 |
| `charttime` | TIMESTAMP | NOT NULL | 给药时间 |
| `medication` | TEXT | 可空 | 药物名称 |
| `event_txt` | VARCHAR(100) | 可空 | 给药事件状态 |
| `scheduletime` | TIMESTAMP | 可空 | 计划给药时间 |
| `storetime` | TIMESTAMP | NOT NULL | 记录存储时间 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `Administered` | 已给药 |
  | `Applied` | 已应用（外用药） |
  | `Delayed` | 延迟给药 |
  | `Not Given` | 未给药 |
  | `Stopped` | 已停止 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| emar_detail | emar_id, emar_seq | 一对多 |
| poe | poe_id | 多对一 |
| pharmacy | pharmacy_id | 多对一 |
| prescriptions | pharmacy_id | 多对一 |

**注意事项：**

- **数据覆盖**: 2016年之前数据可能不完整
- **与 inputevents 的关系**: ICU中的静脉输液信息同时存在于 `inputevents`（来自MetaVision）和 `emar`（来自eMAR系统）
- **详细信息**: 给药的详细信息（如剂量、部位等）存储在 `emar_detail` 表中

---

### `emar_detail` 表

**给药记录详情**。`emar_detail` 表存储 `emar` 表中给药记录的详细信息，包括剂量、给药部位、输液速率等。采用类似EAV的扩展结构。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `emar_id` | VARCHAR(25) | NOT NULL | 给药记录标识 |
| `emar_seq` | INTEGER | NOT NULL | 给药序号 |
| `parent_field_ordinal` | VARCHAR(10) | 可空 | 父字段序号 |
| `administration_type` | VARCHAR(50) | 可空 | 给药类型 |
| `pharmacy_id` | INTEGER | 可空 | 药房记录标识 |
| `barcode_type` | VARCHAR(4) | 可空 | 条形码类型 |
| `reason_for_no_barcode` | TEXT | 可空 | 未扫码原因 |
| `complete_dose_not_given` | VARCHAR(5) | 可空 | 完整剂量是否未给 |
| `dose_due` | VARCHAR(100) | 可空 | 应给剂量 |
| `dose_due_unit` | VARCHAR(50) | 可空 | 应给剂量单位 |
| `dose_given` | VARCHAR(255) | 可空 | 实际给予剂量 |
| `dose_given_unit` | VARCHAR(50) | 可空 | 实际给予剂量单位 |
| `will_remainder_of_dose_be_given` | VARCHAR(5) | 可空 | 剩余剂量是否会给 |
| `product_amount_given` | VARCHAR(30) | 可空 | 产品给予量 |
| `product_unit` | VARCHAR(30) | 可空 | 产品单位 |
| `product_code` | VARCHAR(30) | 可空 | 产品代码 |
| `product_description` | VARCHAR(255) | 可空 | 产品描述 |
| `product_description_other` | VARCHAR(255) | 可空 | 其他产品描述 |
| `prior_infusion_rate` | VARCHAR(40) | 可空 | 之前输液速率 |
| `infusion_rate` | VARCHAR(40) | 可空 | 当前输液速率 |
| `infusion_rate_adjustment` | VARCHAR(50) | 可空 | 速率调整 |
| `infusion_rate_adjustment_amount` | VARCHAR(30) | 可空 | 速率调整量 |
| `infusion_rate_unit` | VARCHAR(30) | 可空 | 输液速率单位 |
| `route` | VARCHAR(10) | 可空 | 给药途径 |
| `infusion_complete` | VARCHAR(1) | 可空 | 输液是否完成 |
| `completion_interval` | VARCHAR(50) | 可空 | 完成时间间隔 |
| `new_iv_bag_hung` | VARCHAR(1) | 可空 | 是否挂新袋 |
| `continued_infusion_in_other_location` | VARCHAR(1) | 可空 | 是否在其他位置继续输液 |
| `restart_interval` | TEXT | 可空 | 重启间隔 |
| `side` | VARCHAR(10) | 可空 | 身体侧（左/右） |
| `site` | VARCHAR(255) | 可空 | 给药部位 |
| `non_formulary_visual_verification` | VARCHAR(1) | 可空 | 非处方目录药物视觉确认 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| emar | emar_id, emar_seq | 多对一 |
| patients | subject_id | 多对一 |
| pharmacy | pharmacy_id | 多对一 |

**注意事项：**

- **一对多关系**: 每个 `emar` 记录可能有多行 `emar_detail`
- **汇总行**: `parent_field_ordinal = NULL` 的行包含整体给药信息
- **明细行**: 其他行包含每个药品单位的详细信息
- **字段分布**: 某些字段仅在汇总行有值，某些仅在明细行有值

---

### `poe` 表

**医嘱录入**。`poe`（Provider Order Entry，医嘱录入）表记录医生在电子医嘱系统中下达的各类医嘱。包括药物、检验、影像、会诊等各类医嘱的基本信息。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `poe_id` | VARCHAR(25) | NOT NULL, 主键 | 医嘱唯一标识 |
| `poe_seq` | INTEGER | NOT NULL | 医嘱序号 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | 可空 | 住院唯一标识 |
| `ordertime` | TIMESTAMP(0) | NOT NULL | 医嘱下达时间 |
| `order_type` | VARCHAR(25) | NOT NULL | 医嘱类型 |
| `order_subtype` | VARCHAR(50) | 可空 | 医嘱子类型 |
| `transaction_type` | VARCHAR(15) | 可空 | 操作类型 |
| `discontinue_of_poe_id` | VARCHAR(25) | 可空 | 被停止的医嘱ID |
| `discontinued_by_poe_id` | VARCHAR(25) | 可空 | 停止此医嘱的医嘱ID |
| `order_provider_id` | VARCHAR(10) | 可空 | 下达医嘱的医生标识 |
| `order_status` | VARCHAR(15) | 可空 | 医嘱状态 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `Medications` | 药物医嘱 |
  | `Lab` | 检验医嘱 |
  | `Imaging` | 影像检查医嘱 |
  | `Procedures` | 操作/手术医嘱 |
  | `Consults` | 会诊医嘱 |
  | `Nutrition` | 营养医嘱 |
  | `Blood Bank` | 血库医嘱 |
  | `Respiratory` | 呼吸治疗医嘱 |
  | `ADT` | 入院/出院/转科医嘱 |

  | 值 | 说明 |
  |---|---|
  | `New` | 新建医嘱 |
  | `Change` | 修改医嘱 |
  | `D/C` | 停止医嘱 (Discontinue) |
  | `Renew` | 续签医嘱 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| poe_detail | poe_id, poe_seq | 一对多 |
| prescriptions | poe_id | 一对一 |
| emar | poe_id | 一对多 |

**注意事项：**

- **基本信息表**: 此表只包含医嘱的基本信息，详细内容在 `poe_detail` 表
- **与其他表的关系**: 药物医嘱的详细信息在 `prescriptions` 表
- **门诊医嘱**: `hadm_id` 为空的记录可能是门诊医嘱

---

### `poe_detail` 表

**医嘱详情**。`poe_detail` 表存储医嘱的详细信息，采用实体-属性-值（EAV）模型，为 `poe` 表中的医嘱提供补充信息。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `poe_id` | VARCHAR(25) | NOT NULL | 医嘱唯一标识 |
| `poe_seq` | INTEGER | NOT NULL | 医嘱序号 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `field_name` | VARCHAR(255) | NOT NULL | 属性名称 |
| `field_value` | TEXT | 可空 | 属性值 |

**主键**: (`poe_id`, `poe_seq`, `field_name`)

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| poe | poe_id, poe_seq | 多对一 |
| patients | subject_id | 多对一 |

**注意事项：**

- **查询复杂性**: EAV模型查询比传统关系模型复杂，需要进行透视操作
- **属性不固定**: 不同医嘱可能有不同的属性组合
- **与其他表重复**: 部分信息可能与 `prescriptions` 等表重复

---

### `provider` 表

**医疗提供者字典**。`provider` 表是医疗提供者（Provider）的维度表，列出数据库中所有可能的医疗提供者标识。医疗提供者包括医生、护士、药剂师等参与患者诊疗的医护人员。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `provider_id` | VARCHAR(10) | NOT NULL, 主键 | 医疗提供者唯一标识 |

**外键关系：**

此表作为维度表被多个表引用：

| 引用表 | 引用字段 | 说明 |
|--------|----------|------|
| admissions | admit_provider_id | 入院提供者 |
| emar | enter_provider_id, verify_provider_id | 用药记录提供者 |
| poe | order_provider_id | 医嘱提供者 |
| labevents | order_provider_id | 检验开单提供者 |
| pharmacy | enter_provider_id, verify_provider_id | 药房提供者 |

**注意事项：**

- **无详细信息**: 此表仅包含标识符，无提供者姓名等详细信息
- **去标识化**: 标识符为随机生成，无法追溯到真实个人
- **角色不明**: 无法直接确定提供者的职位或科室
- **与caregiver区分**: `provider` 用于HOSP模块，`caregiver` 用于ICU模块
- **后缀命名**: 不同表中的字段后缀表示不同角色（如 `admit_`, `order_`, `enter_`）

---

## 三、ICU 模块（重症监护模块）

> 共 9 张表。

| 表名 | 说明 |
|------|------|
| [`icustays`](#icustays-表) | ICU入住记录 |
| [`chartevents`](#chartevents-表) | 床旁观察与测量 |
| [`d_items`](#d_items-表) | ICU项目字典 |
| [`inputevents`](#inputevents-表) | 静脉输液与药物输注 |
| [`outputevents`](#outputevents-表) | 排出量 |
| [`procedureevents`](#procedureevents-表) | ICU操作与治疗事件 |
| [`datetimeevents`](#datetimeevents-表) | 日期时间记录 |
| [`ingredientevents`](#ingredientevents-表) | 输液成分详情 |
| [`caregiver`](#caregiver-表) | 护理人员字典 |

### `icustays` 表

**ICU入住记录**。`icustays` 表定义患者的ICU（重症监护室）入住记录。每次ICU入住对应一行记录。此表从 `transfers` 表派生，是研究ICU患者的核心表。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `stay_id` | INTEGER | NOT NULL, 主键 | ICU入住唯一标识 |
| `first_careunit` | VARCHAR(20) | 可空 | 首个ICU类型 |
| `last_careunit` | VARCHAR(20) | 可空 | 最后ICU类型 |
| `intime` | TIMESTAMP(0) | NOT NULL | ICU入住时间 |
| `outtime` | TIMESTAMP(0) | NOT NULL | ICU离开时间 |
| `los` | DOUBLE PRECISION | 可空 | ICU住院时长（天） |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `Medical Intensive Care Unit (MICU)` | 内科ICU |
  | `Medical/Surgical Intensive Care Unit (MICU/SICU)` | 内外科ICU |
  | `Surgical Intensive Care Unit (SICU)` | 外科ICU |
  | `Cardiac Vascular Intensive Care Unit (CVICU)` | 心血管ICU |
  | `Coronary Care Unit (CCU)` | 冠心病监护室 |
  | `Neuro Surgical Intensive Care Unit (Neuro SICU)` | 神经外科ICU |
  | `Trauma SICU (TSICU)` | 创伤外科ICU |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| chartevents | stay_id | 一对多 |
| inputevents | stay_id | 一对多 |
| outputevents | stay_id | 一对多 |
| procedureevents | stay_id | 一对多 |

**注意事项：**

- **stay_id vs icustay_id**: MIMIC-IV使用 `stay_id`，MIMIC-III使用 `icustay_id`
- **一次住院多次ICU**: 同一次住院（`hadm_id`）可能有多次ICU入住
- **ICU内转科**: 如果患者在ICU之间转移（如MICU→SICU），`first_careunit` 和 `last_careunit` 会不同
- **短暂离开**: 短暂（<24小时）离开ICU后返回会被合并为一次入住

---

### `chartevents` 表

**床旁观察与测量**。`chartevents` 表是ICU模块中最大的表，存储ICU护士在床旁记录的各种观察和测量数据。包括生命体征、评估量表、护理记录等。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `stay_id` | INTEGER | NOT NULL | ICU入住标识 |
| `caregiver_id` | INTEGER | 可空 | 记录护士标识 |
| `charttime` | TIMESTAMP(0) | NOT NULL | 观察时间 |
| `storetime` | TIMESTAMP(0) | 可空 | 存储/验证时间 |
| `itemid` | INTEGER | NOT NULL | 测量项目标识 |
| `value` | VARCHAR(200) | 可空 | 测量值（文本） |
| `valuenum` | DOUBLE PRECISION | 可空 | 测量值（数值） |
| `valueuom` | VARCHAR(20) | 可空 | 计量单位 |
| `warning` | SMALLINT | 可空 | 警告标志 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| icustays | stay_id | 多对一 |
| d_items | itemid | 多对一 |

**注意事项：**

- **数据量巨大**: 这是MIMIC中最大的表，查询需要优化
- **数据频率**: 生命体征通常每小时记录，但可根据病情调整
- **数据质量**: 存在录入错误，分析前需进行数据清洗
- **时间差异**: charttime和storetime可能相差数小时
- **仅ICU数据**: 此表仅包含ICU期间的数据，普通病房数据不在此表

---

### `d_items` 表

**ICU项目字典**。`d_items` 是ICU模块的核心维度表（字典表），为ICU事件表中的 `itemid` 提供描述信息。所有ICU事件表（chartevents, inputevents, outputevents, procedureevents, ingredientevents）都通过 `itemid` 关联此表。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `itemid` | INTEGER | NOT NULL, 主键 | 项目唯一标识 |
| `label` | VARCHAR(200) | 可空 | 项目名称 |
| `abbreviation` | VARCHAR(100) | 可空 | 项目缩写 |
| `linksto` | VARCHAR(50) | 可空 | 链接到的表名 |
| `category` | VARCHAR(100) | 可空 | 项目类别 |
| `unitname` | VARCHAR(100) | 可空 | 计量单位 |
| `param_type` | VARCHAR(30) | 可空 | 参数类型 |
| `lownormalvalue` | FLOAT | 可空 | 正常范围下限 |
| `highnormalvalue` | FLOAT | 可空 | 正常范围上限 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `chartevents` | 图表事件（生命体征等） |
  | `inputevents` | 输入事件（输液等） |
  | `outputevents` | 输出事件（尿量等） |
  | `procedureevents` | 操作事件（机械通气等） |
  | `datetimeevents` | 日期时间事件 |

  | 值 | 说明 |
  |---|---|
  | `Routine Vital Signs` | 常规生命体征 |
  | `Hemodynamics` | 血流动力学 |
  | `Respiratory` | 呼吸相关 |
  | `Labs` | 实验室检验 |
  | `IV Medication` | 静脉用药 |
  | `Fluids - Intake` | 液体入量 |
  | `Output` | 排出量 |
  | `Procedures` | 操作/治疗 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| chartevents | itemid | 一对多 |
| inputevents | itemid | 一对多 |
| outputevents | itemid | 一对多 |
| procedureevents | itemid | 一对多 |
| ingredientevents | itemid | 一对多 |

**注意事项：**

- **仅MetaVision**: 此表仅包含MetaVision系统的项目（itemid>220000）
- **linksto字段**: 使用此字段确定数据在哪个表中
- **参考范围**: 部分项目没有参考范围信息
- **与MIMIC-III的区别**: MIMIC-III包含CareVue系统的项目，itemid不同

---

### `inputevents` 表

**静脉输液与药物输注**。`inputevents` 表记录患者在ICU期间接受的静脉输液和药物输注信息。包括持续输液（如血管活性药物）和间歇性给药（如抗生素）。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `stay_id` | INTEGER | NOT NULL | ICU入住标识 |
| `caregiver_id` | INTEGER | 可空 | 记录护士标识 |
| `starttime` | TIMESTAMP(0) | NOT NULL | 开始时间 |
| `endtime` | TIMESTAMP(0) | NOT NULL | 结束时间 |
| `storetime` | TIMESTAMP(0) | 可空 | 存储时间 |
| `itemid` | INTEGER | NOT NULL | 药物/液体标识 |
| `amount` | DOUBLE PRECISION | 可空 | 给药量 |
| `amountuom` | VARCHAR(30) | 可空 | 给药量单位 |
| `rate` | DOUBLE PRECISION | 可空 | 输注速率 |
| `rateuom` | VARCHAR(30) | 可空 | 速率单位 |
| `orderid` | BIGINT | 可空 | 医嘱ID |
| `linkorderid` | BIGINT | 可空 | 关联医嘱ID |
| `ordercategoryname` | VARCHAR(100) | 可空 | 医嘱类别名称 |
| `secondaryordercategoryname` | VARCHAR(100) | 可空 | 次级类别名称 |
| `ordercomponenttypedescription` | VARCHAR(200) | 可空 | 成分类型描述 |
| `ordercategorydescription` | VARCHAR(50) | 可空 | 医嘱类别描述 |
| `patientweight` | DOUBLE PRECISION | 可空 | 患者体重(kg) |
| `totalamount` | DOUBLE PRECISION | 可空 | 总量 |
| `totalamountuom` | VARCHAR(50) | 可空 | 总量单位 |
| `isopenbag` | SMALLINT | 可空 | 是否开放袋 |
| `statusdescription` | VARCHAR(30) | 可空 | 状态描述 |
| `originalamount` | DOUBLE PRECISION | 可空 | 原始药量 |
| `originalrate` | DOUBLE PRECISION | 可空 | 原始速率 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `Continuous Med` | 持续药物输注 |
  | `Drug Push` | 静脉推注 |
  | `Med Bolus` | 药物快速输注 |
  | `IV Fluid Bolus` | 液体快速输注 |

  | 值 | 说明 |
  |---|---|
  | `Main Parameter` | 主要成分 |
  | `Additive` | 添加剂 |
  | `Mixed Solution` | 混合溶液 |
  | `Base` | 基础液体 |

  | 值 | 说明 |
  |---|---|
  | `FinishedRunning` | 正常完成 |
  | `Stopped` | 停止 |
  | `Paused` | 暂停 |
  | `Changed` | 已更改 |
  | `Flushed` | 冲洗 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| icustays | stay_id | 多对一 |
| d_items | itemid | 多对一 |

**注意事项：**

- **速率调整**: 每次速率调整都产生新行，需要根据时间连续性合并分析
- **单位变化**: 同一药物可能使用不同单位（如mcg vs mg）
- **与emar的关系**: ICU期间的给药同时记录在 `inputevents` 和 `emar` 中
- **体重计算**: 使用 `patientweight` 验证按体重计算的剂量
- **混合液**: 一个输液袋可能包含多种药物，使用 `orderid` 关联

---

### `outputevents` 表

**排出量**。`outputevents` 表记录患者在ICU期间的排出量数据，包括尿量、引流液量、胃肠道排出量等。这是评估患者液体平衡的重要数据。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `stay_id` | INTEGER | NOT NULL | ICU入住标识 |
| `caregiver_id` | INTEGER | 可空 | 记录护士标识 |
| `charttime` | TIMESTAMP(3) | NOT NULL | 记录时间 |
| `storetime` | TIMESTAMP(3) | 可空 | 存储时间 |
| `itemid` | INTEGER | NOT NULL | 排出项目标识 |
| `value` | DOUBLE PRECISION | 可空 | 排出量 |
| `valueuom` | VARCHAR(20) | 可空 | 计量单位 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| icustays | stay_id | 多对一 |
| d_items | itemid | 多对一 |

**注意事项：**

- **尿量来源**: 包括导尿管尿量（Foley）和自主排尿（Void）
- **累计记录**: 每条记录是自上次清空以来的累计量
- **估计值**: 部分记录可能是估计值（如大便量）
- **手术室数据**: `OR Out` 记录手术期间的排出量
- **引流管编号**: 同类型引流管可能有多个（如Chest Tube #1, #2, #3）

---

### `procedureevents` 表

**ICU操作与治疗事件**。`procedureevents` 表记录ICU中有起止时间的操作和治疗事件，如机械通气、连续肾脏替代治疗（CRRT）、各类置管等。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `stay_id` | INTEGER | NOT NULL | ICU入住标识 |
| `caregiver_id` | INTEGER | 可空 | 记录护士标识 |
| `starttime` | TIMESTAMP | NOT NULL | 操作开始时间 |
| `endtime` | TIMESTAMP | NOT NULL | 操作结束时间 |
| `storetime` | TIMESTAMP | 可空 | 记录存储时间 |
| `itemid` | INTEGER | NOT NULL | 操作项目标识 |
| `value` | DOUBLE PRECISION | 可空 | 持续时间（数值） |
| `valueuom` | VARCHAR(20) | 可空 | 时间单位 |
| `location` | VARCHAR(100) | 可空 | 操作部位 |
| `locationcategory` | VARCHAR(50) | 可空 | 部位类别 |
| `orderid` | INTEGER | 可空 | 医嘱ID |
| `linkorderid` | INTEGER | 可空 | 关联医嘱ID |
| `ordercategoryname` | VARCHAR(50) | 可空 | 医嘱类别 |
| `ordercategorydescription` | VARCHAR(30) | 可空 | 类别描述 |
| `patientweight` | DOUBLE PRECISION | 可空 | 患者体重 |
| `isopenbag` | SMALLINT | 可空 | 是否开放袋 |
| `continueinnextdept` | SMALLINT | 可空 | 是否在下一科室继续 |
| `statusdescription` | VARCHAR(20) | 可空 | 状态描述 |
| `originalamount` | DOUBLE PRECISION | 可空 | 原始量 |
| `originalrate` | DOUBLE PRECISION | 可空 | 原始速率 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `Invasive Venous` | 有创静脉 |
  | `Invasive Arterial` | 有创动脉 |
  | `Airway` | 气道 |
  | `Unknown` | 未知 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| icustays | stay_id | 多对一 |
| d_items | itemid | 多对一 |

**注意事项：**

- **与procedures_icd的区别**:
- **机械通气记录**: 可能有多段记录（中断后重新开始）
- **状态信息**: 使用 `statusdescription` 判断操作是否正常完成
- **转科继续**: `continueinnextdept` 标识转出后是否继续

---

### `datetimeevents` 表

**日期时间记录**。`datetimeevents` 表记录ICU中以日期时间格式记录的信息，如末次透析日期、插管日期等。此表与 `chartevents` 表结构类似，但存储的值为日期时间类型而非数值或文本。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `stay_id` | INTEGER | NOT NULL | ICU入住标识 |
| `caregiver_id` | INTEGER | 可空 | 记录护士标识 |
| `charttime` | TIMESTAMP(0) | NOT NULL | 记录时间 |
| `storetime` | TIMESTAMP(0) | 可空 | 存储时间 |
| `itemid` | INTEGER | NOT NULL | 项目标识 |
| `value` | TIMESTAMP(0) | NOT NULL | 记录的日期时间值 |
| `valueuom` | VARCHAR(50) | 可空 | 值的单位 |
| `warning` | SMALLINT | 可空 | 警告标志 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| icustays | stay_id | 多对一 |
| d_items | itemid | 多对一 |
| caregiver | caregiver_id | 多对一 |

**注意事项：**

- **与chartevents区别**: 此表专门存储日期时间类型的值
- **value含义**: `value` 是记录的日期时间值，不是记录时间
- **数据稀疏**: 相比 `chartevents`，此表记录数量较少
- **项目定义**: 使用 `d_items` 表查询具体项目含义
- **去标识化**: 所有日期时间已进行去标识化偏移

---

### `ingredientevents` 表

**输液成分详情**。`ingredientevents` 表记录输液中各成分的详细信息，特别是营养液中的成分（如蛋白质、脂肪、葡萄糖含量）和水分含量。是 `inputevents` 表的补充。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `stay_id` | INTEGER | NOT NULL | ICU入住标识 |
| `caregiver_id` | INTEGER | 可空 | 记录护士标识 |
| `starttime` | TIMESTAMP(0) | NOT NULL | 开始时间 |
| `endtime` | TIMESTAMP(0) | NOT NULL | 结束时间 |
| `storetime` | TIMESTAMP(0) | 可空 | 存储时间 |
| `itemid` | INTEGER | NOT NULL | 成分标识 |
| `amount` | DOUBLE PRECISION | 可空 | 给予量 |
| `amountuom` | VARCHAR(20) | 可空 | 给予量单位 |
| `rate` | DOUBLE PRECISION | 可空 | 输注速率 |
| `rateuom` | VARCHAR(20) | 可空 | 速率单位 |
| `orderid` | INTEGER | 可空 | 医嘱ID |
| `linkorderid` | INTEGER | 可空 | 关联医嘱ID |
| `statusdescription` | VARCHAR(20) | 可空 | 状态描述 |
| `originalamount` | DOUBLE PRECISION | 可空 | 原始量 |
| `originalrate` | DOUBLE PRECISION | 可空 | 原始速率 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| icustays | stay_id | 多对一 |
| d_items | itemid | 多对一 |
| inputevents | orderid | 多对一 |

**注意事项：**

- **与inputevents的关系**: 使用 `orderid` 将成分关联到具体输液
- **MIMIC-IV新增**: 此表是MIMIC-IV新增的，MIMIC-III没有
- **主要用于营养分析**: 最常见的用途是分析肠外营养成分
- **水含量**: 可用于更精确地计算液体摄入量

---

### `caregiver` 表

**护理人员字典**。`caregiver` 表是ICU模块中护理人员（Caregiver）的维度表，列出所有在ICU信息系统中记录数据的护理人员标识。与HOSP模块的 `provider` 表类似，但专用于ICU模块。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `caregiver_id` | INTEGER | NOT NULL, 主键 | 护理人员唯一标识 |

**外键关系：**

此表作为维度表被ICU模块的事件表引用：

| 引用表 | 引用字段 | 说明 |
|--------|----------|------|
| chartevents | caregiver_id | 记录护士 |
| inputevents | caregiver_id | 记录护士 |
| outputevents | caregiver_id | 记录护士 |
| procedureevents | caregiver_id | 记录护士 |
| ingredientevents | caregiver_id | 记录护士 |

**注意事项：**

- **无详细信息**: 此表仅包含标识符，无护理人员详细信息
- **ICU专用**: 仅用于ICU模块，HOSP模块使用 `provider` 表
- **去标识化**: 标识符已去标识化，无法追溯到真实个人
- **可选字段**: 在事件表中 `caregiver_id` 可能为空
- **不同标识体系**: `caregiver_id` 和 `provider_id` 是独立的标识体系

---

## 四、NOTE 模块（临床文本模块）

> 共 4 张表。

| 表名 | 说明 |
|------|------|
| [`discharge`](#discharge-表) | 出院小结 |
| [`discharge_detail`](#discharge_detail-表) | 出院小结补充信息 |
| [`radiology`](#radiology-表) | 放射学报告 |
| [`radiology_detail`](#radiology_detail-表) | 放射学报告补充信息 |

### `discharge` 表

**出院小结**。`discharge` 表存储患者的出院小结（Discharge Summary），是详细记录患者整个住院过程的临床文本。出院小结包含主诉、现病史、既往史、住院经过、出院诊断等重要信息。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `note_id` | VARCHAR(25) | NOT NULL, 主键 | 文档唯一标识 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `note_type` | CHAR(2) | NOT NULL | 文档类型 |
| `note_seq` | INTEGER | NOT NULL | 文档序号 |
| `charttime` | TIMESTAMP | NOT NULL | 文档记录时间 |
| `storetime` | TIMESTAMP | 可空 | 文档存储时间 |
| `text` | TEXT | NOT NULL | 出院小结全文 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `DS` | Discharge Summary（出院小结） |
  | `AD` | Addendum（补充记录） |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| discharge_detail | note_id | 一对多 |

**注意事项：**

- **自由文本**: 出院小结是非结构化的自由文本
- **格式变化**: 不同医生的写作风格和章节安排可能不同
- **去标识化痕迹**: `___` 表示已移除的敏感信息
- **章节缺失**: 社会史和出院指导章节已被完全移除
- **补充记录**: 可能存在后续的补充记录（Addendum）

---

### `discharge_detail` 表

**出院小结补充信息**。`discharge_detail` 表存储与出院小结相关的补充结构化信息，采用实体-属性-值（EAV）模型。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `note_id` | VARCHAR(25) | NOT NULL | 文档唯一标识 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `field_name` | VARCHAR(255) | NOT NULL | 属性名称 |
| `field_value` | TEXT | NOT NULL | 属性值 |
| `field_ordinal` | INTEGER | NOT NULL | 属性序号 |

**主键**: (`note_id`, `field_name`, `field_ordinal`)

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| discharge | note_id | 多对一 |
| patients | subject_id | 多对一 |

**注意事项：**

- **信息有限**: 目前此表主要包含作者信息
- **EAV模型**: 采用灵活的实体-属性-值结构
- **与主表关联**: 通过 `note_id` 与 `discharge` 表关联

---

### `radiology` 表

**放射学报告**。`radiology` 表存储放射学检查报告，包括X线、CT、MRI、超声等各类影像学检查的报告文本。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `note_id` | VARCHAR(25) | NOT NULL, 主键 | 报告唯一标识 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `note_type` | CHAR(2) | NOT NULL | 报告类型 |
| `note_seq` | INTEGER | NOT NULL | 报告序号 |
| `charttime` | TIMESTAMP | NOT NULL | 检查时间 |
| `storetime` | TIMESTAMP | 可空 | 报告完成时间 |
| `text` | TEXT | NOT NULL | 报告全文 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `RR` | Radiology Report（放射学报告） |
  | `AR` | Addendum Report（补充报告） |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| radiology_detail | note_id | 一对多 |

**注意事项：**

- **自由文本**: 报告是非结构化文本
- **结构化程度**: 放射学报告通常比出院小结更结构化
- **补充报告**: 可能存在后续的补充报告（Addendum）
- **检查详情**: 检查类型、CPT编码等在 `radiology_detail` 表中
- **去标识化**: 已移除患者可识别信息

---

### `radiology_detail` 表

**放射学报告补充信息**。`radiology_detail` 表存储与放射学报告相关的结构化补充信息，包括检查名称、检查代码、CPT编码等。采用实体-属性-值（EAV）模型。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `note_id` | VARCHAR(25) | NOT NULL | 报告唯一标识 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `field_name` | VARCHAR(255) | NOT NULL | 属性名称 |
| `field_value` | TEXT | NOT NULL | 属性值 |
| `field_ordinal` | INTEGER | NOT NULL | 属性序号 |

**主键**: (`note_id`, `field_name`, `field_ordinal`)

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `exam_name` | 检查名称 |
  | `exam_code` | 检查代码 |
  | `cpt_code` | CPT编码 |
  | `parent_note_id` | 父报告ID（用于补充报告） |
  | `addendum_note_id` | 补充报告ID |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| radiology | note_id | 多对一 |
| patients | subject_id | 多对一 |

**注意事项：**

- **EAV模型**: 采用灵活的实体-属性-值结构
- **多值属性**: 同一报告可能有多个CPT编码
- **补充报告**: 使用 `addendum_note_id` 和 `parent_note_id` 追踪补充报告关系
- **与主表关联**: 必须通过 `note_id` 与 `radiology` 表关联获取完整信息

---

## 五、ED 模块（急诊模块）

> 共 6 张表。

| 表名 | 说明 |
|------|------|
| [`edstays`](#edstays-表) | 急诊就诊记录 |
| [`triage`](#triage-表) | 分诊评估 |
| [`vitalsign`](#vitalsign-表) | 急诊生命体征 |
| [`diagnosis`](#diagnosis-表) | 急诊诊断 |
| [`medrecon`](#medrecon-表) | 用药核对 |
| [`pyxis`](#pyxis-表) | 急诊发药记录 |

### `edstays` 表

**急诊就诊记录**。`edstays` 表是急诊科（Emergency Department, ED）数据的核心追踪表，记录患者的急诊就诊信息，包括入科时间、出科时间、到达方式和离开去向等。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | 可空 | 住院唯一标识 |
| `stay_id` | INTEGER | NOT NULL | 急诊就诊唯一标识 |
| `intime` | TIMESTAMP(0) | NOT NULL | 急诊入科时间 |
| `outtime` | TIMESTAMP(0) | NOT NULL | 急诊出科时间 |
| `gender` | VARCHAR(1) | NOT NULL | 性别 |
| `race` | VARCHAR(60) | 可空 | 种族 |
| `arrival_transport` | VARCHAR(50) | NOT NULL | 到达方式 |
| `disposition` | VARCHAR(255) | 可空 | 离开去向 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | `WALK IN` | 步行到达 |
  | `AMBULANCE` | 救护车 |
  | `HELICOPTER` | 直升机 |
  | `OTHER` | 其他 |

  | 值 | 说明 |
  |---|---|
  | `HOME` | 回家 |
  | `ADMITTED` | 收入院 |
  | `TRANSFER` | 转院 |
  | `LEFT WITHOUT BEING SEEN` | 未就诊即离开 |
  | `LEFT AGAINST MEDICAL ADVICE` | 自动出院 |
  | `EXPIRED` | 死亡 |

**外键关系：**

| 关联表 | 关联字段 | 关系 | 说明 |
|--------|----------|------|------|
| patients | subject_id | 多对一 | 关联患者基本信息 |
| admissions | hadm_id | 多对一 | 关联住院记录（如有） |
| diagnosis | stay_id | 一对多 | 急诊诊断 |
| medrecon | stay_id | 一对多 | 用药核对 |
| pyxis | stay_id | 一对多 | 急诊发药 |
| triage | stay_id | 一对一 | 分诊评估 |
| vitalsign | stay_id | 一对多 | 生命体征 |

**注意事项：**

- **stay_id 独立性**: ED的 `stay_id` 与ICU的 `stay_id` 是独立的标识符序列
- **hadm_id 可空**: 未收入院的患者 `hadm_id` 为 NULL
- **种族数据**: `race` 为自报数据，可能存在缺失或不准确
- **时间偏移**: 与MIMIC-IV其他数据一样，时间已进行去标识化偏移

---

### `triage` 表

**分诊评估**。`triage` 表记录急诊分诊评估信息，包括患者到达急诊时的生命体征、疼痛评分、急诊严重指数（ESI）分级和主诉。分诊是急诊护理流程的第一步，决定患者的就诊优先级。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `stay_id` | INTEGER | NOT NULL | 急诊就诊唯一标识 |
| `temperature` | NUMERIC(10,4) | 可空 | 体温（华氏度） |
| `heartrate` | NUMERIC(10,4) | 可空 | 心率（次/分） |
| `resprate` | NUMERIC(10,4) | 可空 | 呼吸频率（次/分） |
| `o2sat` | NUMERIC(10,4) | 可空 | 血氧饱和度（%） |
| `sbp` | NUMERIC(10,4) | 可空 | 收缩压（mmHg） |
| `dbp` | NUMERIC(10,4) | 可空 | 舒张压（mmHg） |
| `pain` | TEXT | 可空 | 疼痛评分（0-10） |
| `acuity` | NUMERIC(10,4) | 可空 | ESI分级（1-5） |
| `chiefcomplaint` | VARCHAR(255) | 可空 | 主诉 |

**关键字段取值与枚举：**

  | 分级 | 说明 |
  |---|---|
  | 1 | 需要立即抢救 |
  | 2 | 高风险状态，意识改变或严重疼痛 |
  | 3 | 需要多项资源 |
  | 4 | 需要一项资源 |
  | 5 | 不需要资源 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| edstays | stay_id | 一对一 |
| patients | subject_id | 多对一 |

**注意事项：**

- **一对一关系**: 每次急诊就诊只有一条分诊记录
- **华氏度**: 体温单位为华氏度，需要转换
- **缺失值**: 部分字段可能有缺失值
- **主诉去标识化**: 主诉已去标识化，可能影响分析
- **疼痛评分**: `pain` 为TEXT类型，可能包含非数字值
- **ESI系统**: ESI是美国常用的分诊系统，其他国家可能使用不同系统

---

### `vitalsign` 表

**急诊生命体征**。`vitalsign` 表记录患者在急诊期间的生命体征测量值。与 `triage` 表记录的分诊时单次评估不同，此表记录急诊停留期间的多次生命体征测量。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `stay_id` | INTEGER | NOT NULL | 急诊就诊唯一标识 |
| `charttime` | TIMESTAMP(0) | 可空 | 记录时间 |
| `temperature` | NUMERIC(10,4) | 可空 | 体温（华氏度） |
| `heartrate` | NUMERIC(10,4) | 可空 | 心率（次/分） |
| `resprate` | NUMERIC(10,4) | 可空 | 呼吸频率（次/分） |
| `o2sat` | NUMERIC(10,4) | 可空 | 血氧饱和度（%） |
| `sbp` | INTEGER | 可空 | 收缩压（mmHg） |
| `dbp` | INTEGER | 可空 | 舒张压（mmHg） |
| `rhythm` | TEXT | 可空 | 心律 |
| `pain` | TEXT | 可空 | 疼痛评分（0-10） |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| edstays | stay_id | 多对一 |
| patients | subject_id | 多对一 |

**注意事项：**

- **与triage区别**: `triage` 记录分诊时单次评估，`vitalsign` 记录急诊期间多次测量
- **华氏度**: 体温单位为华氏度
- **数据类型差异**: `sbp`/`dbp` 为INTEGER，与 `triage` 表略有不同
- **缺失值**: 部分去标识化导致的自由文本无法转换，造成缺失值
- **心律描述**: `rhythm` 为自由文本，格式可能不统一
- **测量频率**: 测量频率取决于患者情况和临床需求

---

### `diagnosis` 表

**急诊诊断**。`diagnosis` 表存储急诊科患者的诊断信息，使用ICD编码系统（ICD-9或ICD-10）记录。此表记录的是急诊阶段的诊断，与住院诊断（`diagnoses_icd`）是不同的。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `stay_id` | INTEGER | NOT NULL | 急诊就诊唯一标识 |
| `seq_num` | INTEGER | NOT NULL | 诊断序号 |
| `icd_code` | VARCHAR(10) | NOT NULL | ICD诊断编码 |
| `icd_version` | INTEGER | NOT NULL | ICD版本（9或10） |
| `icd_title` | TEXT | NOT NULL | 诊断描述 |

**关键字段取值与枚举：**

  | 值 | 说明 |
  |---|---|
  | 9 | ICD-9-CM编码 |
  | 10 | ICD-10-CM编码 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| edstays | stay_id | 多对一 |
| patients | subject_id | 多对一 |
| d_icd_diagnoses | icd_code, icd_version | 多对一 |

**注意事项：**

- **急诊诊断**: 此表记录的是急诊阶段的诊断，可能与最终住院诊断不同
- **诊断时机**: 急诊诊断通常在信息有限的情况下做出
- **ICD版本混合**: 数据集中同时包含ICD-9和ICD-10编码
- **与住院诊断区分**: 此表（ED模块）与 `diagnoses_icd`（HOSP模块）是不同的表

---

### `medrecon` 表

**用药核对**。`medrecon` 表记录急诊用药核对（Medicine Reconciliation）信息，即患者到达急诊时报告的正在服用的药物。这是了解患者基础用药情况的重要数据来源。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `stay_id` | INTEGER | NOT NULL | 急诊就诊唯一标识 |
| `charttime` | TIMESTAMP(0) | 可空 | 记录时间 |
| `name` | VARCHAR(255) | 可空 | 药物名称 |
| `gsn` | VARCHAR(10) | 可空 | GSN编码 |
| `ndc` | VARCHAR(12) | 可空 | NDC编码 |
| `etc_rn` | SMALLINT | NOT NULL | 药物分类序号 |
| `etccode` | VARCHAR(8) | 可空 | ETC分类编码 |
| `etcdescription` | VARCHAR(255) | 可空 | ETC分类描述 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| edstays | stay_id | 多对一 |
| patients | subject_id | 多对一 |

**注意事项：**

- **自报数据**: 用药信息来自患者自报，可能不完整或不准确
- **非处方药**: 可能包含OTC药物和保健品
- **剂量缺失**: 此表不包含具体剂量信息
- **多分类**: 同一药物可能有多个ETC分类（`etc_rn`区分）
- **时间限制**: 仅记录急诊就诊时的用药情况

---

### `pyxis` 表

**急诊发药记录**。`pyxis` 表记录急诊科通过Pyxis自动发药系统发放的药物。Pyxis是一种常见的医院自动发药柜系统，用于安全、高效地分发药物。

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `stay_id` | INTEGER | NOT NULL | 急诊就诊唯一标识 |
| `charttime` | TIMESTAMP(0) | 可空 | 发药记录时间 |
| `med_rn` | SMALLINT | NOT NULL | 单次发药的行号 |
| `name` | VARCHAR(255) | 可空 | 药物名称 |
| `gsn` | VARCHAR(10) | 可空 | GSN编码 |
| `gsn_rn` | SMALLINT | NOT NULL | GSN分组行号 |

**外键关系：**

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| edstays | stay_id | 多对一 |
| patients | subject_id | 多对一 |

**注意事项：**

- **发药vs给药**: 此表记录的是发药（dispensing），而非实际给药（administration）
- **多GSN关联**: 同一药物可能有多个GSN值（用 `gsn_rn` 区分）
- **时间近似**: `charttime` 近似于用药时间，但可能有延迟
- **仅限急诊**: 仅包含急诊期间的发药，不包括后续住院
- **与medrecon区别**: `pyxis` 是急诊期间的发药，`medrecon` 是入院前的用药核对

---

## 附录

### A. EAV 模型说明

MIMIC-IV 中以下表采用实体-属性-值（EAV）模型存储灵活的补充信息：

| 表 | field_name 示例 | 说明 |
|----|-----------------|------|
| `discharge_detail` | `author` | 出院小结作者 |
| `radiology_detail` | `exam_name`, `exam_code`, `cpt_code` | 放射学检查详情 |
| `poe_detail` | `Dose`, `Route`, `Frequency` | 医嘱补充属性 |

查询时需通过透视（pivot）操作将 EAV 转换为宽表格式。

### B. 时间去标识化

- 所有日期已偏移至 2100 年代，患者级别的偏移量保持时间间隔不变
- 通过 `patients.anchor_year`、`anchor_age`、`anchor_year_group` 可推算真实年份范围
- ≥89 岁患者年龄统一设置为 91

### C. HOSP 与 ICU 提供者标识的区别

| | HOSP 模块 | ICU 模块 |
|---|---|---|
| 标识符 | `provider_id` (VARCHAR, P开头) | `caregiver_id` (INTEGER) |
| 字典表 | `provider` | `caregiver` |
| 引用位置 | admissions, emar, poe, labevents, pharmacy | chartevents, inputevents, outputevents 等 |

### D. ICU 与 ED 的 stay_id 是独立的

- ICU 的 `stay_id` 来自 `icustays`，标识每次 ICU 入住
- ED 的 `stay_id` 来自 `edstays`，标识每次急诊就诊
- 两者是不同的标识符序列，不可混淆

### E. 数据文件索引

#### mimic-iv-3.1/ (HOSP + ICU)

| 文件 | 模块 | 说明 |
|------|------|------|
| `admissions.csv.gz` | hosp | 住院记录 |
| `d_hcpcs.csv.gz` | hosp | HCPCS编码字典 |
| `d_icd_diagnoses.csv.gz` | hosp | 诊断编码字典 |
| `d_icd_procedures.csv.gz` | hosp | 操作编码字典 |
| `d_labitems.csv.gz` | hosp | 检验项目字典 |
| `diagnoses_icd.csv.gz` | hosp | 诊断编码 |
| `drgcodes.csv.gz` | hosp | DRG分组 |
| `emar.csv.gz` | hosp | 给药记录 |
| `emar_detail.csv.gz` | hosp | 给药详情 |
| `hcpcsevents.csv.gz` | hosp | HCPCS事件 |
| `labevents.csv.gz` | hosp | 检验结果 |
| `microbiologyevents.csv.gz` | hosp | 微生物检验 |
| `omr.csv.gz` | hosp | 在线医疗记录 |
| `patients.csv.gz` | hosp | 患者信息 |
| `pharmacy.csv.gz` | hosp | 药房记录 |
| `poe.csv.gz` | hosp | 医嘱录入 |
| `poe_detail.csv.gz` | hosp | 医嘱详情 |
| `prescriptions.csv.gz` | hosp | 药物处方 |
| `procedures_icd.csv.gz` | hosp | 操作编码 |
| `provider.csv.gz` | hosp | 提供者字典 |
| `services.csv.gz` | hosp | 服务科室 |
| `transfers.csv.gz` | hosp | 院内转移 |
| `icu/caregiver.csv.gz` | icu | 护理人员字典 |
| `icu/chartevents.csv.gz` | icu | 床旁观察(最大表) |
| `icu/d_items.csv.gz` | icu | ICU项目字典 |
| `icu/datetimeevents.csv.gz` | icu | 日期时间记录 |
| `icu/icustays.csv.gz` | icu | ICU入住记录 |
| `icu/ingredientevents.csv.gz` | icu | 输液成分 |
| `icu/inputevents.csv.gz` | icu | 输液与药物输注 |
| `icu/outputevents.csv.gz` | icu | 排出量 |
| `icu/procedureevents.csv.gz` | icu | ICU操作事件 |

#### mimic-iv-note-2.2/note/

| `discharge.csv.gz` | note | 出院小结 |
| `discharge_detail.csv.gz` | note | 出院小结补充 |
| `radiology.csv.gz` | note | 放射学报告 |
| `radiology_detail.csv.gz` | note | 放射学报告补充 |

#### mimic-iv-ed/ed/

| `diagnosis.csv.gz` | ed | 急诊诊断 |
| `edstays.csv.gz` | ed | 急诊就诊 |
| `medrecon.csv.gz` | ed | 用药核对 |
| `pyxis.csv.gz` | ed | 急诊发药 |
| `triage.csv.gz` | ed | 分诊评估 |
| `vitalsign.csv.gz` | ed | 急诊生命体征 |
