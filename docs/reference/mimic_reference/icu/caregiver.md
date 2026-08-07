# caregiver 表

## 概述

`caregiver` 表是ICU模块中护理人员（Caregiver）的维度表，列出所有在ICU信息系统中记录数据的护理人员标识。与HOSP模块的 `provider` 表类似，但专用于ICU模块。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `caregiver_id` | INTEGER | NOT NULL, 主键 | 护理人员唯一标识 |

## 字段详解

### caregiver_id
- **含义**: ICU护理人员的唯一标识符
- **格式**: 整数
- **说明**: 去标识化的护理人员标识

## 数据特点

- 截至MIMIC-IV v2.2，此表仅列出所有唯一的 `caregiver_id` 值
- 不包含护理人员的姓名、职位等详细信息
- 主要用于追踪ICU数据记录的来源

## 在其他表中的引用

`caregiver_id` 在ICU模块的事件表中被引用：

| 表名 | 说明 |
|------|------|
| chartevents | 记录生命体征的护理人员 |
| inputevents | 记录输液的护理人员 |
| outputevents | 记录出量的护理人员 |
| procedureevents | 记录操作的护理人员 |
| ingredientevents | 记录成分的护理人员 |
| datetimeevents | 记录日期时间的护理人员 |

## 外键关系

此表作为维度表被ICU模块的事件表引用：

| 引用表 | 引用字段 | 说明 |
|--------|----------|------|
| chartevents | caregiver_id | 记录护士 |
| inputevents | caregiver_id | 记录护士 |
| outputevents | caregiver_id | 记录护士 |
| procedureevents | caregiver_id | 记录护士 |
| ingredientevents | caregiver_id | 记录护士 |

## 使用示例

### 查询所有护理人员

```sql
SELECT caregiver_id
FROM caregiver
ORDER BY caregiver_id;
```

### 统计每位护理人员的记录数量

```sql
SELECT
    c.caregiver_id,
    COUNT(*) as record_count
FROM caregiver c
INNER JOIN chartevents ce ON c.caregiver_id = ce.caregiver_id
GROUP BY c.caregiver_id
ORDER BY record_count DESC
LIMIT 20;
```

### 分析护理人员的工作分布

```sql
SELECT
    ce.caregiver_id,
    COUNT(DISTINCT ce.stay_id) as patient_count,
    COUNT(*) as total_records
FROM chartevents ce
WHERE ce.caregiver_id IS NOT NULL
GROUP BY ce.caregiver_id
ORDER BY total_records DESC
LIMIT 20;
```

### 查看护理人员记录的项目类型

```sql
SELECT
    c.caregiver_id,
    d.category,
    COUNT(*) as count
FROM chartevents c
INNER JOIN d_items d ON c.itemid = d.itemid
WHERE c.caregiver_id = 12345
GROUP BY c.caregiver_id, d.category
ORDER BY count DESC;
```

## 应用场景

### 1. 数据溯源
- 追踪特定记录的录入者
- 数据质量审计

### 2. 工作量分析
- 统计护理人员的记录工作量
- 分析护理工作分布

### 3. 护理研究
- 研究不同护理人员的记录习惯
- 分析护理模式的差异

## ETL映射建议

1. **标识符映射**: `caregiver_id` 可能需要映射到本地护理人员系统
2. **与provider区分**: 注意区分HOSP模块的 `provider_id` 和ICU模块的 `caregiver_id`

## 注意事项

1. **无详细信息**: 此表仅包含标识符，无护理人员详细信息
2. **ICU专用**: 仅用于ICU模块，HOSP模块使用 `provider` 表
3. **去标识化**: 标识符已去标识化，无法追溯到真实个人
4. **可选字段**: 在事件表中 `caregiver_id` 可能为空
5. **不同标识体系**: `caregiver_id` 和 `provider_id` 是独立的标识体系
