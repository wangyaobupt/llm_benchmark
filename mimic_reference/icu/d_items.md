# d_items 表

## 概述

`d_items` 是ICU模块的核心维度表（字典表），为ICU事件表中的 `itemid` 提供描述信息。所有ICU事件表（chartevents, inputevents, outputevents, procedureevents, ingredientevents）都通过 `itemid` 关联此表。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `itemid` | INTEGER | NOT NULL, 主键 | 项目唯一标识 |
| `label` | VARCHAR(200) | 可空 | 项目名称 |
| `abbreviation` | VARCHAR(100) | 可空 | 项目缩写 |
| `linksto` | VARCHAR(50) | 可空 | 链接到的表名 |
| `category` | VARCHAR(100) | 可空 | 项目类别 |
| `unitname` | VARCHAR(100) | 可空 | 计量单位 |
| `param_type` | VARCHAR(30) | 可空 | 参数类型 |
| `lownormalvalue` | FLOAT | 可空 | 正常范围下限 |
| `highnormalvalue` | FLOAT | 可空 | 正常范围上限 |

## 字段详解

### itemid
- **含义**: 项目的唯一标识符
- **取值范围**: >220000（MetaVision系统）
- **说明**: 与MIMIC-III中CareVue系统的itemid不同

### label
- **含义**: 项目的完整名称
- **示例**: "Heart Rate", "Arterial Blood Pressure systolic"

### abbreviation
- **含义**: 项目的常用缩写
- **示例**: "HR", "ABPs"

### linksto
- **含义**: 此项目数据存储在哪个表中
- **取值**:
  | 值 | 说明 |
  |---|---|
  | `chartevents` | 图表事件（生命体征等） |
  | `inputevents` | 输入事件（输液等） |
  | `outputevents` | 输出事件（尿量等） |
  | `procedureevents` | 操作事件（机械通气等） |
  | `datetimeevents` | 日期时间事件 |

### category
- **含义**: 项目的分类
- **常见取值**:
  | 值 | 说明 |
  |---|---|
  | `Routine Vital Signs` | 常规生命体征 |
  | `Hemodynamics` | 血流动力学 |
  | `Respiratory` | 呼吸相关 |
  | `Labs` | 实验室检验 |
  | `IV Medication` | 静脉用药 |
  | `Fluids - Intake` | 液体入量 |
  | `Output` | 排出量 |
  | `Procedures` | 操作/治疗 |

### param_type
- **含义**: 参数的数据类型
- **取值**: `Numeric`（数值）, `Text`（文本）, `Date`（日期）

### lownormalvalue / highnormalvalue
- **含义**: 测量值的正常参考范围
- **说明**: 并非所有项目都有参考范围

## 数据规模

- 总行数: 4,014个项目定义

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| chartevents | itemid | 一对多 |
| inputevents | itemid | 一对多 |
| outputevents | itemid | 一对多 |
| procedureevents | itemid | 一对多 |
| ingredientevents | itemid | 一对多 |

## 按类别分类的常用项目

### 生命体征 (Routine Vital Signs)

| itemid | label | 说明 |
|--------|-------|------|
| 220045 | Heart Rate | 心率 |
| 220210 | Respiratory Rate | 呼吸频率 |
| 223761 | Temperature Fahrenheit | 体温(°F) |
| 223762 | Temperature Celsius | 体温(°C) |
| 220277 | O2 saturation pulseoxymetry | SpO2 |

### 血压 (Blood Pressure)

| itemid | label | 说明 |
|--------|-------|------|
| 220050 | Arterial Blood Pressure systolic | 有创动脉收缩压 |
| 220051 | Arterial Blood Pressure diastolic | 有创动脉舒张压 |
| 220052 | Arterial Blood Pressure mean | 有创动脉平均压 |
| 220179 | Non Invasive Blood Pressure systolic | 无创收缩压 |
| 220180 | Non Invasive Blood Pressure diastolic | 无创舒张压 |
| 220181 | Non Invasive Blood Pressure mean | 无创平均压 |

### 静脉输液药物 (IV Medication)

| itemid | label | 说明 |
|--------|-------|------|
| 221906 | Norepinephrine | 去甲肾上腺素 |
| 221289 | Epinephrine | 肾上腺素 |
| 222315 | Vasopressin | 血管加压素 |
| 221662 | Dopamine | 多巴胺 |
| 221744 | Fentanyl | 芬太尼 |
| 222168 | Propofol | 丙泊酚 |
| 225154 | Morphine Sulfate | 硫酸吗啡 |

### 液体输入 (Fluids - Intake)

| itemid | label | 说明 |
|--------|-------|------|
| 220949 | Dextrose 5% | 5%葡萄糖 |
| 220950 | NaCl 0.9% | 生理盐水 |
| 220952 | Dextrose 5% in Lactated Ringer's | 5%GS乳酸林格液 |

### 排出量 (Output)

| itemid | label | 说明 |
|--------|-------|------|
| 226559 | Foley | 尿管尿量 |
| 226560 | Void | 自主排尿 |
| 226561 | Chest Tube #1 | 胸管引流液 |

## 使用示例

### 查看所有项目分类

```sql
SELECT
    category,
    COUNT(*) as item_count
FROM d_items
GROUP BY category
ORDER BY item_count DESC;
```

### 搜索特定项目

```sql
SELECT
    itemid,
    label,
    category,
    unitname
FROM d_items
WHERE label ILIKE '%blood pressure%';
```

### 查看特定表的项目

```sql
SELECT
    itemid,
    label,
    category
FROM d_items
WHERE linksto = 'chartevents'
ORDER BY category, label;
```

## ETL映射建议

1. **项目对照**: 将本地监护项目与 `d_items` 进行对照
2. **类别映射**: 参考MIMIC的分类体系
3. **单位处理**: 注意单位的一致性

## 注意事项

1. **仅MetaVision**: 此表仅包含MetaVision系统的项目（itemid>220000）
2. **linksto字段**: 使用此字段确定数据在哪个表中
3. **参考范围**: 部分项目没有参考范围信息
4. **与MIMIC-III的区别**: MIMIC-III包含CareVue系统的项目，itemid不同
