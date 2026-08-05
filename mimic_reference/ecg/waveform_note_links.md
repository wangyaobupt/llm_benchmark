# waveform_note_links 表

## 概述

`waveform_note_links` 表建立ECG波形数据与心脏科医生临床报告之间的关联。通过此表可以将ECG波形与对应的专家解读报告匹配，用于训练和评估ECG自动分析系统。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `study_id` | INTEGER | NOT NULL | ECG检查唯一标识 |
| `note_id` | VARCHAR | NOT NULL | 临床笔记标识 |
| `note_seq` | INTEGER | NOT NULL | ECG时间序号 |
| `path` | VARCHAR | 可空 | 波形文件路径 |

## 字段详解

### subject_id
- **含义**: 患者的唯一标识符
- **关联**: 与MIMIC-IV其他模块的 `subject_id` 关联

### study_id
- **含义**: ECG检查的唯一标识
- **关联**: 与 `record_list` 和 `machine_measurements` 表关联

### note_id
- **含义**: 关联的心脏科医生报告标识
- **用途**: 链接到MIMIC-IV-Note模块中的心脏科报告
- **说明**: 可用于获取专家对ECG的解读

### note_seq
- **含义**: ECG的时间顺序编号
- **用途**: 对同一患者的多次ECG进行时间排序
- **说明**: 数字越大表示时间越晚

### path
- **含义**: ECG波形文件的存储路径
- **格式**: 与 `record_list` 表中的路径对应

## 数据规模

- 总记录数: 约 600,000 条
- 文件大小: 约 56 MB
- 说明: 并非所有ECG都有关联的临床报告

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| record_list | study_id | 一对一 |
| machine_measurements | study_id | 一对一 |
| Note模块 | note_id | 多对一 |
| patients | subject_id | 多对一 |

## 使用示例

### 查询患者ECG与报告的关联

```sql
SELECT
    subject_id,
    study_id,
    note_id,
    note_seq,
    path
FROM waveform_note_links
WHERE subject_id = 12345678
ORDER BY note_seq;
```

### 统计有报告的ECG比例

```sql
SELECT
    COUNT(DISTINCT r.study_id) as total_ecg,
    COUNT(DISTINCT w.study_id) as ecg_with_notes,
    ROUND(COUNT(DISTINCT w.study_id) * 100.0 / COUNT(DISTINCT r.study_id), 2) as percentage
FROM record_list r
LEFT JOIN waveform_note_links w ON r.study_id = w.study_id;
```

### 关联ECG测量与临床报告

```sql
SELECT
    w.subject_id,
    w.study_id,
    w.note_id,
    m.ecg_time,
    m.rr_interval,
    m.report_0 as machine_diagnosis
FROM waveform_note_links w
INNER JOIN machine_measurements m ON w.study_id = m.study_id
WHERE w.subject_id = 12345678
ORDER BY m.ecg_time;
```

### 分析每位患者的ECG时间序列

```sql
SELECT
    subject_id,
    COUNT(*) as ecg_count,
    MIN(note_seq) as first_seq,
    MAX(note_seq) as last_seq
FROM waveform_note_links
GROUP BY subject_id
HAVING COUNT(*) > 5
ORDER BY ecg_count DESC
LIMIT 100;
```

### 构建机器诊断与专家报告对照数据集

```sql
SELECT
    w.study_id,
    w.note_id,
    m.report_0 as machine_diagnosis_1,
    m.report_1 as machine_diagnosis_2,
    w.path
FROM waveform_note_links w
INNER JOIN machine_measurements m ON w.study_id = m.study_id
WHERE m.report_0 IS NOT NULL
LIMIT 1000;
```

## 应用场景

### 1. ECG自动解读系统训练
- 使用专家报告作为标注数据
- 训练深度学习模型进行ECG解读

### 2. 机器诊断验证
- 对比机器诊断与专家解读
- 评估机器诊断的准确性

### 3. 临床研究
- 研究ECG变化与临床事件的关系
- 追踪心脏病的ECG演变

### 4. 教育培训
- 构建ECG学习数据库
- 开发ECG教学系统

## ETL映射建议

1. **报告获取**: 通过 `note_id` 从Note模块获取完整报告文本
2. **时间排序**: 使用 `note_seq` 进行时间排序
3. **数据匹配**: 确保 `study_id` 在各表间一致关联

## 注意事项

1. **覆盖率**: 并非所有ECG都有关联的临床报告（约75%有报告）
2. **报告位置**: 心脏科医生报告存储在MIMIC-IV-Note模块
3. **时间序列**: `note_seq` 表示时间顺序，但不是实际时间
4. **数据发布**: 根据MIMIC文档，心脏科报告可能在后续版本中发布
5. **研究应用**: 主要用于机器学习和ECG自动分析研究
