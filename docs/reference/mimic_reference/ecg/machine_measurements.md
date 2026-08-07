# machine_measurements 表

## 概述

`machine_measurements` 表存储ECG设备自动生成的测量值和诊断报告。包括RR间期、QRS波时限等定量指标，以及设备自动生成的诊断文本。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `study_id` | INTEGER | NOT NULL | ECG检查唯一标识 |
| `ecg_time` | TIMESTAMP | 可空 | ECG记录时间 |
| `rr_interval` | NUMERIC | 可空 | 平均RR间期（毫秒） |
| `qrs_onset` | NUMERIC | 可空 | QRS波起始时间 |
| `qrs_end` | NUMERIC | 可空 | QRS波终止时间 |
| `bandwidth` | VARCHAR | 可空 | 带宽设置 |
| `filtering` | VARCHAR | 可空 | 滤波设置 |
| `cart_id` | VARCHAR | 可空 | 设备标识（去标识化） |
| `report_0` | TEXT | 可空 | 机器诊断报告第1行 |
| `report_1` | TEXT | 可空 | 机器诊断报告第2行 |
| ... | ... | ... | ... |
| `report_17` | TEXT | 可空 | 机器诊断报告第18行 |

## 字段详解

### subject_id / study_id
- **含义**: 患者和ECG检查的唯一标识
- **关联**: 与 `record_list` 表关联

### ecg_time
- **含义**: ECG记录的时间
- **说明**: 已去标识化偏移
- **用途**: 时间序列分析，与其他临床数据对齐

### rr_interval
- **含义**: 平均RR间期
- **单位**: 毫秒（ms）
- **临床意义**: 反映心率，RR间期 = 60000/心率
- **正常范围**: 600-1000 ms（对应心率60-100 bpm）

### qrs_onset / qrs_end
- **含义**: QRS波群的起始和终止时间点
- **用途**: 计算QRS时限
- **临床意义**: QRS时限反映心室除极时间

### bandwidth / filtering
- **含义**: ECG记录时的带宽和滤波设置
- **用途**: 了解信号处理参数

### cart_id
- **含义**: ECG设备的标识
- **说明**: 已去标识化
- **用途**: 分析不同设备的测量差异

### report_0 - report_17
- **含义**: ECG设备自动生成的诊断报告
- **格式**: 每行一个诊断或描述
- **示例**: "Sinus rhythm", "Normal ECG", "Left ventricular hypertrophy"

## 数据规模

- 总记录数: 约 800,000 条
- 文件大小: 约 174 MB

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| record_list | study_id | 一对一 |
| waveform_note_links | study_id | 一对一 |
| patients | subject_id | 多对一 |

## 使用示例

### 查询ECG测量值

```sql
SELECT
    study_id,
    ecg_time,
    rr_interval,
    qrs_end - qrs_onset as qrs_duration,
    report_0,
    report_1
FROM machine_measurements
WHERE subject_id = 12345678
ORDER BY ecg_time;
```

### 计算心率分布

```sql
SELECT
    ROUND(60000 / rr_interval, 0) as heart_rate,
    COUNT(*) as count
FROM machine_measurements
WHERE rr_interval IS NOT NULL
  AND rr_interval BETWEEN 400 AND 1500
GROUP BY ROUND(60000 / rr_interval, 0)
ORDER BY heart_rate;
```

### 统计机器诊断分布

```sql
SELECT
    report_0 as primary_diagnosis,
    COUNT(*) as count
FROM machine_measurements
WHERE report_0 IS NOT NULL
GROUP BY report_0
ORDER BY count DESC
LIMIT 20;
```

### 筛选异常QRS时限

```sql
SELECT
    subject_id,
    study_id,
    ecg_time,
    qrs_end - qrs_onset as qrs_duration,
    report_0
FROM machine_measurements
WHERE (qrs_end - qrs_onset) > 120  -- QRS > 120ms
ORDER BY (qrs_end - qrs_onset) DESC
LIMIT 100;
```

### 分析心动过速

```sql
SELECT
    m.subject_id,
    m.study_id,
    m.ecg_time,
    60000 / m.rr_interval as heart_rate,
    m.report_0
FROM machine_measurements m
WHERE m.rr_interval < 600  -- 心率 > 100 bpm
  AND m.rr_interval IS NOT NULL
ORDER BY m.rr_interval
LIMIT 100;
```

### 合并所有诊断报告行

```sql
SELECT
    study_id,
    CONCAT_WS('; ',
        NULLIF(report_0, ''),
        NULLIF(report_1, ''),
        NULLIF(report_2, ''),
        NULLIF(report_3, ''),
        NULLIF(report_4, '')
    ) as combined_report
FROM machine_measurements
WHERE subject_id = 12345678;
```

## 应用场景

### 1. 心率变异性研究
- 分析RR间期的变化
- 研究自主神经功能

### 2. 心律失常检测
- 基于机器诊断筛选心律失常
- 验证机器诊断的准确性

### 3. QRS形态分析
- 研究宽QRS波的病因
- 分析束支阻滞的分布

### 4. 设备质量评估
- 对比不同设备的测量一致性
- 评估机器诊断的可靠性

## ETL映射建议

1. **单位转换**: RR间期与心率的转换
2. **报告合并**: 将多行报告合并为单一文本
3. **诊断编码**: 将机器诊断映射到标准诊断编码
4. **时间处理**: 注意 `ecg_time` 已去标识化

## 注意事项

1. **机器诊断局限**: 机器自动诊断可能有误，需结合临床判断
2. **报告格式**: 诊断报告分散在多个字段中
3. **缺失值**: 部分字段可能为空
4. **设备差异**: 不同设备的测量和诊断可能有差异
5. **去标识化**: 时间和设备信息已去标识化
