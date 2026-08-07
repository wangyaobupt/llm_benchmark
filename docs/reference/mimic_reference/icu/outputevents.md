# outputevents 表

## 概述

`outputevents` 表记录患者在ICU期间的排出量数据，包括尿量、引流液量、胃肠道排出量等。这是评估患者液体平衡的重要数据。

## 表结构

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

## 字段详解

### charttime
- **含义**: 排出量记录的时间点
- **说明**: 通常是护士清空引流袋/尿袋的时间

### itemid
- **含义**: 排出项目的标识符
- **关联**: 连接 `d_items` 表获取项目名称

### value
- **含义**: 排出的量
- **单位**: 通常为ml

### valueuom
- **含义**: 计量单位
- **常见值**: ml

## 常见排出项目

| itemid | 项目名称 | 中文说明 |
|--------|----------|----------|
| 226559 | Foley | 导尿管尿量 |
| 226560 | Void | 自主排尿 |
| 226561 | Chest Tube #1 | 胸管引流#1 |
| 226563 | Chest Tube #2 | 胸管引流#2 |
| 226564 | Chest Tube #3 | 胸管引流#3 |
| 226575 | Jackson Pratt #1 | JP引流管#1 |
| 226576 | Jackson Pratt #2 | JP引流管#2 |
| 226580 | Gastric | 胃管引流 |
| 226582 | Hemovac | 负压引流 |
| 226588 | Stool | 大便 |
| 226571 | Blood Loss (Measured) | 失血量（测量） |
| 226567 | OR Out | 手术室排出 |

## 数据规模

- 总行数: 4,234,967 行
- 来源: MetaVision ICU信息系统

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| icustays | stay_id | 多对一 |
| d_items | itemid | 多对一 |

## 使用示例

### 查询患者每日尿量

```sql
SELECT
    stay_id,
    DATE(charttime) as date,
    SUM(value) as daily_urine_output_ml
FROM outputevents
WHERE stay_id = 12345678
  AND itemid IN (226559, 226560)  -- Foley和Void
GROUP BY stay_id, DATE(charttime)
ORDER BY date;
```

### 统计各类排出量

```sql
SELECT
    d.label as output_type,
    SUM(o.value) as total_ml
FROM outputevents o
INNER JOIN d_items d ON o.itemid = d.itemid
WHERE o.stay_id = 12345678
GROUP BY d.label
ORDER BY total_ml DESC;
```

### 计算液体平衡

```sql
WITH daily_input AS (
    SELECT
        stay_id,
        DATE(starttime) as date,
        SUM(amount) as input_ml
    FROM inputevents
    WHERE amountuom = 'ml'
    GROUP BY stay_id, DATE(starttime)
),
daily_output AS (
    SELECT
        stay_id,
        DATE(charttime) as date,
        SUM(value) as output_ml
    FROM outputevents
    GROUP BY stay_id, DATE(charttime)
)
SELECT
    COALESCE(i.stay_id, o.stay_id) as stay_id,
    COALESCE(i.date, o.date) as date,
    COALESCE(i.input_ml, 0) as input_ml,
    COALESCE(o.output_ml, 0) as output_ml,
    COALESCE(i.input_ml, 0) - COALESCE(o.output_ml, 0) as balance
FROM daily_input i
FULL OUTER JOIN daily_output o
    ON i.stay_id = o.stay_id AND i.date = o.date
WHERE COALESCE(i.stay_id, o.stay_id) = 12345678
ORDER BY date;
```

### 识别少尿患者

```sql
SELECT
    stay_id,
    DATE(charttime) as date,
    SUM(CASE WHEN itemid IN (226559, 226560) THEN value ELSE 0 END) as urine_output_ml
FROM outputevents
GROUP BY stay_id, DATE(charttime)
HAVING SUM(CASE WHEN itemid IN (226559, 226560) THEN value ELSE 0 END) < 400
ORDER BY date;
```

## ETL映射建议

1. **排出类别**: 建立本地排出项目到 `itemid` 的映射
2. **单位统一**: 确保所有排出量使用ml
3. **时间记录**: 记录护士清空测量的时间
4. **多引流管**: 区分不同部位的引流管（如胸管#1、#2）

## 注意事项

1. **尿量来源**: 包括导尿管尿量（Foley）和自主排尿（Void）
2. **累计记录**: 每条记录是自上次清空以来的累计量
3. **估计值**: 部分记录可能是估计值（如大便量）
4. **手术室数据**: `OR Out` 记录手术期间的排出量
5. **引流管编号**: 同类型引流管可能有多个（如Chest Tube #1, #2, #3）
