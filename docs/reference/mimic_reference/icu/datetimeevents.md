# datetimeevents 表

## 概述

`datetimeevents` 表记录ICU中以日期时间格式记录的信息，如末次透析日期、插管日期等。此表与 `chartevents` 表结构类似，但存储的值为日期时间类型而非数值或文本。

## 表结构

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

## 字段详解

### subject_id / hadm_id / stay_id
- **含义**: 患者、住院和ICU入住的唯一标识
- **关联**: 分别关联 `patients`、`admissions` 和 `icustays` 表

### caregiver_id
- **含义**: 记录此信息的护理人员
- **关联**: 关联 `caregiver` 表

### charttime
- **含义**: 信息记录的时间
- **说明**: 表示这个日期时间信息是在什么时候被记录的

### storetime
- **含义**: 数据存储到系统的时间
- **说明**: 通常等于或晚于 `charttime`

### itemid
- **含义**: 记录项目的标识
- **关联**: 关联 `d_items` 表获取项目名称

### value
- **含义**: 记录的日期时间值
- **说明**: 这是实际记录的日期时间，如"末次透析日期"
- **类型**: TIMESTAMP

### valueuom
- **含义**: 值的单位（通常为空或日期相关单位）

### warning
- **含义**: 警告标志
- **用途**: 标识异常或需要关注的值

## 常见记录项目

| itemid | 项目名称 | 说明 |
|--------|----------|------|
| 224191 | Date of Last Dialysis | 末次透析日期 |
| 225059 | Intubation Date | 插管日期 |
| 225060 | Extubation Date | 拔管日期 |
| 225324 | Date of PICC Insertion | PICC置管日期 |
| 227578 | Date of CVC Insertion | 中心静脉置管日期 |

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| icustays | stay_id | 多对一 |
| d_items | itemid | 多对一 |
| caregiver | caregiver_id | 多对一 |

## 使用示例

### 查询患者的日期时间记录

```sql
SELECT
    de.stay_id,
    de.charttime,
    d.label as item_name,
    de.value as recorded_datetime
FROM datetimeevents de
INNER JOIN d_items d ON de.itemid = d.itemid
WHERE de.stay_id = 12345678
ORDER BY de.charttime;
```

### 查询末次透析日期

```sql
SELECT
    stay_id,
    charttime,
    value as last_dialysis_date
FROM datetimeevents
WHERE itemid = 224191  -- Date of Last Dialysis
ORDER BY charttime;
```

### 计算透析间隔天数

```sql
SELECT
    de.stay_id,
    de.charttime as record_time,
    de.value as last_dialysis_date,
    de.charttime::date - de.value::date as days_since_dialysis
FROM datetimeevents de
WHERE de.itemid = 224191
ORDER BY de.stay_id, de.charttime;
```

### 查询插管和拔管日期

```sql
SELECT
    stay_id,
    MAX(CASE WHEN itemid = 225059 THEN value END) as intubation_date,
    MAX(CASE WHEN itemid = 225060 THEN value END) as extubation_date
FROM datetimeevents
WHERE itemid IN (225059, 225060)
GROUP BY stay_id
HAVING MAX(CASE WHEN itemid = 225059 THEN value END) IS NOT NULL;
```

### 统计各类日期时间记录

```sql
SELECT
    d.label as item_name,
    COUNT(*) as record_count
FROM datetimeevents de
INNER JOIN d_items d ON de.itemid = d.itemid
GROUP BY d.label
ORDER BY record_count DESC
LIMIT 20;
```

### 关联ICU入住信息

```sql
SELECT
    i.stay_id,
    i.intime,
    i.outtime,
    de.value as procedure_date,
    d.label as procedure_type
FROM icustays i
INNER JOIN datetimeevents de ON i.stay_id = de.stay_id
INNER JOIN d_items d ON de.itemid = d.itemid
WHERE i.subject_id = 12345678
ORDER BY de.value;
```

## 应用场景

### 1. 透析管理
- 追踪透析患者的治疗历史
- 计算透析间隔时间

### 2. 机械通气分析
- 记录插管和拔管时间
- 计算机械通气持续时间

### 3. 置管追踪
- 追踪各类导管的置入时间
- 评估导管相关感染风险

### 4. 时间线构建
- 构建患者诊疗时间线
- 分析事件发生的先后顺序

## ETL映射建议

1. **项目映射**: 通过 `d_items` 表获取项目定义
2. **日期格式**: 确保日期时间格式的正确转换
3. **时间关联**: 注意 `charttime`（记录时间）和 `value`（记录的日期值）的区别

## 注意事项

1. **与chartevents区别**: 此表专门存储日期时间类型的值
2. **value含义**: `value` 是记录的日期时间值，不是记录时间
3. **数据稀疏**: 相比 `chartevents`，此表记录数量较少
4. **项目定义**: 使用 `d_items` 表查询具体项目含义
5. **去标识化**: 所有日期时间已进行去标识化偏移
