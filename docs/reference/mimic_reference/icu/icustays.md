# icustays 表

## 概述

`icustays` 表定义患者的ICU（重症监护室）入住记录。每次ICU入住对应一行记录。此表从 `transfers` 表派生，是研究ICU患者的核心表。

## 表结构

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

## 字段详解

### stay_id
- **含义**: ICU入住的唯一标识符
- **说明**: 这是系统生成的标识符，用于关联ICU模块中的所有事件表
- **与MIMIC-III的区别**: 替代了MIMIC-III中的 `icustay_id`

### first_careunit / last_careunit
- **含义**: 患者在此次ICU入住期间的首个和最后ICU类型
- **常见取值**:
  | 值 | 说明 |
  |---|---|
  | `Medical Intensive Care Unit (MICU)` | 内科ICU |
  | `Medical/Surgical Intensive Care Unit (MICU/SICU)` | 内外科ICU |
  | `Surgical Intensive Care Unit (SICU)` | 外科ICU |
  | `Cardiac Vascular Intensive Care Unit (CVICU)` | 心血管ICU |
  | `Coronary Care Unit (CCU)` | 冠心病监护室 |
  | `Neuro Surgical Intensive Care Unit (Neuro SICU)` | 神经外科ICU |
  | `Trauma SICU (TSICU)` | 创伤外科ICU |

### intime / outtime
- **含义**: 进入和离开ICU的时间
- **来源**: 从 `transfers` 表派生

### los (Length of Stay)
- **含义**: ICU住院时长
- **单位**: 小数天数（如1.5表示1.5天）
- **计算**: `los = (outtime - intime) / 24小时`

## 派生逻辑

此表从 `transfers` 表派生：
1. 筛选 `careunit` 为ICU类型的转移记录
2. 24小时内连续的ICU入住合并为一次 `stay_id`
3. 中间如有非ICU病房，则分为多次ICU入住

```
示例:
转移记录: ICU -> 普通病房 -> ICU
结果: 2个独立的 stay_id
```

## 数据规模

- 总记录数: 73,181次ICU入住
- 独立患者数: 50,920人
- 平均ICU住院时长: 11.0天（标准差13.3天）
- ICU内死亡率: 11.6%

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| chartevents | stay_id | 一对多 |
| inputevents | stay_id | 一对多 |
| outputevents | stay_id | 一对多 |
| procedureevents | stay_id | 一对多 |

## 使用示例

### 查询患者的ICU入住记录

```sql
SELECT
    subject_id,
    hadm_id,
    stay_id,
    first_careunit,
    last_careunit,
    intime,
    outtime,
    los
FROM icustays
WHERE subject_id = 12345678
ORDER BY intime;
```

### 统计各ICU的入住次数

```sql
SELECT
    first_careunit,
    COUNT(*) as stay_count,
    AVG(los) as avg_los
FROM icustays
GROUP BY first_careunit
ORDER BY stay_count DESC;
```

### 计算ICU死亡率

```sql
SELECT
    i.first_careunit,
    COUNT(*) as total,
    SUM(CASE WHEN a.deathtime BETWEEN i.intime AND i.outtime THEN 1 ELSE 0 END) as deaths,
    ROUND(100.0 * SUM(CASE WHEN a.deathtime BETWEEN i.intime AND i.outtime THEN 1 ELSE 0 END) / COUNT(*), 2) as mortality_rate
FROM icustays i
INNER JOIN admissions a ON i.hadm_id = a.hadm_id
GROUP BY i.first_careunit
ORDER BY mortality_rate DESC;
```

## ETL映射建议

1. **ICU识别**: 建立本地病房代码到ICU类型的映射
2. **入住合并**: 考虑短暂离开ICU后返回的情况是否合并
3. **时间精度**: 记录准确的ICU入住和离开时间
4. **住院关联**: 确保每次ICU入住都关联到正确的住院记录

## 注意事项

1. **stay_id vs icustay_id**: MIMIC-IV使用 `stay_id`，MIMIC-III使用 `icustay_id`
2. **一次住院多次ICU**: 同一次住院（`hadm_id`）可能有多次ICU入住
3. **ICU内转科**: 如果患者在ICU之间转移（如MICU→SICU），`first_careunit` 和 `last_careunit` 会不同
4. **短暂离开**: 短暂（<24小时）离开ICU后返回会被合并为一次入住
