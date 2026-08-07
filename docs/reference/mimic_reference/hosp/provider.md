# provider 表

## 概述

`provider` 表是医疗提供者（Provider）的维度表，列出数据库中所有可能的医疗提供者标识。医疗提供者包括医生、护士、药剂师等参与患者诊疗的医护人员。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `provider_id` | VARCHAR(10) | NOT NULL, 主键 | 医疗提供者唯一标识 |

## 字段详解

### provider_id
- **含义**: 医疗提供者的唯一标识符
- **格式**: 以字母"P"开头，后跟数字和字母的组合
- **示例**: `P003AB`, `P00102`
- **说明**: 随机生成的去标识化标识符

## 数据特点

- 截至MIMIC-IV v2.2，此表仅列出所有唯一的 `provider_id` 值
- 不包含提供者的姓名、科室、职称等详细信息
- 用于去标识化的同时保持数据关联性

## 在其他表中的引用

`provider_id` 在多个表中以后缀形式出现：

| 表名 | 字段名 | 说明 |
|------|--------|------|
| admissions | `admit_provider_id` | 入院医生 |
| emar | `enter_provider_id` | 录入人员 |
| emar | `verify_provider_id` | 验证人员 |
| poe | `order_provider_id` | 开单医生 |
| labevents | `order_provider_id` | 开单医生 |
| pharmacy | `enter_provider_id` | 录入药剂师 |
| pharmacy | `verify_provider_id` | 验证药剂师 |

## 外键关系

此表作为维度表被多个表引用：

| 引用表 | 引用字段 | 说明 |
|--------|----------|------|
| admissions | admit_provider_id | 入院提供者 |
| emar | enter_provider_id, verify_provider_id | 用药记录提供者 |
| poe | order_provider_id | 医嘱提供者 |
| labevents | order_provider_id | 检验开单提供者 |
| pharmacy | enter_provider_id, verify_provider_id | 药房提供者 |

## 使用示例

### 查询所有医疗提供者

```sql
SELECT provider_id
FROM provider
ORDER BY provider_id;
```

### 统计每位提供者的入院数量

```sql
SELECT
    p.provider_id,
    COUNT(a.hadm_id) as admission_count
FROM provider p
LEFT JOIN admissions a ON p.provider_id = a.admit_provider_id
GROUP BY p.provider_id
ORDER BY admission_count DESC
LIMIT 20;
```

### 分析提供者的处方数量

```sql
SELECT
    p.provider_id,
    COUNT(DISTINCT e.emar_id) as emar_count
FROM provider p
INNER JOIN emar e ON p.provider_id = e.enter_provider_id
GROUP BY p.provider_id
ORDER BY emar_count DESC
LIMIT 20;
```

### 查找某提供者的所有医嘱

```sql
SELECT
    poe.poe_id,
    poe.order_type,
    poe.order_subtype,
    poe.ordertime
FROM poe
WHERE poe.order_provider_id = 'P003AB'
ORDER BY poe.ordertime
LIMIT 100;
```

## 应用场景

### 1. 提供者分析
- 分析不同提供者的诊疗模式
- 研究处方习惯的差异

### 2. 质量评估
- 评估不同提供者的诊疗质量
- 分析用药安全性

### 3. 工作量分析
- 统计提供者的工作量分布
- 资源配置优化

## ETL映射建议

1. **标识符映射**: `provider_id` 需要映射到本地医护人员系统
2. **角色区分**: 根据引用表的字段后缀区分提供者角色
3. **去标识化考虑**: 原始数据中的提供者身份已被替换

## 注意事项

1. **无详细信息**: 此表仅包含标识符，无提供者姓名等详细信息
2. **去标识化**: 标识符为随机生成，无法追溯到真实个人
3. **角色不明**: 无法直接确定提供者的职位或科室
4. **与caregiver区分**: `provider` 用于HOSP模块，`caregiver` 用于ICU模块
5. **后缀命名**: 不同表中的字段后缀表示不同角色（如 `admit_`, `order_`, `enter_`）
