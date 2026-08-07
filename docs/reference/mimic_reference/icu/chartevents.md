# chartevents 表

## 概述

`chartevents` 表是ICU模块中最大的表，存储ICU护士在床旁记录的各种观察和测量数据。包括生命体征、评估量表、护理记录等。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `stay_id` | INTEGER | NOT NULL | ICU入住标识 |
| `caregiver_id` | INTEGER | 可空 | 记录护士标识 |
| `charttime` | TIMESTAMP(0) | NOT NULL | 观察时间 |
| `storetime` | TIMESTAMP(0) | 可空 | 存储/验证时间 |
| `itemid` | INTEGER | NOT NULL | 测量项目标识 |
| `value` | VARCHAR(200) | 可空 | 测量值（文本） |
| `valuenum` | DOUBLE PRECISION | 可空 | 测量值（数值） |
| `valueuom` | VARCHAR(20) | 可空 | 计量单位 |
| `warning` | SMALLINT | 可空 | 警告标志 |

## 字段详解

### charttime vs storetime
- **charttime**: 观察/测量实际发生的时间（临床意义上的时间点）
- **storetime**: 护士在系统中录入或验证该记录的时间
- **差异**: `storetime` 通常晚于 `charttime`

### itemid
- **含义**: 测量项目的标识符
- **关联**: 需要连接 `d_items` 表获取项目名称
- **取值范围**: >220000（MetaVision系统特有）

### value / valuenum
- **value**: 文本格式的测量结果
- **valuenum**: 数值格式的测量结果（便于计算）
- **说明**: 非数值结果时 `valuenum` 为空

### warning
- **含义**: 是否有异常警告
- **取值**: 0（无警告）, 1（有警告）

### caregiver_id
- **含义**: 记录护士的匿名标识
- **用途**: 可用于分析护士工作负荷等

## 常见测量项目

### 生命体征

| itemid | 项目名称 | 中文说明 |
|--------|----------|----------|
| 220045 | Heart Rate | 心率 |
| 220050 | Arterial Blood Pressure systolic | 动脉收缩压 |
| 220051 | Arterial Blood Pressure diastolic | 动脉舒张压 |
| 220052 | Arterial Blood Pressure mean | 动脉平均压 |
| 220179 | Non Invasive Blood Pressure systolic | 无创收缩压 |
| 220180 | Non Invasive Blood Pressure diastolic | 无创舒张压 |
| 220210 | Respiratory Rate | 呼吸频率 |
| 223761 | Temperature Fahrenheit | 体温(华氏) |
| 223762 | Temperature Celsius | 体温(摄氏) |
| 220277 | O2 saturation pulseoxymetry | 脉氧饱和度 |

### 评估量表

| itemid | 项目名称 | 中文说明 |
|--------|----------|----------|
| 223900 | GCS - Verbal Response | GCS语言反应 |
| 223901 | GCS - Motor Response | GCS运动反应 |
| 220739 | GCS - Eye Opening | GCS睁眼反应 |
| 228096 | Riker-SAS Score | Riker镇静评分 |
| 223988 | RASS | Richmond躁动-镇静量表 |

### 呼吸机参数

| itemid | 项目名称 | 中文说明 |
|--------|----------|----------|
| 224685 | Tidal Volume (observed) | 潮气量(实测) |
| 224686 | Tidal Volume (set) | 潮气量(设定) |
| 224687 | Minute Volume | 分钟通气量 |
| 224688 | Peak Insp. Pressure | 吸气峰压 |
| 224689 | Plateau Pressure | 平台压 |
| 224690 | PEEP set | PEEP设定值 |
| 223835 | FiO2 | 吸入氧浓度 |

## 数据规模

- 总行数: 313,645,063 行
- 来源: MetaVision ICU信息系统

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| icustays | stay_id | 多对一 |
| d_items | itemid | 多对一 |

## 使用示例

### 查询患者心率

```sql
SELECT
    c.subject_id,
    c.charttime,
    c.valuenum as heart_rate
FROM chartevents c
INNER JOIN d_items d ON c.itemid = d.itemid
WHERE c.stay_id = 12345678
  AND d.label = 'Heart Rate'
ORDER BY c.charttime;
```

### 提取生命体征数据

```sql
SELECT
    c.stay_id,
    c.charttime,
    MAX(CASE WHEN c.itemid = 220045 THEN c.valuenum END) as heart_rate,
    MAX(CASE WHEN c.itemid = 220050 THEN c.valuenum END) as sbp,
    MAX(CASE WHEN c.itemid = 220051 THEN c.valuenum END) as dbp,
    MAX(CASE WHEN c.itemid = 220210 THEN c.valuenum END) as resp_rate,
    MAX(CASE WHEN c.itemid = 223762 THEN c.valuenum END) as temperature,
    MAX(CASE WHEN c.itemid = 220277 THEN c.valuenum END) as spo2
FROM chartevents c
WHERE c.stay_id = 12345678
GROUP BY c.stay_id, c.charttime
ORDER BY c.charttime;
```

### 计算GCS总分

```sql
SELECT
    stay_id,
    charttime,
    SUM(CASE
        WHEN itemid = 223900 THEN valuenum  -- Verbal
        WHEN itemid = 223901 THEN valuenum  -- Motor
        WHEN itemid = 220739 THEN valuenum  -- Eye
        ELSE 0
    END) as gcs_total
FROM chartevents
WHERE itemid IN (223900, 223901, 220739)
  AND stay_id = 12345678
GROUP BY stay_id, charttime
ORDER BY charttime;
```

## ETL映射建议

1. **项目映射**: 建立本地监护项目到 `itemid` 的映射
2. **时间处理**: 区分观察时间（charttime）和记录时间（storetime）
3. **单位标准化**: 确保测量单位一致
4. **数据验证**: 检查异常值（如心率>300可能是错误数据）

## 注意事项

1. **数据量巨大**: 这是MIMIC中最大的表，查询需要优化
2. **数据频率**: 生命体征通常每小时记录，但可根据病情调整
3. **数据质量**: 存在录入错误，分析前需进行数据清洗
4. **时间差异**: charttime和storetime可能相差数小时
5. **仅ICU数据**: 此表仅包含ICU期间的数据，普通病房数据不在此表
