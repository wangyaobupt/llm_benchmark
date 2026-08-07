# radiology_detail 表

## 概述

`radiology_detail` 表存储与放射学报告相关的结构化补充信息，包括检查名称、检查代码、CPT编码等。采用实体-属性-值（EAV）模型。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `note_id` | VARCHAR(25) | NOT NULL | 报告唯一标识 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `field_name` | VARCHAR(255) | NOT NULL | 属性名称 |
| `field_value` | TEXT | NOT NULL | 属性值 |
| `field_ordinal` | INTEGER | NOT NULL | 属性序号 |

**主键**: (`note_id`, `field_name`, `field_ordinal`)

## 字段详解

### note_id
- **含义**: 关联到 `radiology` 表的报告标识
- **用途**: 确定此详细信息属于哪份放射学报告

### field_name
- **含义**: 属性的名称
- **常见取值**:
  | 值 | 说明 |
  |---|---|
  | `exam_name` | 检查名称 |
  | `exam_code` | 检查代码 |
  | `cpt_code` | CPT编码 |
  | `parent_note_id` | 父报告ID（用于补充报告） |
  | `addendum_note_id` | 补充报告ID |

### field_value
- **含义**: 属性对应的值
- **格式**: 文本

### field_ordinal
- **含义**: 同一属性的序号
- **用途**: 当同一属性有多个值时（如多个CPT编码）进行区分

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| radiology | note_id | 多对一 |
| patients | subject_id | 多对一 |

## 使用示例

### 查询报告的检查信息

```sql
SELECT
    note_id,
    MAX(CASE WHEN field_name = 'exam_name' THEN field_value END) as exam_name,
    MAX(CASE WHEN field_name = 'exam_code' THEN field_value END) as exam_code,
    MAX(CASE WHEN field_name = 'cpt_code' THEN field_value END) as cpt_code
FROM radiology_detail
WHERE note_id = 'subject_RR_123'
GROUP BY note_id;
```

### 统计检查类型分布

```sql
SELECT
    field_value as exam_name,
    COUNT(*) as count
FROM radiology_detail
WHERE field_name = 'exam_name'
GROUP BY field_value
ORDER BY count DESC
LIMIT 20;
```

### 联合查询报告和详情

```sql
SELECT
    r.note_id,
    r.hadm_id,
    r.charttime,
    rd_name.field_value as exam_name,
    rd_cpt.field_value as cpt_code,
    LEFT(r.text, 200) as text_preview
FROM radiology r
LEFT JOIN radiology_detail rd_name
    ON r.note_id = rd_name.note_id
    AND rd_name.field_name = 'exam_name'
LEFT JOIN radiology_detail rd_cpt
    ON r.note_id = rd_cpt.note_id
    AND rd_cpt.field_name = 'cpt_code'
WHERE r.hadm_id = 12345678
ORDER BY r.charttime;
```

### 查找补充报告

```sql
SELECT
    r.note_id as original_note,
    rd.field_value as addendum_note,
    r.charttime
FROM radiology r
INNER JOIN radiology_detail rd ON r.note_id = rd.note_id
WHERE rd.field_name = 'addendum_note_id'
ORDER BY r.charttime;
```

### 按CPT编码筛选

```sql
SELECT
    r.subject_id,
    r.hadm_id,
    rd.field_value as cpt_code,
    r.charttime
FROM radiology r
INNER JOIN radiology_detail rd ON r.note_id = rd.note_id
WHERE rd.field_name = 'cpt_code'
  AND rd.field_value = '71046'  -- 胸部X线CPT编码
ORDER BY r.charttime;
```

## 常见检查的CPT编码

| CPT编码 | 检查类型 |
|---------|----------|
| 71045-71048 | 胸部X线 |
| 70450-70470 | 头颅CT |
| 74150-74178 | 腹部CT |
| 70551-70553 | 脑部MRI |
| 76700-76705 | 腹部超声 |

## ETL映射建议

1. **检查编码**: 记录检查的标准编码（如CPT）
2. **检查名称**: 标准化检查名称
3. **补充报告关联**: 建立主报告和补充报告的关联

## 注意事项

1. **EAV模型**: 采用灵活的实体-属性-值结构
2. **多值属性**: 同一报告可能有多个CPT编码
3. **补充报告**: 使用 `addendum_note_id` 和 `parent_note_id` 追踪补充报告关系
4. **与主表关联**: 必须通过 `note_id` 与 `radiology` 表关联获取完整信息
