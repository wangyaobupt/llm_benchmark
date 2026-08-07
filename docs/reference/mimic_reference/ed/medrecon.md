# medrecon 表

## 概述

`medrecon` 表记录急诊用药核对（Medicine Reconciliation）信息，即患者到达急诊时报告的正在服用的药物。这是了解患者基础用药情况的重要数据来源。

## 表结构

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

## 字段详解

### subject_id / stay_id
- **含义**: 患者和急诊就诊的唯一标识
- **关联**: 与 `edstays` 表关联

### charttime
- **含义**: 用药核对的记录时间
- **用途**: 确定信息采集的时间点

### name
- **含义**: 药物名称
- **格式**: 通常为药物通用名或商品名

### gsn (Generic Sequence Number)
- **含义**: 通用序列号，一种药物编码系统
- **用途**: 药物的标准化识别

### ndc (National Drug Code)
- **含义**: 美国国家药物编码
- **格式**: 通常为11位数字
- **用途**: 唯一标识药物产品

### etc_rn
- **含义**: 同一药物的分类序号
- **用途**: 一个药物可能属于多个治疗类别，用于区分

### etccode / etcdescription
- **含义**: 增强治疗分类（Enhanced Therapeutic Class）编码和描述
- **用途**: 药物的治疗分类，便于按类别分析用药

## 数据规模

- 总行数: 2,987,342 行
- 来源: 急诊科信息系统

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| edstays | stay_id | 多对一 |
| patients | subject_id | 多对一 |

## 使用示例

### 查询患者入急诊时的用药

```sql
SELECT
    stay_id,
    charttime,
    name,
    gsn,
    etcdescription
FROM medrecon
WHERE stay_id = 12345678
ORDER BY name;
```

### 统计常用药物

```sql
SELECT
    name,
    COUNT(DISTINCT stay_id) as patient_count
FROM medrecon
WHERE name IS NOT NULL
GROUP BY name
ORDER BY patient_count DESC
LIMIT 20;
```

### 按药物分类统计

```sql
SELECT
    etcdescription,
    COUNT(DISTINCT stay_id) as patient_count,
    COUNT(*) as record_count
FROM medrecon
WHERE etcdescription IS NOT NULL
GROUP BY etcdescription
ORDER BY patient_count DESC
LIMIT 20;
```

### 查找服用特定药物的患者

```sql
SELECT
    e.subject_id,
    e.stay_id,
    e.intime,
    m.name,
    m.etcdescription
FROM edstays e
INNER JOIN medrecon m ON e.stay_id = m.stay_id
WHERE m.name ILIKE '%metoprolol%'
ORDER BY e.intime;
```

### 分析心血管药物使用情况

```sql
SELECT
    m.name,
    COUNT(DISTINCT m.stay_id) as stay_count
FROM medrecon m
WHERE m.etcdescription ILIKE '%cardiovascular%'
   OR m.etcdescription ILIKE '%antihypertensive%'
GROUP BY m.name
ORDER BY stay_count DESC
LIMIT 20;
```

### 计算每次急诊的用药数量

```sql
SELECT
    stay_id,
    COUNT(DISTINCT name) as medication_count
FROM medrecon
WHERE name IS NOT NULL
GROUP BY stay_id
ORDER BY medication_count DESC
LIMIT 100;
```

## 应用场景

### 1. 基础用药分析
- 了解患者入院前的用药情况
- 评估多重用药（polypharmacy）

### 2. 药物流行病学
- 分析人群中常见药物的使用
- 研究特定药物的使用模式

### 3. 药物相互作用研究
- 识别潜在的药物相互作用
- 评估合并用药的风险

### 4. 用药依从性研究
- 与处方数据对比评估依从性
- 分析停药或漏服情况

## ETL映射建议

1. **药物编码**: 使用 `gsn` 或 `ndc` 进行标准化映射
2. **药物分类**: `etccode` 可用于按类别聚合分析
3. **数据清洗**: `name` 字段可能有格式变化，需要标准化
4. **时间关联**: 使用 `charttime` 确定记录时间点

## 注意事项

1. **自报数据**: 用药信息来自患者自报，可能不完整或不准确
2. **非处方药**: 可能包含OTC药物和保健品
3. **剂量缺失**: 此表不包含具体剂量信息
4. **多分类**: 同一药物可能有多个ETC分类（`etc_rn`区分）
5. **时间限制**: 仅记录急诊就诊时的用药情况
