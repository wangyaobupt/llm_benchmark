# inputevents 表

## 概述

`inputevents` 表记录患者在ICU期间接受的静脉输液和药物输注信息。包括持续输液（如血管活性药物）和间歇性给药（如抗生素）。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `stay_id` | INTEGER | NOT NULL | ICU入住标识 |
| `caregiver_id` | INTEGER | 可空 | 记录护士标识 |
| `starttime` | TIMESTAMP(0) | NOT NULL | 开始时间 |
| `endtime` | TIMESTAMP(0) | NOT NULL | 结束时间 |
| `storetime` | TIMESTAMP(0) | 可空 | 存储时间 |
| `itemid` | INTEGER | NOT NULL | 药物/液体标识 |
| `amount` | DOUBLE PRECISION | 可空 | 给药量 |
| `amountuom` | VARCHAR(30) | 可空 | 给药量单位 |
| `rate` | DOUBLE PRECISION | 可空 | 输注速率 |
| `rateuom` | VARCHAR(30) | 可空 | 速率单位 |
| `orderid` | BIGINT | 可空 | 医嘱ID |
| `linkorderid` | BIGINT | 可空 | 关联医嘱ID |
| `ordercategoryname` | VARCHAR(100) | 可空 | 医嘱类别名称 |
| `secondaryordercategoryname` | VARCHAR(100) | 可空 | 次级类别名称 |
| `ordercomponenttypedescription` | VARCHAR(200) | 可空 | 成分类型描述 |
| `ordercategorydescription` | VARCHAR(50) | 可空 | 医嘱类别描述 |
| `patientweight` | DOUBLE PRECISION | 可空 | 患者体重(kg) |
| `totalamount` | DOUBLE PRECISION | 可空 | 总量 |
| `totalamountuom` | VARCHAR(50) | 可空 | 总量单位 |
| `isopenbag` | SMALLINT | 可空 | 是否开放袋 |
| `statusdescription` | VARCHAR(30) | 可空 | 状态描述 |
| `originalamount` | DOUBLE PRECISION | 可空 | 原始药量 |
| `originalrate` | DOUBLE PRECISION | 可空 | 原始速率 |

## 字段详解

### starttime / endtime
- **含义**: 该输注记录的起止时间
- **说明**: 每次速率调整都会产生新的记录行

### amount / amountuom
- **含义**: 在该时间段内给予的药物/液体量及单位
- **常见单位**: ml, mg, mcg, units

### rate / rateuom
- **含义**: 输注速率及单位
- **常见单位**:
  - ml/hour（液体）
  - mcg/kg/min（血管活性药物常用）
  - mg/hour
  - units/hour

### orderid / linkorderid
- **含义**: 医嘱标识
- **orderid**: 当前配置/溶液的标识
- **linkorderid**: 关联同一原始医嘱的不同配置

### ordercategoryname
- **含义**: 给药的类别
- **常见取值**:
  | 值 | 说明 |
  |---|---|
  | `Continuous Med` | 持续药物输注 |
  | `Drug Push` | 静脉推注 |
  | `Med Bolus` | 药物快速输注 |
  | `IV Fluid Bolus` | 液体快速输注 |

### ordercomponenttypedescription
- **含义**: 在混合液中的成分角色
- **取值**:
  | 值 | 说明 |
  |---|---|
  | `Main Parameter` | 主要成分 |
  | `Additive` | 添加剂 |
  | `Mixed Solution` | 混合溶液 |
  | `Base` | 基础液体 |

### statusdescription
- **含义**: 输注的最终状态
- **取值**:
  | 值 | 说明 |
  |---|---|
  | `FinishedRunning` | 正常完成 |
  | `Stopped` | 停止 |
  | `Paused` | 暂停 |
  | `Changed` | 已更改 |
  | `Flushed` | 冲洗 |

### patientweight
- **含义**: 用于计算剂量的患者体重
- **单位**: kg
- **用途**: 验证按体重计算的剂量

## 常见药物/液体 itemid

### 血管活性药物

| itemid | 药物名称 | 常用单位 |
|--------|----------|----------|
| 221906 | Norepinephrine | mcg/kg/min |
| 221289 | Epinephrine | mcg/kg/min |
| 222315 | Vasopressin | units/hour |
| 221662 | Dopamine | mcg/kg/min |
| 221653 | Dobutamine | mcg/kg/min |
| 221749 | Phenylephrine | mcg/kg/min |

### 镇静/镇痛药物

| itemid | 药物名称 | 说明 |
|--------|----------|------|
| 222168 | Propofol | 丙泊酚 |
| 221744 | Fentanyl | 芬太尼 |
| 225154 | Morphine Sulfate | 硫酸吗啡 |
| 221668 | Midazolam | 咪达唑仑 |
| 225942 | Dexmedetomidine | 右美托咪定 |

### 静脉液体

| itemid | 液体名称 | 说明 |
|--------|----------|------|
| 220949 | Dextrose 5% | 5%葡萄糖 |
| 220950 | NaCl 0.9% | 生理盐水 |
| 225158 | NaCl 0.45% | 半盐水 |
| 225823 | Lactated Ringer's | 乳酸林格液 |

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| icustays | stay_id | 多对一 |
| d_items | itemid | 多对一 |

## 使用示例

### 查询患者的血管活性药物使用

```sql
SELECT
    i.stay_id,
    d.label as drug_name,
    i.starttime,
    i.endtime,
    i.rate,
    i.rateuom
FROM inputevents i
INNER JOIN d_items d ON i.itemid = d.itemid
WHERE i.stay_id = 12345678
  AND i.itemid IN (221906, 221289, 222315, 221662)  -- 常见血管活性药
ORDER BY i.starttime;
```

### 计算去甲肾上腺素总剂量

```sql
SELECT
    stay_id,
    SUM(amount) as total_amount,
    amountuom
FROM inputevents
WHERE itemid = 221906  -- Norepinephrine
  AND stay_id = 12345678
GROUP BY stay_id, amountuom;
```

### 分析液体平衡

```sql
SELECT
    stay_id,
    DATE(starttime) as date,
    SUM(amount) as total_input_ml
FROM inputevents
WHERE stay_id = 12345678
  AND amountuom = 'ml'
GROUP BY stay_id, DATE(starttime)
ORDER BY date;
```

## ETL映射建议

1. **药物映射**: 建立本地药物到 `itemid` 的映射
2. **单位标准化**: 确保剂量和速率单位一致
3. **时间段处理**: 记录每次速率调整的时间段
4. **混合液处理**: 正确处理溶液中的多种成分

## 注意事项

1. **速率调整**: 每次速率调整都产生新行，需要根据时间连续性合并分析
2. **单位变化**: 同一药物可能使用不同单位（如mcg vs mg）
3. **与emar的关系**: ICU期间的给药同时记录在 `inputevents` 和 `emar` 中
4. **体重计算**: 使用 `patientweight` 验证按体重计算的剂量
5. **混合液**: 一个输液袋可能包含多种药物，使用 `orderid` 关联
