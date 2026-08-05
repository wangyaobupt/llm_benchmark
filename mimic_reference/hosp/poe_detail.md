# poe_detail 表

## 概述

`poe_detail` 表存储医嘱的详细信息，采用实体-属性-值（EAV）模型，为 `poe` 表中的医嘱提供补充信息。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `poe_id` | VARCHAR(25) | NOT NULL | 医嘱唯一标识 |
| `poe_seq` | INTEGER | NOT NULL | 医嘱序号 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `field_name` | VARCHAR(255) | NOT NULL | 属性名称 |
| `field_value` | TEXT | 可空 | 属性值 |

**主键**: (`poe_id`, `poe_seq`, `field_name`)

## 字段详解

### poe_id / poe_seq
- **含义**: 关联到 `poe` 表的医嘱标识
- **用途**: 确定此详细信息属于哪个医嘱

### field_name
- **含义**: 属性的名称
- **说明**: 采用EAV模型，不同类型的医嘱可能有不同的属性

### field_value
- **含义**: 属性对应的值
- **格式**: 文本格式，需要根据 `field_name` 理解其含义

## EAV模型说明

```
传统关系模型:
| order_id | dose | route | frequency |
|----------|------|-------|-----------|
| 001      | 500mg| IV    | Q6H       |

EAV模型:
| order_id | field_name | field_value |
|----------|------------|-------------|
| 001      | dose       | 500mg       |
| 001      | route      | IV          |
| 001      | frequency  | Q6H         |
```

**EAV模型优点**: 灵活存储不同类型医嘱的不同属性

## 常见的 field_name

### 药物医嘱相关

| field_name | 说明 |
|------------|------|
| Dose | 剂量 |
| Route | 给药途径 |
| Frequency | 给药频次 |
| PRN Indication | PRN（必要时）的指征 |
| Duration | 持续时间 |

### 检验医嘱相关

| field_name | 说明 |
|------------|------|
| Specimen Type | 标本类型 |
| Priority | 优先级 |
| Reason for Exam | 检查原因 |

### 影像医嘱相关

| field_name | 说明 |
|------------|------|
| Body Part | 检查部位 |
| Contrast | 是否使用造影剂 |
| Clinical History | 临床病史 |

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| poe | poe_id, poe_seq | 多对一 |
| patients | subject_id | 多对一 |

## 使用示例

### 查询医嘱的所有详细信息

```sql
SELECT
    poe_id,
    field_name,
    field_value
FROM poe_detail
WHERE poe_id = 'subjectid_123_456'
ORDER BY field_name;
```

### 将EAV转换为宽表格式

```sql
SELECT
    poe_id,
    MAX(CASE WHEN field_name = 'Dose' THEN field_value END) as dose,
    MAX(CASE WHEN field_name = 'Route' THEN field_value END) as route,
    MAX(CASE WHEN field_name = 'Frequency' THEN field_value END) as frequency
FROM poe_detail
GROUP BY poe_id;
```

### 统计常见的属性名称

```sql
SELECT
    field_name,
    COUNT(*) as count
FROM poe_detail
GROUP BY field_name
ORDER BY count DESC
LIMIT 20;
```

## ETL映射建议

1. **属性识别**: 识别本地医嘱系统中需要记录的属性
2. **EAV转换**: 将传统表格式转换为EAV格式
3. **属性名标准化**: 使用标准化的属性名称

## 注意事项

1. **查询复杂性**: EAV模型查询比传统关系模型复杂，需要进行透视操作
2. **属性不固定**: 不同医嘱可能有不同的属性组合
3. **与其他表重复**: 部分信息可能与 `prescriptions` 等表重复
