# services 表

## 概述

`services` 表记录患者在住院期间接受治疗的医疗服务/科室。一次住院可能由多个科室先后负责治疗。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `transfertime` | TIMESTAMP(0) | NOT NULL | 转科时间 |
| `prev_service` | VARCHAR(20) | 可空 | 前一个服务科室 |
| `curr_service` | VARCHAR(20) | NOT NULL | 当前服务科室 |

## 字段详解

### transfertime
- **含义**: 患者从前一科室转入当前科室的时间
- **说明**: 第一条记录是入院时分配的科室，此时 `prev_service` 为空

### prev_service / curr_service
- **含义**: 前一个和当前负责患者治疗的科室
- **注意**: 这是医疗服务科室，不是物理位置（物理位置见 `transfers` 表）

### 科室代码说明

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

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |

## services vs transfers

| 特性 | services | transfers |
|------|----------|-----------|
| 记录内容 | 医疗服务科室 | 物理位置/病房 |
| 含义 | 哪个团队负责治疗 | 患者在哪个病房 |
| 可同时存在 | 是 | 否 |

一个患者可以在内科ICU（transfers记录）接受心内科（services记录）团队的治疗。

## 使用示例

### 查询患者的科室转换历史

```sql
SELECT
    subject_id,
    hadm_id,
    transfertime,
    prev_service,
    curr_service
FROM services
WHERE hadm_id = 12345678
ORDER BY transfertime;
```

### 统计各科室的患者数

```sql
SELECT
    curr_service,
    COUNT(DISTINCT hadm_id) as admission_count
FROM services
GROUP BY curr_service
ORDER BY admission_count DESC;
```

### 联合查询科室和病房

```sql
SELECT
    s.hadm_id,
    s.transfertime as service_time,
    s.curr_service,
    t.intime as ward_time,
    t.careunit
FROM services s
LEFT JOIN transfers t ON s.hadm_id = t.hadm_id
WHERE s.hadm_id = 12345678
ORDER BY s.transfertime;
```

## ETL映射建议

1. **科室代码映射**: 将本地科室代码映射到MIMIC的科室代码
2. **转科时间**: 记录患者医疗服务变更的时间
3. **区分概念**: 注意区分医疗服务（services）和物理位置（transfers）

## 注意事项

1. 大部分住院只有一条 `services` 记录
2. 科室变更通常发生在病情变化或需要专科会诊时
3. `services` 记录的是负责治疗的团队，而非患者的物理位置
