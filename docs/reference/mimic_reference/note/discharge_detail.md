# discharge_detail 表

## 概述

`discharge_detail` 表存储与出院小结相关的补充结构化信息，采用实体-属性-值（EAV）模型。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `note_id` | VARCHAR(25) | NOT NULL | 文档唯一标识 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `field_name` | VARCHAR(255) | NOT NULL | 属性名称 |
| `field_value` | TEXT | NOT NULL | 属性值 |
| `field_ordinal` | INTEGER | NOT NULL | 属性序号 |

**主键**: (`note_id`, `field_name`, `field_ordinal`)

## 字段详解

### note_id
- **含义**: 关联到 `discharge` 表的文档标识
- **用途**: 确定此详细信息属于哪份出院小结

### field_name
- **含义**: 属性的名称
- **当前取值**: 主要是 `author`（作者）

### field_value
- **含义**: 属性对应的值
- **说明**: 文本格式

### field_ordinal
- **含义**: 同一属性的序号
- **用途**: 当同一属性有多个值时进行区分

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| discharge | note_id | 多对一 |
| patients | subject_id | 多对一 |

## 使用示例

### 查询出院小结的作者

```sql
SELECT
    d.note_id,
    d.hadm_id,
    dd.field_name,
    dd.field_value as author
FROM discharge d
INNER JOIN discharge_detail dd ON d.note_id = dd.note_id
WHERE d.hadm_id = 12345678
  AND dd.field_name = 'author';
```

### 统计属性类型

```sql
SELECT
    field_name,
    COUNT(*) as count
FROM discharge_detail
GROUP BY field_name;
```

## ETL映射建议

1. **作者信息**: 记录文档作者的标识
2. **EAV结构**: 采用灵活的属性-值结构存储元数据

## 注意事项

1. **信息有限**: 目前此表主要包含作者信息
2. **EAV模型**: 采用灵活的实体-属性-值结构
3. **与主表关联**: 通过 `note_id` 与 `discharge` 表关联
