# vitalsign 表（急诊生命体征）

## 概述

`vitalsign` 表记录患者在急诊期间的生命体征测量值。与 `triage` 表记录的分诊时单次评估不同，此表记录急诊停留期间的多次生命体征测量。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `stay_id` | INTEGER | NOT NULL | 急诊就诊唯一标识 |
| `charttime` | TIMESTAMP(0) | 可空 | 记录时间 |
| `temperature` | NUMERIC(10,4) | 可空 | 体温（华氏度） |
| `heartrate` | NUMERIC(10,4) | 可空 | 心率（次/分） |
| `resprate` | NUMERIC(10,4) | 可空 | 呼吸频率（次/分） |
| `o2sat` | NUMERIC(10,4) | 可空 | 血氧饱和度（%） |
| `sbp` | INTEGER | 可空 | 收缩压（mmHg） |
| `dbp` | INTEGER | 可空 | 舒张压（mmHg） |
| `rhythm` | TEXT | 可空 | 心律 |
| `pain` | TEXT | 可空 | 疼痛评分（0-10） |

## 字段详解

### subject_id / stay_id
- **含义**: 患者和急诊就诊的唯一标识
- **关联**: 与 `edstays` 表关联

### charttime
- **含义**: 生命体征记录的时间
- **用途**: 追踪生命体征的时间变化

### temperature
- **含义**: 体温
- **单位**: 华氏度（°F）
- **换算**: 摄氏度 = (华氏度 - 32) × 5/9

### heartrate
- **含义**: 心率
- **单位**: 次/分钟（bpm）

### resprate
- **含义**: 呼吸频率
- **单位**: 次/分钟

### o2sat
- **含义**: 外周血氧饱和度
- **单位**: 百分比（%）

### sbp / dbp
- **含义**: 收缩压/舒张压
- **单位**: 毫米汞柱（mmHg）
- **数据类型**: INTEGER（与triage表略有不同）

### rhythm
- **含义**: 心律描述
- **格式**: 文本描述
- **常见取值**: `Sinus Rhythm`, `Atrial Fibrillation`, `Sinus Tachycardia` 等

### pain
- **含义**: 患者自报的疼痛程度
- **评分**: 0-10分

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| edstays | stay_id | 多对一 |
| patients | subject_id | 多对一 |

## 使用示例

### 查询急诊期间的生命体征

```sql
SELECT
    stay_id,
    charttime,
    temperature,
    heartrate,
    resprate,
    o2sat,
    sbp,
    dbp,
    rhythm
FROM vitalsign
WHERE stay_id = 12345678
ORDER BY charttime;
```

### 分析生命体征变化趋势

```sql
SELECT
    stay_id,
    charttime,
    heartrate,
    LAG(heartrate) OVER (PARTITION BY stay_id ORDER BY charttime) as prev_hr,
    heartrate - LAG(heartrate) OVER (PARTITION BY stay_id ORDER BY charttime) as hr_change
FROM vitalsign
WHERE stay_id = 12345678
  AND heartrate IS NOT NULL
ORDER BY charttime;
```

### 计算每次急诊的生命体征统计

```sql
SELECT
    stay_id,
    COUNT(*) as measurement_count,
    ROUND(AVG(heartrate), 0) as avg_hr,
    ROUND(MIN(heartrate), 0) as min_hr,
    ROUND(MAX(heartrate), 0) as max_hr,
    ROUND(AVG(sbp), 0) as avg_sbp,
    ROUND(MIN(o2sat), 1) as min_spo2
FROM vitalsign
GROUP BY stay_id
HAVING COUNT(*) > 1
ORDER BY measurement_count DESC
LIMIT 100;
```

### 识别生命体征恶化

```sql
WITH vital_changes AS (
    SELECT
        v.stay_id,
        v.charttime,
        v.heartrate,
        v.sbp,
        v.o2sat,
        LAG(v.heartrate) OVER (PARTITION BY v.stay_id ORDER BY v.charttime) as prev_hr,
        LAG(v.sbp) OVER (PARTITION BY v.stay_id ORDER BY v.charttime) as prev_sbp,
        LAG(v.o2sat) OVER (PARTITION BY v.stay_id ORDER BY v.charttime) as prev_spo2
    FROM vitalsign v
)
SELECT
    stay_id,
    charttime,
    heartrate,
    prev_hr,
    sbp,
    prev_sbp,
    o2sat,
    prev_spo2
FROM vital_changes
WHERE (heartrate - prev_hr > 20)
   OR (prev_sbp - sbp > 20)
   OR (prev_spo2 - o2sat > 5)
ORDER BY charttime;
```

### 统计心律类型

```sql
SELECT
    rhythm,
    COUNT(*) as count
FROM vitalsign
WHERE rhythm IS NOT NULL
GROUP BY rhythm
ORDER BY count DESC
LIMIT 20;
```

### 关联分诊与后续生命体征

```sql
SELECT
    t.stay_id,
    t.heartrate as triage_hr,
    t.sbp as triage_sbp,
    t.acuity,
    AVG(v.heartrate) as avg_ed_hr,
    AVG(v.sbp) as avg_ed_sbp,
    MAX(v.heartrate) as max_ed_hr
FROM triage t
INNER JOIN vitalsign v ON t.stay_id = v.stay_id
GROUP BY t.stay_id, t.heartrate, t.sbp, t.acuity
HAVING COUNT(*) > 1
ORDER BY t.acuity;
```

## 应用场景

### 1. 生命体征监测
- 追踪急诊期间的生命体征变化
- 识别生命体征恶化趋势

### 2. 早期预警系统
- 计算早期预警评分（如NEWS、MEWS）
- 触发临床警报

### 3. 心律分析
- 分析异常心律的发生率
- 研究心律与临床结局的关系

### 4. 急诊质量评估
- 评估生命体征监测的频率
- 分析对异常生命体征的响应时间

## ETL映射建议

1. **单位转换**: 体温从华氏度转换为摄氏度
2. **时间序列处理**: 按时间排序构建生命体征序列
3. **心律标准化**: 将心律描述映射到标准术语
4. **异常值处理**: 检测并处理生理上不可能的值

## 注意事项

1. **与triage区别**: `triage` 记录分诊时单次评估，`vitalsign` 记录急诊期间多次测量
2. **华氏度**: 体温单位为华氏度
3. **数据类型差异**: `sbp`/`dbp` 为INTEGER，与 `triage` 表略有不同
4. **缺失值**: 部分去标识化导致的自由文本无法转换，造成缺失值
5. **心律描述**: `rhythm` 为自由文本，格式可能不统一
6. **测量频率**: 测量频率取决于患者情况和临床需求
