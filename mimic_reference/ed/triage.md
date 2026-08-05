# triage 表

## 概述

`triage` 表记录急诊分诊评估信息，包括患者到达急诊时的生命体征、疼痛评分、急诊严重指数（ESI）分级和主诉。分诊是急诊护理流程的第一步，决定患者的就诊优先级。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `stay_id` | INTEGER | NOT NULL | 急诊就诊唯一标识 |
| `temperature` | NUMERIC(10,4) | 可空 | 体温（华氏度） |
| `heartrate` | NUMERIC(10,4) | 可空 | 心率（次/分） |
| `resprate` | NUMERIC(10,4) | 可空 | 呼吸频率（次/分） |
| `o2sat` | NUMERIC(10,4) | 可空 | 血氧饱和度（%） |
| `sbp` | NUMERIC(10,4) | 可空 | 收缩压（mmHg） |
| `dbp` | NUMERIC(10,4) | 可空 | 舒张压（mmHg） |
| `pain` | TEXT | 可空 | 疼痛评分（0-10） |
| `acuity` | NUMERIC(10,4) | 可空 | ESI分级（1-5） |
| `chiefcomplaint` | VARCHAR(255) | 可空 | 主诉 |

## 字段详解

### subject_id / stay_id
- **含义**: 患者和急诊就诊的唯一标识
- **关联**: 与 `edstays` 表一对一关联

### temperature
- **含义**: 体温
- **单位**: 华氏度（°F）
- **换算**: 摄氏度 = (华氏度 - 32) × 5/9
- **正常范围**: 97.8-99.1°F（36.5-37.3°C）

### heartrate
- **含义**: 心率
- **单位**: 次/分钟（bpm）
- **正常范围**: 60-100 bpm

### resprate
- **含义**: 呼吸频率
- **单位**: 次/分钟
- **正常范围**: 12-20 次/分

### o2sat
- **含义**: 外周血氧饱和度
- **单位**: 百分比（%）
- **正常范围**: ≥95%

### sbp / dbp
- **含义**: 收缩压/舒张压
- **单位**: 毫米汞柱（mmHg）
- **正常范围**: 收缩压 90-120，舒张压 60-80

### pain
- **含义**: 患者自报的疼痛程度
- **评分**: 0-10分，0为无痛，10为最剧烈的疼痛
- **类型**: TEXT（可能包含非数字描述）

### acuity
- **含义**: 急诊严重指数（Emergency Severity Index, ESI）
- **取值**:
  | 分级 | 说明 |
  |---|---|
  | 1 | 需要立即抢救 |
  | 2 | 高风险状态，意识改变或严重疼痛 |
  | 3 | 需要多项资源 |
  | 4 | 需要一项资源 |
  | 5 | 不需要资源 |
- **说明**: 数字越小，紧急程度越高

### chiefcomplaint
- **含义**: 患者的主诉
- **说明**: 已去标识化，敏感信息已移除
- **用途**: 了解患者就诊原因

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| edstays | stay_id | 一对一 |
| patients | subject_id | 多对一 |

## 使用示例

### 查询分诊评估

```sql
SELECT
    stay_id,
    temperature,
    heartrate,
    resprate,
    o2sat,
    sbp,
    dbp,
    pain,
    acuity,
    chiefcomplaint
FROM triage
WHERE stay_id = 12345678;
```

### 统计ESI分级分布

```sql
SELECT
    acuity,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
FROM triage
WHERE acuity IS NOT NULL
GROUP BY acuity
ORDER BY acuity;
```

### 分析不同ESI分级的生命体征

```sql
SELECT
    acuity,
    ROUND(AVG((temperature - 32) * 5 / 9), 1) as avg_temp_c,
    ROUND(AVG(heartrate), 0) as avg_hr,
    ROUND(AVG(resprate), 0) as avg_rr,
    ROUND(AVG(o2sat), 1) as avg_spo2,
    ROUND(AVG(sbp), 0) as avg_sbp
FROM triage
WHERE acuity IS NOT NULL
GROUP BY acuity
ORDER BY acuity;
```

### 筛选异常生命体征

```sql
SELECT
    t.stay_id,
    e.intime,
    t.heartrate,
    t.resprate,
    t.o2sat,
    t.sbp,
    t.acuity
FROM triage t
INNER JOIN edstays e ON t.stay_id = e.stay_id
WHERE t.heartrate > 120
   OR t.resprate > 24
   OR t.o2sat < 92
   OR t.sbp < 90
ORDER BY e.intime;
```

### 分析主诉关键词

```sql
SELECT
    CASE
        WHEN chiefcomplaint ILIKE '%chest pain%' THEN 'Chest Pain'
        WHEN chiefcomplaint ILIKE '%shortness of breath%' THEN 'Dyspnea'
        WHEN chiefcomplaint ILIKE '%abdominal pain%' THEN 'Abdominal Pain'
        WHEN chiefcomplaint ILIKE '%headache%' THEN 'Headache'
        WHEN chiefcomplaint ILIKE '%fall%' THEN 'Fall'
        ELSE 'Other'
    END as complaint_category,
    COUNT(*) as count
FROM triage
WHERE chiefcomplaint IS NOT NULL
GROUP BY complaint_category
ORDER BY count DESC;
```

### ESI分级与住院率关系

```sql
SELECT
    t.acuity,
    COUNT(*) as total,
    SUM(CASE WHEN e.hadm_id IS NOT NULL THEN 1 ELSE 0 END) as admitted,
    ROUND(SUM(CASE WHEN e.hadm_id IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as admission_rate
FROM triage t
INNER JOIN edstays e ON t.stay_id = e.stay_id
WHERE t.acuity IS NOT NULL
GROUP BY t.acuity
ORDER BY t.acuity;
```

## 应用场景

### 1. 分诊准确性研究
- 评估ESI分级与临床结局的关系
- 研究分诊的敏感性和特异性

### 2. 早期预警评分
- 基于分诊生命体征计算预警评分
- 识别高风险患者

### 3. 主诉分析
- 分析常见急诊主诉
- 研究特定主诉的就诊模式

### 4. 急诊资源预测
- 基于分诊数据预测资源需求
- 优化急诊人员配置

## ETL映射建议

1. **单位转换**: 体温从华氏度转换为摄氏度
2. **ESI映射**: 将ESI分级映射到本地分诊系统
3. **主诉标准化**: 考虑对主诉进行NLP处理和标准化
4. **生命体征验证**: 检测并处理异常值

## 注意事项

1. **一对一关系**: 每次急诊就诊只有一条分诊记录
2. **华氏度**: 体温单位为华氏度，需要转换
3. **缺失值**: 部分字段可能有缺失值
4. **主诉去标识化**: 主诉已去标识化，可能影响分析
5. **疼痛评分**: `pain` 为TEXT类型，可能包含非数字值
6. **ESI系统**: ESI是美国常用的分诊系统，其他国家可能使用不同系统
