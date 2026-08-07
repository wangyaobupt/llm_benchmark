# edstays 表

## 概述

`edstays` 表是急诊科（Emergency Department, ED）数据的核心追踪表，记录患者的急诊就诊信息，包括入科时间、出科时间、到达方式和离开去向等。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | 可空 | 住院唯一标识 |
| `stay_id` | INTEGER | NOT NULL | 急诊就诊唯一标识 |
| `intime` | TIMESTAMP(0) | NOT NULL | 急诊入科时间 |
| `outtime` | TIMESTAMP(0) | NOT NULL | 急诊出科时间 |
| `gender` | VARCHAR(1) | NOT NULL | 性别 |
| `race` | VARCHAR(60) | 可空 | 种族 |
| `arrival_transport` | VARCHAR(50) | NOT NULL | 到达方式 |
| `disposition` | VARCHAR(255) | 可空 | 离开去向 |

## 字段详解

### subject_id
- **含义**: 患者的唯一标识符
- **关联**: 可与其他模块的 `subject_id` 关联

### hadm_id
- **含义**: 住院唯一标识
- **说明**: 如果患者从急诊收入院，则有此值；如果患者未住院（如直接回家），则为 NULL
- **用途**: 关联急诊就诊与后续住院记录

### stay_id
- **含义**: 急诊就诊的唯一标识
- **说明**: 与ICU的 `stay_id` 是不同的标识符序列
- **用途**: 关联急诊模块内的其他表

### intime / outtime
- **含义**: 急诊入科和出科的时间
- **用途**: 计算急诊停留时长，分析急诊流量

### gender
- **含义**: 患者性别
- **取值**: `M`（男）, `F`（女）

### race
- **含义**: 患者自报的种族/民族
- **说明**: MIMIC-IV v2.1后扩展为33+个类别
- **注意**: 为自报数据，可能不完全准确

### arrival_transport
- **含义**: 患者到达急诊的方式
- **常见取值**:
  | 值 | 说明 |
  |---|---|
  | `WALK IN` | 步行到达 |
  | `AMBULANCE` | 救护车 |
  | `HELICOPTER` | 直升机 |
  | `OTHER` | 其他 |

### disposition
- **含义**: 患者离开急诊的去向
- **常见取值**:
  | 值 | 说明 |
  |---|---|
  | `HOME` | 回家 |
  | `ADMITTED` | 收入院 |
  | `TRANSFER` | 转院 |
  | `LEFT WITHOUT BEING SEEN` | 未就诊即离开 |
  | `LEFT AGAINST MEDICAL ADVICE` | 自动出院 |
  | `EXPIRED` | 死亡 |

## 数据规模

- 总行数: 425,087 行
- 来源: 急诊科信息系统

## 外键关系

| 关联表 | 关联字段 | 关系 | 说明 |
|--------|----------|------|------|
| patients | subject_id | 多对一 | 关联患者基本信息 |
| admissions | hadm_id | 多对一 | 关联住院记录（如有） |
| diagnosis | stay_id | 一对多 | 急诊诊断 |
| medrecon | stay_id | 一对多 | 用药核对 |
| pyxis | stay_id | 一对多 | 急诊发药 |
| triage | stay_id | 一对一 | 分诊评估 |
| vitalsign | stay_id | 一对多 | 生命体征 |

## 使用示例

### 查询患者的急诊就诊记录

```sql
SELECT
    stay_id,
    intime,
    outtime,
    outtime - intime as ed_los,
    arrival_transport,
    disposition
FROM edstays
WHERE subject_id = 12345678
ORDER BY intime;
```

### 统计急诊去向分布

```sql
SELECT
    disposition,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
FROM edstays
GROUP BY disposition
ORDER BY count DESC;
```

### 计算急诊平均停留时间

```sql
SELECT
    disposition,
    AVG(EXTRACT(EPOCH FROM (outtime - intime)) / 3600) as avg_hours
FROM edstays
GROUP BY disposition
ORDER BY avg_hours DESC;
```

### 查找急诊后收入院的患者

```sql
SELECT
    e.subject_id,
    e.stay_id,
    e.intime as ed_intime,
    e.outtime as ed_outtime,
    a.hadm_id,
    a.admittime,
    a.admission_type
FROM edstays e
INNER JOIN admissions a ON e.hadm_id = a.hadm_id
WHERE e.disposition = 'ADMITTED'
ORDER BY e.intime;
```

### 分析急诊到达方式与住院率

```sql
SELECT
    arrival_transport,
    COUNT(*) as total,
    SUM(CASE WHEN hadm_id IS NOT NULL THEN 1 ELSE 0 END) as admitted,
    ROUND(SUM(CASE WHEN hadm_id IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as admission_rate
FROM edstays
GROUP BY arrival_transport
ORDER BY admission_rate DESC;
```

## 应用场景

### 1. 急诊流量分析
- 分析急诊就诊量的时间分布
- 评估急诊拥挤程度

### 2. 患者流向研究
- 分析急诊患者的去向分布
- 研究收入院的决策因素

### 3. 急诊效率评估
- 计算急诊停留时间
- 分析不同到达方式患者的处理时间

## ETL映射建议

1. **就诊标识**: `stay_id` 用于关联急诊模块内的数据
2. **住院关联**: 通过 `hadm_id` 关联后续住院记录
3. **时间处理**: 注意 `intime` 和 `outtime` 的时区处理
4. **编码映射**: `disposition` 可能需要映射到本地系统的离开方式编码

## 注意事项

1. **stay_id 独立性**: ED的 `stay_id` 与ICU的 `stay_id` 是独立的标识符序列
2. **hadm_id 可空**: 未收入院的患者 `hadm_id` 为 NULL
3. **种族数据**: `race` 为自报数据，可能存在缺失或不准确
4. **时间偏移**: 与MIMIC-IV其他数据一样，时间已进行去标识化偏移
