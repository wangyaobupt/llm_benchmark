# admissions 表

## 概述

`admissions` 表记录患者的住院信息，每次住院对应一行记录。包含入院和出院时间、入院类型、来源和去向等关键信息。

## 表结构

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

## 字段详解

### subject_id
- **含义**: 患者唯一标识，关联 `patients` 表
- **使用说明**: 同一患者多次住院会有多行记录，但 `subject_id` 相同

### hadm_id
- **含义**: 住院唯一标识符
- **取值范围**: 2000000 - 2999999
- **ETL映射**: 对应医院系统中的住院号或就诊流水号

### admittime / dischtime
- **含义**: 入院和出院的日期时间
- **说明**: 经过日期偏移处理，但保持时间间隔不变
- **ETL映射**: 对应医院系统中的入院登记时间和出院时间

### deathtime
- **含义**: 院内死亡的具体时间
- **说明**: 仅当患者在院内死亡时有值
- **与 `hospital_expire_flag` 的关系**: 当此字段有值时，`hospital_expire_flag` = 1

### admission_type
- **含义**: 入院类型，反映入院的紧急程度
- **取值**:
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

### admit_provider_id
- **含义**: 接诊医生的匿名标识
- **格式**: 如 "P003AB" 或 "P00102"

### admission_location
- **含义**: 患者入院前所在位置
- **常见取值**:
  - `EMERGENCY ROOM` - 急诊室
  - `PHYSICIAN REFERRAL` - 医生转诊
  - `TRANSFER FROM HOSPITAL` - 外院转入
  - `CLINIC REFERRAL` - 门诊转诊
  - `WALK-IN/SELF REFERRAL` - 自行就诊

### discharge_location
- **含义**: 患者出院后去向
- **常见取值**:
  - `HOME` - 回家
  - `HOME HEALTH CARE` - 居家护理
  - `SKILLED NURSING FACILITY` - 专业护理机构
  - `REHAB` - 康复中心
  - `HOSPICE` - 临终关怀
  - `DIED` - 死亡
  - `AGAINST ADVICE` - 自动出院

### insurance
- **含义**: 患者保险类型
- **常见取值**: `Medicare`, `Medicaid`, `Other`
- **说明**: 同一患者不同次住院的保险可能不同

### language
- **含义**: 患者首选语言
- **说明**: 用于沟通和护理计划

### marital_status
- **含义**: 婚姻状态
- **取值**: `MARRIED`, `SINGLE`, `DIVORCED`, `WIDOWED` 等

### race
- **含义**: 患者自报的种族/民族
- **说明**: 已进行适当聚合以保护隐私

### edregtime / edouttime
- **含义**: 急诊室登记时间和离开时间
- **说明**: 仅对经急诊入院的患者有值
- **用途**: 计算急诊停留时间

### hospital_expire_flag
- **含义**: 院内死亡标志
- **取值**: `0` = 存活出院, `1` = 院内死亡

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| transfers | hadm_id | 一对多 |
| icustays | hadm_id | 一对多 |
| diagnoses_icd | hadm_id | 一对多 |
| procedures_icd | hadm_id | 一对多 |
| labevents | hadm_id | 一对多 |
| prescriptions | hadm_id | 一对多 |

## ETL映射建议

1. **住院ID**: 建立本地住院号到 `hadm_id` 的映射
2. **入院类型标准化**: 将本地入院类型映射到MIMIC的九种分类
3. **位置信息**: 标准化入院来源和出院去向的编码
4. **时间处理**:
   - 保持 `admittime` < `dischtime` 的关系
   - 急诊时间应在入院时间之前
5. **死亡处理**:
   - 院内死亡时设置 `deathtime` 和 `hospital_expire_flag`
   - 确保 `deathtime` 在 `admittime` 和 `dischtime` 之间

## 注意事项

1. **器官捐献账户**: 部分记录可能是器官捐献相关的特殊账户，可能出现极短甚至负数的住院时长
2. **人口统计信息变化**: 同一患者的保险、婚姻状态等可能在不同次住院时有所变化
3. **急诊数据**: 并非所有入院都有急诊数据，取决于入院途径
