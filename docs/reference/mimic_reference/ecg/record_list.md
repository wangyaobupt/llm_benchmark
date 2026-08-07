# record_list 表（ECG记录列表）

## 概述

`record_list` 表是ECG模块的核心索引表，将检查标识（study_id）映射到实际的ECG波形文件路径。通过此表可以定位和访问约800,000份诊断性心电图波形数据。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `study_id` | INTEGER | NOT NULL | ECG检查唯一标识 |
| `path` | VARCHAR | NOT NULL | 波形文件路径 |

## 字段详解

### subject_id
- **含义**: 患者的唯一标识符
- **格式**: 整数
- **关联**: 可与MIMIC-IV其他模块的 `subject_id` 关联

### study_id
- **含义**: ECG检查的唯一标识
- **用途**: 关联 `machine_measurements` 和 `waveform_note_links` 表

### path
- **含义**: ECG波形文件的存储路径
- **格式**: 相对路径，按患者ID层级组织
- **示例**: `p10/p10000032/s50000123/50000123.dat`

## 数据规模

- 总记录数: 约 800,000 条
- 患者数: 约 160,000 人

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| machine_measurements | study_id | 一对一 |
| waveform_note_links | study_id | 一对一 |

## 使用示例

### 查询患者的ECG记录列表

```sql
SELECT
    subject_id,
    study_id,
    path
FROM record_list
WHERE subject_id = 12345678
ORDER BY study_id;
```

### 统计每位患者的ECG数量

```sql
SELECT
    subject_id,
    COUNT(*) as ecg_count
FROM record_list
GROUP BY subject_id
ORDER BY ecg_count DESC
LIMIT 100;
```

### 关联ECG记录与机器测量

```sql
SELECT
    r.subject_id,
    r.study_id,
    r.path,
    m.ecg_time,
    m.rr_interval
FROM record_list r
INNER JOIN machine_measurements m ON r.study_id = m.study_id
WHERE r.subject_id = 12345678
ORDER BY m.ecg_time;
```

### 查找有临床报告的ECG

```sql
SELECT
    r.subject_id,
    r.study_id,
    r.path,
    w.note_id
FROM record_list r
INNER JOIN waveform_note_links w ON r.study_id = w.study_id
WHERE r.subject_id = 12345678;
```

## 应用场景

### 1. ECG数据检索
- 定位特定患者或检查的波形文件
- 批量获取研究所需的ECG数据

### 2. 数据管理
- 构建ECG数据索引
- 验证数据完整性

### 3. 研究队列构建
- 筛选符合条件的ECG记录
- 关联临床数据构建研究数据集

## ETL映射建议

1. **路径处理**: 文件路径需要根据实际存储位置进行调整
2. **标识符映射**: `study_id` 是ECG模块内的主要关联键
3. **患者关联**: 通过 `subject_id` 关联其他临床数据

## 注意事项

1. **文件格式**: 波形文件为特定格式（如WFDB格式），需要专门工具读取
2. **路径结构**: 文件按患者ID层级组织
3. **一检查一记录**: 每个 `study_id` 对应一条记录
4. **存储位置**: 实际使用时需要确认波形文件的存储位置
