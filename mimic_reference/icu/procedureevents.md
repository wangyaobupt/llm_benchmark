# procedureevents 表

## 概述

`procedureevents` 表记录ICU中有起止时间的操作和治疗事件，如机械通气、连续肾脏替代治疗（CRRT）、各类置管等。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `stay_id` | INTEGER | NOT NULL | ICU入住标识 |
| `caregiver_id` | INTEGER | 可空 | 记录护士标识 |
| `starttime` | TIMESTAMP | NOT NULL | 操作开始时间 |
| `endtime` | TIMESTAMP | NOT NULL | 操作结束时间 |
| `storetime` | TIMESTAMP | 可空 | 记录存储时间 |
| `itemid` | INTEGER | NOT NULL | 操作项目标识 |
| `value` | DOUBLE PRECISION | 可空 | 持续时间（数值） |
| `valueuom` | VARCHAR(20) | 可空 | 时间单位 |
| `location` | VARCHAR(100) | 可空 | 操作部位 |
| `locationcategory` | VARCHAR(50) | 可空 | 部位类别 |
| `orderid` | INTEGER | 可空 | 医嘱ID |
| `linkorderid` | INTEGER | 可空 | 关联医嘱ID |
| `ordercategoryname` | VARCHAR(50) | 可空 | 医嘱类别 |
| `ordercategorydescription` | VARCHAR(30) | 可空 | 类别描述 |
| `patientweight` | DOUBLE PRECISION | 可空 | 患者体重 |
| `isopenbag` | SMALLINT | 可空 | 是否开放袋 |
| `continueinnextdept` | SMALLINT | 可空 | 是否在下一科室继续 |
| `statusdescription` | VARCHAR(20) | 可空 | 状态描述 |
| `originalamount` | DOUBLE PRECISION | 可空 | 原始量 |
| `originalrate` | DOUBLE PRECISION | 可空 | 原始速率 |

## 字段详解

### starttime / endtime
- **含义**: 操作的起止时间
- **用途**: 计算操作持续时间

### value / valueuom
- **含义**: 操作的持续时间
- **单位**: `day`（天）, `hour`（小时）, `min`（分钟）, `None`

### location / locationcategory
- **含义**: 操作的具体部位和部位类别
- **locationcategory常见取值**:
  | 值 | 说明 |
  |---|---|
  | `Invasive Venous` | 有创静脉 |
  | `Invasive Arterial` | 有创动脉 |
  | `Airway` | 气道 |
  | `Unknown` | 未知 |

### statusdescription
- **含义**: 操作的最终状态
- **取值**: `FinishedRunning`, `Paused`, `Stopped`

### continueinnextdept
- **含义**: 操作是否在转出后继续
- **取值**: 0（否）, 1（是）
- **用途**: 判断如机械通气是否在转出ICU后继续

## 常见操作项目

### 机械通气相关

| itemid | 项目名称 | 说明 |
|--------|----------|------|
| 225792 | Invasive Ventilation | 有创机械通气 |
| 225794 | Non-invasive Ventilation | 无创通气 |
| 227194 | Extubation | 拔管 |
| 225468 | Unplanned Extubation | 非计划拔管 |

### 置管相关

| itemid | 项目名称 | 说明 |
|--------|----------|------|
| 225752 | Arterial Line | 动脉置管 |
| 227719 | Dialysis Catheter | 透析导管 |
| 224263 | Multi Lumen | 多腔中心静脉导管 |
| 225761 | Peripheral IV | 外周静脉置管 |
| 224264 | PICC Line | PICC管 |

### 器官支持

| itemid | 项目名称 | 说明 |
|--------|----------|------|
| 225441 | Hemodialysis | 血液透析 |
| 225802 | CRRT Filter Change | CRRT滤器更换 |
| 225803 | IABP | 主动脉球囊反搏 |

### 其他

| itemid | 项目名称 | 说明 |
|--------|----------|------|
| 225401 | Blood Transfusion | 输血 |
| 225459 | Chest Tube Removed | 胸管拔除 |
| 225466 | Foley Catheter | 导尿管留置 |

## 数据规模

- 总行数: 696,092 行
- 来源: MetaVision ICU信息系统

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| icustays | stay_id | 多对一 |
| d_items | itemid | 多对一 |

## 使用示例

### 查询机械通气时长

```sql
SELECT
    stay_id,
    starttime,
    endtime,
    EXTRACT(EPOCH FROM (endtime - starttime))/3600 as duration_hours
FROM procedureevents
WHERE itemid = 225792  -- Invasive Ventilation
  AND stay_id = 12345678
ORDER BY starttime;
```

### 统计患者的各类置管

```sql
SELECT
    p.stay_id,
    d.label as procedure_name,
    p.location,
    p.starttime,
    p.endtime
FROM procedureevents p
INNER JOIN d_items d ON p.itemid = d.itemid
WHERE p.stay_id = 12345678
  AND d.category = 'Access Lines - Invasive'
ORDER BY p.starttime;
```

### 计算总机械通气时间

```sql
SELECT
    stay_id,
    SUM(EXTRACT(EPOCH FROM (endtime - starttime))/3600) as total_vent_hours
FROM procedureevents
WHERE itemid = 225792  -- Invasive Ventilation
GROUP BY stay_id
HAVING SUM(EXTRACT(EPOCH FROM (endtime - starttime))/3600) > 24
ORDER BY total_vent_hours DESC;
```

### 查找接受CRRT的患者

```sql
SELECT DISTINCT
    subject_id,
    hadm_id,
    stay_id
FROM procedureevents
WHERE itemid IN (225441, 225802)  -- Hemodialysis, CRRT
ORDER BY subject_id;
```

## ETL映射建议

1. **操作映射**: 建立本地操作到 `itemid` 的映射
2. **时间记录**: 记录操作的完整起止时间
3. **部位信息**: 记录置管的具体部位
4. **连续性**: 区分中断后重新开始的操作

## 注意事项

1. **与procedures_icd的区别**:
   - `procedureevents` 是ICU实时记录，有精确时间
   - `procedures_icd` 是出院后编码，粒度较粗
2. **机械通气记录**: 可能有多段记录（中断后重新开始）
3. **状态信息**: 使用 `statusdescription` 判断操作是否正常完成
4. **转科继续**: `continueinnextdept` 标识转出后是否继续
