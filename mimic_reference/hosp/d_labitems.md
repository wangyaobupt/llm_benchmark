# d_labitems 表

## 概述

`d_labitems` 是实验室检验项目的维度表（字典表），为 `labevents` 表中的 `itemid` 提供人类可读的描述信息。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `itemid` | INTEGER | NOT NULL, 主键 | 检验项目唯一标识 |
| `label` | VARCHAR(50) | 可空 | 检验项目名称 |
| `fluid` | VARCHAR(50) | 可空 | 标本类型 |
| `category` | VARCHAR(50) | 可空 | 检验类别 |

## 字段详解

### itemid
- **含义**: 检验项目的唯一标识符
- **用途**: 作为 `labevents` 表的外键，连接检验结果与项目定义
- **说明**: 每个独特的 检验项目+标本类型 组合对应一个 `itemid`

### label
- **含义**: 检验项目的名称
- **示例**: `Creatinine`（肌酐）, `Potassium`（钾）, `Hemoglobin`（血红蛋白）
- **ETL映射**: 对应医院LIS系统中的检验项目名称

### fluid
- **含义**: 检验标本的类型
- **常见取值**:
  | 值 | 说明 |
  |---|---|
  | `Blood` | 血液 |
  | `Urine` | 尿液 |
  | `Cerebrospinal Fluid (CSF)` | 脑脊液 |
  | `Ascites` | 腹水 |
  | `Pleural` | 胸水 |
  | `Joint Fluid` | 关节液 |
  | `Stool` | 粪便 |
  | `Other Body Fluid` | 其他体液 |

### category
- **含义**: 检验的分类，提供更高层次的检验类型信息
- **常见取值**:
  | 值 | 说明 |
  |---|---|
  | `Blood Gas` | 血气分析 |
  | `Chemistry` | 生化检验 |
  | `Hematology` | 血液学检验 |
  | `Coagulation` | 凝血功能 |
  | `Urinalysis` | 尿液分析 |

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| labevents | itemid | 一对多 |

## 常用检验项目参考

### 生化检验 (Chemistry)

| itemid | label | 中文名 | 临床意义 |
|--------|-------|--------|----------|
| 50912 | Creatinine | 肌酐 | 肾功能指标 |
| 50971 | Potassium | 钾 | 电解质 |
| 50983 | Sodium | 钠 | 电解质 |
| 50882 | Bicarbonate | 碳酸氢根 | 酸碱平衡 |
| 50893 | Calcium, Total | 总钙 | 电解质 |
| 50931 | Glucose | 葡萄糖 | 糖代谢 |
| 50960 | Magnesium | 镁 | 电解质 |
| 50963 | NTproBNP | N端脑钠肽前体 | 心功能标志物 |

### 血液学 (Hematology)

| itemid | label | 中文名 | 临床意义 |
|--------|-------|--------|----------|
| 51221 | Hematocrit | 血细胞比容 | 贫血评估 |
| 51222 | Hemoglobin | 血红蛋白 | 贫血评估 |
| 51265 | Platelet Count | 血小板计数 | 凝血功能 |
| 51301 | White Blood Cells | 白细胞计数 | 感染/炎症 |
| 51279 | Red Blood Cells | 红细胞计数 | 贫血评估 |

### 凝血功能 (Coagulation)

| itemid | label | 中文名 | 临床意义 |
|--------|-------|--------|----------|
| 51237 | INR(PT) | 国际标准化比值 | 抗凝监测 |
| 51274 | PT | 凝血酶原时间 | 凝血功能 |
| 51275 | PTT | 部分凝血活酶时间 | 凝血功能 |

### 血气分析 (Blood Gas)

| itemid | label | 中文名 | 临床意义 |
|--------|-------|--------|----------|
| 50820 | pH | 酸碱度 | 酸碱平衡 |
| 50821 | pO2 | 氧分压 | 氧合状态 |
| 50818 | pCO2 | 二氧化碳分压 | 通气状态 |
| 50802 | Base Excess | 碱剩余 | 酸碱平衡 |

## 使用示例

### 查看所有检验项目

```sql
SELECT
    itemid,
    label,
    fluid,
    category
FROM d_labitems
ORDER BY category, label;
```

### 查找特定类别的检验

```sql
SELECT *
FROM d_labitems
WHERE category = 'Blood Gas';
```

## ETL映射建议

1. **项目对照**: 将本地LIS系统中的检验项目与 `d_labitems` 进行对照映射
2. **标本类型**: 注意区分同一检验在不同标本类型中的 `itemid` 不同
3. **LOINC编码**: 如有条件，可使用LOINC编码作为中间桥梁进行映射
4. **类别划分**: 参照MIMIC的分类体系对本地检验进行分类

## 注意事项

1. 同一检验项目在不同标本类型中会有不同的 `itemid`
2. 使用 `itemid` 而非 `label` 进行数据分析，因为 `label` 可能有微小变化
3. 大多数项目已映射到LOINC编码，便于与外部系统互操作
