# emar 表

## 概述

`emar`（Electronic Medicine Administration Record，电子药物给药记录）表记录药物的实际给药情况。与 `prescriptions` 表（记录处方）不同，此表记录的是药物实际被给予患者的时间和状态。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | 可空 | 住院唯一标识 |
| `emar_id` | VARCHAR(25) | NOT NULL, 主键 | 给药记录唯一标识 |
| `emar_seq` | INTEGER | NOT NULL | 给药序号 |
| `poe_id` | VARCHAR(25) | NOT NULL | 医嘱标识 |
| `pharmacy_id` | INTEGER | 可空 | 药房记录标识 |
| `enter_provider_id` | VARCHAR(10) | 可空 | 录入人员标识 |
| `charttime` | TIMESTAMP | NOT NULL | 给药时间 |
| `medication` | TEXT | 可空 | 药物名称 |
| `event_txt` | VARCHAR(100) | 可空 | 给药事件状态 |
| `scheduletime` | TIMESTAMP | 可空 | 计划给药时间 |
| `storetime` | TIMESTAMP | NOT NULL | 记录存储时间 |

## 字段详解

### emar_id
- **含义**: 给药记录的唯一标识
- **格式**: 由 `subject_id` 和序号组成
- **用途**: 连接 `emar_detail` 表获取详细信息

### emar_seq
- **含义**: 给药事件的序号
- **说明**: 按时间顺序递增，用于排序同一患者的给药记录

### poe_id
- **含义**: 关联到原始医嘱的标识
- **用途**: 追踪给药对应的处方医嘱

### pharmacy_id
- **含义**: 关联到 `pharmacy` 和 `prescriptions` 表
- **用途**: 连接处方和给药信息

### charttime
- **含义**: 药物给予患者的时间
- **临床意义**: 这是药物实际给予的时间点
- **与 scheduletime 的区别**: `scheduletime` 是计划时间，`charttime` 是实际时间

### medication
- **含义**: 给予的药物名称
- **格式**: 自由文本

### event_txt
- **含义**: 给药事件的状态描述
- **常见取值**:
  | 值 | 说明 |
  |---|---|
  | `Administered` | 已给药 |
  | `Applied` | 已应用（外用药） |
  | `Delayed` | 延迟给药 |
  | `Not Given` | 未给药 |
  | `Stopped` | 已停止 |

### scheduletime
- **含义**: 计划给药时间
- **说明**: 按医嘱设定的应该给药的时间

### storetime
- **含义**: 记录在系统中存储的时间
- **说明**: 可能晚于实际给药时间

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| emar_detail | emar_id, emar_seq | 一对多 |
| poe | poe_id | 多对一 |
| pharmacy | pharmacy_id | 多对一 |
| prescriptions | pharmacy_id | 多对一 |

## 使用示例

### 查询患者的给药记录

```sql
SELECT
    subject_id,
    charttime,
    medication,
    event_txt
FROM emar
WHERE hadm_id = 12345678
ORDER BY charttime;
```

### 统计给药状态分布

```sql
SELECT
    event_txt,
    COUNT(*) as count
FROM emar
GROUP BY event_txt
ORDER BY count DESC;
```

### 联合查询处方和给药

```sql
SELECT
    p.drug,
    p.dose_val_rx,
    p.dose_unit_rx,
    e.charttime,
    e.event_txt
FROM prescriptions p
INNER JOIN emar e ON p.pharmacy_id = e.pharmacy_id
WHERE p.hadm_id = 12345678
ORDER BY e.charttime;
```

## 数据可用性说明

**重要提示**: eMAR系统在2011-2013年间逐步部署到BIDMC各科室，到2016年才完全覆盖全院。因此：
- 2016年之前的住院可能没有完整的eMAR数据
- 分析给药数据时应考虑这一时间限制

## ETL映射建议

1. **条形码系统**: eMAR依赖条形码扫描，需要类似的给药确认机制
2. **时间记录**: 区分计划给药时间和实际给药时间
3. **状态映射**: 将本地给药状态映射到MIMIC的状态值
4. **关联处方**: 确保给药记录能关联到对应的处方

## 注意事项

1. **数据覆盖**: 2016年之前数据可能不完整
2. **与 inputevents 的关系**: ICU中的静脉输液信息同时存在于 `inputevents`（来自MetaVision）和 `emar`（来自eMAR系统）
3. **详细信息**: 给药的详细信息（如剂量、部位等）存储在 `emar_detail` 表中
