# discharge 表

## 概述

`discharge` 表存储患者的出院小结（Discharge Summary），是详细记录患者整个住院过程的临床文本。出院小结包含主诉、现病史、既往史、住院经过、出院诊断等重要信息。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `note_id` | VARCHAR(25) | NOT NULL, 主键 | 文档唯一标识 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `note_type` | CHAR(2) | NOT NULL | 文档类型 |
| `note_seq` | INTEGER | NOT NULL | 文档序号 |
| `charttime` | TIMESTAMP | NOT NULL | 文档记录时间 |
| `storetime` | TIMESTAMP | 可空 | 文档存储时间 |
| `text` | TEXT | NOT NULL | 出院小结全文 |

## 字段详解

### note_id
- **含义**: 文档的唯一标识
- **格式**: 由 `subject_id`、`note_type` 和 `note_seq` 组合而成
- **用途**: 连接 `discharge_detail` 表

### note_type
- **含义**: 文档类型
- **取值**:
  | 值 | 说明 |
  |---|---|
  | `DS` | Discharge Summary（出院小结） |
  | `AD` | Addendum（补充记录） |

### note_seq
- **含义**: 按时间顺序的文档序号
- **说明**: 同一类型文档按时间递增

### charttime
- **含义**: 文档内容对应的临床时间
- **用途**: 用于理解文档内容的时间背景

### storetime
- **含义**: 文档完成并存入系统的时间
- **说明**: 出院小结通常在出院后几天内完成

### text
- **含义**: 出院小结的完整文本内容
- **去标识化**: 已移除患者可识别信息（用 `___` 替代）

## 出院小结的典型结构

出院小结通常包含以下章节：

### 1. 入院信息
- **Chief Complaint**: 主诉
- **History of Present Illness**: 现病史
- **Past Medical History**: 既往史
- **Social History**: 社会史（已移除）
- **Family History**: 家族史

### 2. 检查与评估
- **Physical Exam**: 体格检查
- **Pertinent Results**: 相关检查结果
- **Studies**: 检查研究

### 3. 诊疗过程
- **Brief Hospital Course**: 简要住院经过
- **Medications on Admission**: 入院用药
- **Discharge Medications**: 出院用药

### 4. 出院信息
- **Discharge Diagnosis**: 出院诊断
- **Discharge Condition**: 出院状态
- **Discharge Instructions**: 出院指导（已移除）
- **Follow-up Instructions**: 随访指导

## 去标识化说明

以下内容已从出院小结中移除或替换：
- **社会史（Social History）**: 整节移除
- **出院指导（Discharge Instructions）**: 整节移除
- **患者姓名、日期等**: 用 `___` 替代
- **医生签名**: 去标识化

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| discharge_detail | note_id | 一对多 |

## 使用示例

### 查询患者的出院小结

```sql
SELECT
    note_id,
    hadm_id,
    note_type,
    charttime,
    LEFT(text, 500) as text_preview
FROM discharge
WHERE subject_id = 12345678
ORDER BY charttime;
```

### 搜索包含特定内容的出院小结

```sql
SELECT
    subject_id,
    hadm_id,
    charttime
FROM discharge
WHERE text ILIKE '%sepsis%'
LIMIT 100;
```

### 统计出院小结数量

```sql
SELECT
    note_type,
    COUNT(*) as count
FROM discharge
GROUP BY note_type;
```

## 应用场景

### 1. 临床研究
- 提取诊断信息
- 分析治疗方案
- 研究疾病进程

### 2. NLP应用
- 命名实体识别
- 文本分类
- 信息抽取

### 3. 教育培训
- 病例学习
- 医学写作参考

## ETL映射建议

1. **文档结构化**: 可尝试将出院小结解析为结构化字段
2. **章节提取**: 使用文本处理提取各章节内容
3. **时间对齐**: 与其他临床数据按时间对齐

## 注意事项

1. **自由文本**: 出院小结是非结构化的自由文本
2. **格式变化**: 不同医生的写作风格和章节安排可能不同
3. **去标识化痕迹**: `___` 表示已移除的敏感信息
4. **章节缺失**: 社会史和出院指导章节已被完全移除
5. **补充记录**: 可能存在后续的补充记录（Addendum）
