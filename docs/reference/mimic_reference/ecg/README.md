# ECG 模块（心电图）

## 概述

ECG模块（MIMIC-IV-ECG）包含心电图波形数据及相关的机器测量值和临床报告。该模块包含约800,000份诊断性12导联心电图，来自约160,000名患者。数据采集于2008-2019年。

## 数据组成

ECG模块包含以下数据表/文件：

| 表/文件名 | 说明 |
|-----------|------|
| `record_list` | ECG记录列表 |
| `machine_measurements` | 机器自动测量值 |
| `waveform_note_links` | 波形与报告关联 |
| 波形文件 | 实际的ECG波形数据 |

## 技术规格

| 参数 | 值 |
|------|-----|
| 导联数 | 12导联 |
| 记录时长 | 10秒 |
| 采样率 | 500 Hz |
| 总记录数 | ~800,000 |
| 患者数 | ~160,000 |
| 关联报告数 | ~600,000 |

## 数据表详解

### record_list 表

ECG记录列表，将检查标识映射到波形文件路径。

| 字段名 | 数据类型 | 说明 |
|--------|----------|------|
| `subject_id` | INTEGER | 患者唯一标识 |
| `study_id` | INTEGER | ECG检查唯一标识 |
| `path` | VARCHAR | 波形文件路径 |

### machine_measurements 表

ECG机器自动生成的测量值和诊断报告。

| 字段名 | 数据类型 | 说明 |
|--------|----------|------|
| `subject_id` | INTEGER | 患者唯一标识 |
| `study_id` | INTEGER | ECG检查唯一标识 |
| `ecg_time` | TIMESTAMP | ECG记录时间 |
| `rr_interval` | NUMERIC | 平均RR间期 |
| `qrs_onset` | NUMERIC | QRS波起始时间 |
| `qrs_end` | NUMERIC | QRS波终止时间 |
| `bandwidth` | VARCHAR | 带宽设置 |
| `filtering` | VARCHAR | 滤波设置 |
| `cart_id` | VARCHAR | 设备标识（去标识化） |
| `report_0` - `report_17` | TEXT | 机器生成的诊断报告行 |

### waveform_note_links 表

将ECG波形与心脏科医生报告关联。

| 字段名 | 数据类型 | 说明 |
|--------|----------|------|
| `subject_id` | INTEGER | 患者唯一标识 |
| `study_id` | INTEGER | ECG检查唯一标识 |
| `note_id` | VARCHAR | 关联的临床笔记标识 |
| `note_seq` | INTEGER | ECG的时间顺序编号 |
| `path` | VARCHAR | 波形文件路径 |

## 与其他模块的关联

| 关联模块 | 关联字段 | 说明 |
|----------|----------|------|
| hosp.patients | subject_id | 关联患者基本信息 |
| note模块 | note_id | 关联心脏科医生报告 |

## 使用示例

### 查询患者的ECG记录

```sql
SELECT
    subject_id,
    study_id,
    path
FROM record_list
WHERE subject_id = 12345678
ORDER BY study_id;
```

### 查询机器测量值

```sql
SELECT
    subject_id,
    study_id,
    ecg_time,
    rr_interval,
    qrs_onset,
    qrs_end,
    report_0,
    report_1
FROM machine_measurements
WHERE subject_id = 12345678
ORDER BY ecg_time;
```

### 关联ECG与临床报告

```sql
SELECT
    w.subject_id,
    w.study_id,
    w.note_id,
    w.note_seq
FROM waveform_note_links w
WHERE w.subject_id = 12345678
ORDER BY w.note_seq;
```

### 分析RR间期分布

```sql
SELECT
    ROUND(rr_interval, -1) as rr_interval_bucket,
    COUNT(*) as count
FROM machine_measurements
WHERE rr_interval IS NOT NULL
  AND rr_interval BETWEEN 400 AND 1500
GROUP BY ROUND(rr_interval, -1)
ORDER BY rr_interval_bucket;
```

### 统计机器诊断

```sql
SELECT
    report_0 as machine_diagnosis,
    COUNT(*) as count
FROM machine_measurements
WHERE report_0 IS NOT NULL
GROUP BY report_0
ORDER BY count DESC
LIMIT 20;
```

## 应用场景

### 1. 心律失常检测
- 开发自动心律失常检测算法
- 研究各类心律失常的ECG特征

### 2. 机器学习研究
- 训练深度学习模型进行ECG分类
- 对比机器诊断与人工诊断

### 3. 临床研究
- 研究ECG指标与临床结局的关系
- 分析心脏病的ECG演变

### 4. 信号处理研究
- 开发ECG信号处理算法
- 研究噪声过滤和特征提取方法

## ETL映射建议

1. **波形处理**: ECG波形数据需要专门的信号处理工具
2. **测量值映射**: 机器测量值可映射到标准ECG参数
3. **报告解析**: 机器报告为多行文本，可能需要合并处理
4. **时间关联**: 使用 `ecg_time` 与其他临床数据时间对齐

## 注意事项

1. **波形数据格式**: ECG波形以特定格式存储，需要专门工具读取
2. **机器报告限制**: 机器自动诊断可能有误，需人工确认
3. **采样率**: 500 Hz采样率，每10秒记录包含5000个采样点/导联
4. **去标识化**: 设备标识和时间已去标识化
5. **报告关联**: 并非所有ECG都有关联的心脏科医生报告
6. **数据版本**: 关注MIMIC-IV-ECG的版本更新
