# omr 表

## 概述

`omr`（Online Medical Record，在线医疗记录）表存储患者的基本生理测量数据，包括来自门诊和住院的血压、身高、体重、BMI和肾小球滤过率估算值(eGFR)。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `chartdate` | DATE | NOT NULL | 记录日期 |
| `seq_num` | INTEGER | NOT NULL | 序号 |
| `result_name` | VARCHAR(100) | NOT NULL | 测量项目名称 |
| `result_value` | TEXT | NOT NULL | 测量值 |

**主键**: (`subject_id`, `chartdate`, `seq_num`)

## 字段详解

### chartdate
- **含义**: 测量记录的日期
- **说明**: 仅有日期，没有具体时间

### seq_num
- **含义**: 同一患者同一日期内的记录序号
- **用途**: 区分同一天的多次测量

### result_name
- **含义**: 测量项目的名称
- **取值**:
  | 值 | 说明 |
  |---|---|
  | `Blood Pressure` | 血压 |
  | `Height` | 身高 |
  | `Weight` | 体重 |
  | `BMI (kg/m2)` | 体质指数 |
  | `eGFR` | 估算肾小球滤过率 |

### result_value
- **含义**: 测量的具体数值
- **格式**:
  - 血压: "120/80" (收缩压/舒张压)
  - 身高: "170" (通常是厘米或英寸)
  - 体重: "70" (通常是公斤或磅)
  - BMI: "24.5"
  - eGFR: ">60" 或具体数值

## 数据来源

此表数据来自BIDMC及其附属机构的门诊和住院系统，包括：
- 门诊就诊记录
- 住院期间记录
- 护理记录

**重要特点**: 可以获取患者住院前的"基线"数据，这在研究中非常有价值。

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |

## 使用示例

### 查询患者的体重历史

```sql
SELECT
    subject_id,
    chartdate,
    result_value as weight
FROM omr
WHERE subject_id = 12345678
  AND result_name = 'Weight'
ORDER BY chartdate;
```

### 获取患者住院前的基线BMI

```sql
SELECT
    o.subject_id,
    a.hadm_id,
    a.admittime,
    o.chartdate,
    o.result_value as bmi
FROM omr o
INNER JOIN admissions a ON o.subject_id = a.subject_id
WHERE o.result_name = 'BMI (kg/m2)'
  AND o.chartdate < DATE(a.admittime)
ORDER BY o.subject_id, a.admittime, o.chartdate DESC;
```

### 统计血压记录

```sql
SELECT
    subject_id,
    chartdate,
    result_value as blood_pressure,
    SPLIT_PART(result_value, '/', 1) as systolic,
    SPLIT_PART(result_value, '/', 2) as diastolic
FROM omr
WHERE result_name = 'Blood Pressure'
ORDER BY subject_id, chartdate;
```

### 获取每个患者的最近测量值

```sql
SELECT DISTINCT ON (subject_id, result_name)
    subject_id,
    result_name,
    chartdate,
    result_value
FROM omr
ORDER BY subject_id, result_name, chartdate DESC;
```

## ETL映射建议

1. **数据来源**: 从门诊系统和住院护理记录中提取基本生理测量
2. **项目标准化**: 将本地测量项目名称映射到标准名称
3. **单位处理**: 注意身高、体重的单位（厘米/英寸，公斤/磅）
4. **血压格式**: 血压应保存为"收缩压/舒张压"格式

## 注意事项

1. **非结构化值**: `result_value` 是文本格式，可能需要解析
2. **单位变化**: 同一测量项目可能使用不同单位
3. **门诊数据**: 包含门诊数据，不仅限于住院
4. **基线价值**: 可用于获取患者住院前的基线状态
5. **MIMIC-IV新增**: 此表是MIMIC-IV新增的表，MIMIC-III中没有
