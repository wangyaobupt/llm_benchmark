# radiology 表

## 概述

`radiology` 表存储放射学检查报告，包括X线、CT、MRI、超声等各类影像学检查的报告文本。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `note_id` | VARCHAR(25) | NOT NULL, 主键 | 报告唯一标识 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `note_type` | CHAR(2) | NOT NULL | 报告类型 |
| `note_seq` | INTEGER | NOT NULL | 报告序号 |
| `charttime` | TIMESTAMP | NOT NULL | 检查时间 |
| `storetime` | TIMESTAMP | 可空 | 报告完成时间 |
| `text` | TEXT | NOT NULL | 报告全文 |

## 字段详解

### note_id
- **含义**: 报告的唯一标识
- **格式**: 由 `subject_id`、`note_type` 和 `note_seq` 组合而成
- **用途**: 连接 `radiology_detail` 表

### note_type
- **含义**: 报告类型
- **取值**:
  | 值 | 说明 |
  |---|---|
  | `RR` | Radiology Report（放射学报告） |
  | `AR` | Addendum Report（补充报告） |

### note_seq
- **含义**: 按时间顺序的报告序号

### charttime
- **含义**: 影像检查执行的时间
- **临床意义**: 反映检查的实际时间点

### storetime
- **含义**: 报告完成并签发的时间
- **说明**: 通常晚于 `charttime`

### text
- **含义**: 放射学报告的完整文本

## 放射学报告的典型结构

放射学报告通常遵循结构化报告格式：

### 1. Indication（检查指征）
- 检查原因
- 临床问题

### 2. Comparison（对比检查）
- 与之前检查的对比

### 3. Technique（检查技术）
- 检查方法
- 造影剂使用情况

### 4. Findings（发现）
- 详细的影像学发现
- 按解剖部位描述

### 5. Impression（印象）
- 总结性结论
- 诊断建议

## 常见影像检查类型

| 检查类型 | 说明 |
|----------|------|
| CHEST X-RAY | 胸部X线 |
| CT CHEST | 胸部CT |
| CT HEAD | 头颅CT |
| CT ABDOMEN | 腹部CT |
| MRI BRAIN | 脑部MRI |
| ULTRASOUND | 超声检查 |
| ECHO | 超声心动图 |

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| radiology_detail | note_id | 一对多 |

## 使用示例

### 查询患者的放射学报告

```sql
SELECT
    note_id,
    hadm_id,
    charttime,
    LEFT(text, 300) as text_preview
FROM radiology
WHERE subject_id = 12345678
ORDER BY charttime;
```

### 搜索特定发现的报告

```sql
SELECT
    subject_id,
    hadm_id,
    charttime,
    text
FROM radiology
WHERE text ILIKE '%pneumonia%'
LIMIT 100;
```

### 统计检查类型

```sql
SELECT
    rd.field_value as exam_name,
    COUNT(*) as count
FROM radiology r
INNER JOIN radiology_detail rd ON r.note_id = rd.note_id
WHERE rd.field_name = 'exam_name'
GROUP BY rd.field_value
ORDER BY count DESC
LIMIT 20;
```

### 查找胸部X线报告

```sql
SELECT
    r.subject_id,
    r.hadm_id,
    r.charttime,
    r.text
FROM radiology r
INNER JOIN radiology_detail rd ON r.note_id = rd.note_id
WHERE rd.field_name = 'exam_name'
  AND rd.field_value ILIKE '%chest%'
ORDER BY r.charttime
LIMIT 100;
```

## 应用场景

### 1. 影像学研究
- 分析影像发现与临床结果的关系
- 研究特定疾病的影像学表现

### 2. NLP应用
- 放射学报告的自然语言处理
- 自动提取关键发现
- 异常检测

### 3. 临床决策支持
- 与其他临床数据整合分析
- 追踪疾病进展

## ETL映射建议

1. **报告分类**: 根据检查类型对报告进行分类
2. **结构化提取**: 尝试提取报告的各个章节
3. **时间关联**: 将报告与检查医嘱关联

## 注意事项

1. **自由文本**: 报告是非结构化文本
2. **结构化程度**: 放射学报告通常比出院小结更结构化
3. **补充报告**: 可能存在后续的补充报告（Addendum）
4. **检查详情**: 检查类型、CPT编码等在 `radiology_detail` 表中
5. **去标识化**: 已移除患者可识别信息
