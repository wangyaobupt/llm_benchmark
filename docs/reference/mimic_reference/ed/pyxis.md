# pyxis 表

## 概述

`pyxis` 表记录急诊科通过Pyxis自动发药系统发放的药物。Pyxis是一种常见的医院自动发药柜系统，用于安全、高效地分发药物。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `stay_id` | INTEGER | NOT NULL | 急诊就诊唯一标识 |
| `charttime` | TIMESTAMP(0) | 可空 | 发药记录时间 |
| `med_rn` | SMALLINT | NOT NULL | 单次发药的行号 |
| `name` | VARCHAR(255) | 可空 | 药物名称 |
| `gsn` | VARCHAR(10) | 可空 | GSN编码 |
| `gsn_rn` | SMALLINT | NOT NULL | GSN分组行号 |

## 字段详解

### subject_id / stay_id
- **含义**: 患者和急诊就诊的唯一标识
- **关联**: 与 `edstays` 表关联

### charttime
- **含义**: 药物发放的记录时间
- **说明**: 近似于药物给予时间
- **用途**: 追踪用药时间线

### med_rn
- **含义**: 单次发药记录的行号
- **用途**: 用于分组同一次发药的多条记录
- **说明**: 相同的 `med_rn` 值表示同一次发药操作

### name
- **含义**: 药物名称
- **格式**: 通常为药物的通用名或商品名

### gsn (Generic Sequence Number)
- **含义**: 通用序列号编码
- **用途**: 药物的标准化识别

### gsn_rn
- **含义**: GSN分组的行号
- **用途**: 同一药物可能属于多个GSN分类组
- **说明**: 用于区分多个GSN关联

## 数据规模

- 总行数: 1,586,053 行
- 来源: 急诊科信息系统（Pyxis发药系统）

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| edstays | stay_id | 多对一 |
| patients | subject_id | 多对一 |

## 使用示例

### 查询急诊发药记录

```sql
SELECT
    stay_id,
    charttime,
    med_rn,
    name,
    gsn
FROM pyxis
WHERE stay_id = 12345678
ORDER BY charttime, med_rn;
```

### 统计常用急诊药物

```sql
SELECT
    name,
    COUNT(DISTINCT stay_id) as stay_count,
    COUNT(*) as dispense_count
FROM pyxis
WHERE name IS NOT NULL
GROUP BY name
ORDER BY dispense_count DESC
LIMIT 20;
```

### 分析急诊用药时间分布

```sql
SELECT
    EXTRACT(HOUR FROM charttime) as hour,
    COUNT(*) as dispense_count
FROM pyxis
WHERE charttime IS NOT NULL
GROUP BY EXTRACT(HOUR FROM charttime)
ORDER BY hour;
```

### 计算每次急诊的发药次数

```sql
SELECT
    stay_id,
    COUNT(DISTINCT med_rn) as medication_count
FROM pyxis
GROUP BY stay_id
ORDER BY medication_count DESC
LIMIT 100;
```

### 查找特定药物的使用情况

```sql
SELECT
    e.subject_id,
    e.stay_id,
    e.intime,
    p.charttime,
    p.name
FROM edstays e
INNER JOIN pyxis p ON e.stay_id = p.stay_id
WHERE p.name ILIKE '%morphine%'
ORDER BY e.intime, p.charttime;
```

### 分析发药与急诊时间的关系

```sql
SELECT
    p.stay_id,
    e.intime,
    MIN(p.charttime) as first_med_time,
    MIN(p.charttime) - e.intime as time_to_first_med
FROM pyxis p
INNER JOIN edstays e ON p.stay_id = e.stay_id
WHERE p.charttime IS NOT NULL
GROUP BY p.stay_id, e.intime
ORDER BY time_to_first_med
LIMIT 100;
```

## 应用场景

### 1. 急诊用药分析
- 分析急诊常用药物
- 研究特定疾病的急诊用药模式

### 2. 用药时效性研究
- 分析从入急诊到首次用药的时间
- 评估急诊用药效率

### 3. 药物安全研究
- 追踪高警示药物的使用
- 分析用药错误和不良事件

### 4. 资源利用分析
- 评估急诊药物资源消耗
- 优化药物库存管理

## ETL映射建议

1. **药物编码**: 使用 `gsn` 进行标准化映射
2. **发药分组**: 使用 `med_rn` 识别单次发药事件
3. **时间处理**: `charttime` 可能需要与急诊入科时间对齐
4. **去重处理**: 注意处理 `gsn_rn` 导致的多行记录

## 注意事项

1. **发药vs给药**: 此表记录的是发药（dispensing），而非实际给药（administration）
2. **多GSN关联**: 同一药物可能有多个GSN值（用 `gsn_rn` 区分）
3. **时间近似**: `charttime` 近似于用药时间，但可能有延迟
4. **仅限急诊**: 仅包含急诊期间的发药，不包括后续住院
5. **与medrecon区别**: `pyxis` 是急诊期间的发药，`medrecon` 是入院前的用药核对
