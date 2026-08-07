# ingredientevents 表

## 概述

`ingredientevents` 表记录输液中各成分的详细信息，特别是营养液中的成分（如蛋白质、脂肪、葡萄糖含量）和水分含量。是 `inputevents` 表的补充。

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
| `itemid` | INTEGER | NOT NULL | 成分标识 |
| `amount` | DOUBLE PRECISION | 可空 | 给予量 |
| `amountuom` | VARCHAR(20) | 可空 | 给予量单位 |
| `rate` | DOUBLE PRECISION | 可空 | 输注速率 |
| `rateuom` | VARCHAR(20) | 可空 | 速率单位 |
| `orderid` | INTEGER | 可空 | 医嘱ID |
| `linkorderid` | INTEGER | 可空 | 关联医嘱ID |
| `statusdescription` | VARCHAR(20) | 可空 | 状态描述 |
| `originalamount` | DOUBLE PRECISION | 可空 | 原始量 |
| `originalrate` | DOUBLE PRECISION | 可空 | 原始速率 |

## 字段详解

### itemid
- **含义**: 成分的标识符
- **关联**: 连接 `d_items` 表获取成分名称
- **与inputevents区别**: 此表记录的是成分级别的信息，而非药物/液体整体

### amount / rate
- **含义**: 成分的给予量和速率
- **说明**: 根据原始输液速率计算得出

### orderid / linkorderid
- **含义**: 关联到原始输液医嘱
- **用途**: 可与 `inputevents` 表中的医嘱关联

### statusdescription
- **含义**: 输注状态
- **取值**: `Changed`, `Paused`, `FinishedRunning`, `Stopped`, `Rewritten`, `Flushed`

## 常见成分项目

### 营养成分

| itemid | 成分名称 | 说明 |
|--------|----------|------|
| 220950 | NaCl 0.9% - Water Content | 生理盐水-水含量 |
| 220949 | Dextrose 5% - Water Content | 5%葡萄糖-水含量 |
| 227079 | TPN - Water Content | TPN-水含量 |
| 227082 | TPN - Protein | TPN-蛋白质 |
| 227083 | TPN - Lipids | TPN-脂肪 |
| 227080 | TPN - Carbohydrate | TPN-碳水化合物 |

### 电解质

| itemid | 成分名称 | 说明 |
|--------|----------|------|
| 227525 | Potassium Chloride (CRRT) | 氯化钾(CRRT) |
| 227536 | Sodium Chloride (CRRT) | 氯化钠(CRRT) |

## 数据规模

- 总行数: 12,229,408 行
- 来源: MetaVision ICU信息系统

## 使用场景

### 1. 营养评估
计算患者接受的蛋白质、脂肪、碳水化合物总量

### 2. 液体平衡精确计算
使用水含量（Water Content）更精确地计算液体入量

### 3. CRRT成分追踪
追踪CRRT过程中添加的电解质

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| icustays | stay_id | 多对一 |
| d_items | itemid | 多对一 |
| inputevents | orderid | 多对一 |

## 使用示例

### 计算每日蛋白质摄入

```sql
SELECT
    stay_id,
    DATE(starttime) as date,
    SUM(amount) as protein_grams
FROM ingredientevents
WHERE itemid = 227082  -- TPN - Protein
  AND stay_id = 12345678
GROUP BY stay_id, DATE(starttime)
ORDER BY date;
```

### 精确计算水分入量

```sql
SELECT
    stay_id,
    DATE(starttime) as date,
    SUM(amount) as water_ml
FROM ingredientevents
WHERE itemid IN (
    SELECT itemid FROM d_items
    WHERE label LIKE '%Water Content%'
)
  AND stay_id = 12345678
GROUP BY stay_id, DATE(starttime)
ORDER BY date;
```

### 关联输液与成分

```sql
SELECT
    i.stay_id,
    i.starttime,
    id.label as fluid,
    ie.itemid as ingredient_id,
    ied.label as ingredient,
    ie.amount,
    ie.amountuom
FROM inputevents i
INNER JOIN d_items id ON i.itemid = id.itemid
INNER JOIN ingredientevents ie ON i.orderid = ie.orderid
    AND i.starttime = ie.starttime
INNER JOIN d_items ied ON ie.itemid = ied.itemid
WHERE i.stay_id = 12345678
ORDER BY i.starttime, ie.itemid;
```

## ETL映射建议

1. **成分提取**: 从营养液配方中提取各成分含量
2. **水含量计算**: 计算各液体的实际水含量
3. **关联关系**: 建立成分与输液的关联

## 注意事项

1. **与inputevents的关系**: 使用 `orderid` 将成分关联到具体输液
2. **MIMIC-IV新增**: 此表是MIMIC-IV新增的，MIMIC-III没有
3. **主要用于营养分析**: 最常见的用途是分析肠外营养成分
4. **水含量**: 可用于更精确地计算液体摄入量
