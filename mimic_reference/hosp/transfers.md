# transfers 表

## 概述

`transfers` 表记录患者在医院内的物理位置转移信息，追踪患者从入院到出院期间的所有科室流转。`icustays` 表就是从此表派生的。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | 可空 | 住院唯一标识 |
| `transfer_id` | INTEGER | NOT NULL, 主键 | 转移记录唯一标识 |
| `eventtype` | VARCHAR(10) | 可空 | 事件类型 |
| `careunit` | VARCHAR(255) | 可空 | 护理单元/病房类型 |
| `intime` | TIMESTAMP(0) | 可空 | 进入该单元的时间 |
| `outtime` | TIMESTAMP(0) | 可空 | 离开该单元的时间 |

## 字段详解

### subject_id
- **含义**: 患者唯一标识
- **关联**: 连接到 `patients` 表

### hadm_id
- **含义**: 住院标识
- **说明**: 可为空，某些急诊记录可能没有关联的住院记录
- **关联**: 连接到 `admissions` 表

### transfer_id
- **含义**: 物理位置转移的唯一标识符
- **用途**: 每次患者进入新的病房/单元都会生成新的 `transfer_id`

### eventtype
- **含义**: 转移事件的类型
- **取值**:
  | 值 | 说明 |
  |---|---|
  | `ed` | 急诊科（Emergency Department） |
  | `admit` | 医院入院 |
  | `transfer` | 院内转科 |
  | `discharge` | 出院 |

### careunit
- **含义**: 护理单元或病房类型
- **常见取值**:
  | 值 | 说明 |
  |---|---|
  | `Medical Intensive Care Unit (MICU)` | 内科ICU |
  | `Surgical Intensive Care Unit (SICU)` | 外科ICU |
  | `Coronary Care Unit (CCU)` | 冠心病监护室 |
  | `Cardiac Vascular Intensive Care Unit (CVICU)` | 心血管ICU |
  | `Medical/Surgical Intensive Care Unit (MICU/SICU)` | 内外科ICU |
  | `Neuro Intermediate` | 神经科中间病房 |
  | `Neuro Stepdown` | 神经科降级病房 |
  | `Neuro Surgical Intensive Care Unit (Neuro SICU)` | 神经外科ICU |
  | `Trauma SICU (TSICU)` | 创伤外科ICU |
  | `Medicine` | 内科普通病房 |
  | `Surgery` | 外科普通病房 |
  | `Emergency Department` | 急诊科 |
  | `Emergency Department Observation` | 急诊观察 |
  | `Discharge Lounge` | 出院候诊区 |

### intime / outtime
- **含义**: 进入和离开该护理单元的时间
- **说明**: `outtime` 通常等于下一条记录的 `intime`

## 与 icustays 表的关系

`icustays` 表是从 `transfers` 表派生的：
1. 筛选 `careunit` 为ICU类型的记录
2. 合并连续的ICU入住记录（24小时内的连续ICU入住合并为一次）
3. 生成 `stay_id` 标识

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |

## 使用示例

### 追踪患者院内流转路径

```sql
SELECT
    subject_id,
    hadm_id,
    eventtype,
    careunit,
    intime,
    outtime
FROM transfers
WHERE hadm_id = 12345678
ORDER BY intime;
```

### 计算各科室停留时间

```sql
SELECT
    careunit,
    AVG(EXTRACT(EPOCH FROM (outtime - intime))/3600) as avg_hours
FROM transfers
WHERE careunit IS NOT NULL
GROUP BY careunit;
```

## ETL映射建议

1. **转移记录**: 从医院ADT（入院-出院-转科）系统提取转移事件
2. **事件类型映射**:
   - 急诊登记 → `ed`
   - 办理入院 → `admit`
   - 科室转移 → `transfer`
   - 办理出院 → `discharge`
3. **病房类型标准化**: 将本地病房代码映射到标准类型
4. **时间连续性**: 确保转移记录的时间连续，前一记录的 `outtime` 应接近后一记录的 `intime`

## 注意事项

1. 并非所有物理位置都会在此表中记录，主要记录病房级别的转移
2. ICU类型的病房是 `icustays` 表的数据来源
3. `hadm_id` 为空的记录通常是急诊后未入院的患者
4. 同一患者单次住院可能有多次转科记录
