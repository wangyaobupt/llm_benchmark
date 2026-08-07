# drgcodes 表

## 概述

`drgcodes` 表存储住院的诊断相关分组（DRG）编码。DRG是用于医院费用报销的分类系统，将具有相似临床特征和资源消耗的住院病例归为同一组。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `drg_type` | VARCHAR(4) | NOT NULL | DRG编码体系类型 |
| `drg_code` | VARCHAR(10) | NOT NULL | DRG编码 |
| `description` | VARCHAR(195) | 可空 | DRG描述 |
| `drg_severity` | SMALLINT | 可空 | 疾病严重度 |
| `drg_mortality` | SMALLINT | 可空 | 死亡风险等级 |

## 字段详解

### drg_type
- **含义**: DRG编码使用的分类体系
- **取值**:
  | 值 | 说明 |
  |---|---|
  | `APR` | All Patient Refined DRG（全患者精细化DRG） |
  | `HCFA` | Health Care Financing Administration（医疗保健筹资管理局）DRG |

### drg_code
- **含义**: DRG分组的代码
- **格式**: 数字编码
- **说明**: 每个DRG代表一类临床相似且资源消耗相近的病例

### description
- **含义**: DRG的文字描述
- **示例**: "CARDIAC VALVE & OTH MAJ CARDIOTHORACIC PROC W/O CARD CATH"

### drg_severity
- **含义**: 疾病严重程度分级
- **取值**: 1-4（仅APR-DRG）
  | 值 | 说明 |
  |---|------|
  | 1 | Minor（轻度） |
  | 2 | Moderate（中度） |
  | 3 | Major（重度） |
  | 4 | Extreme（极重度） |

### drg_mortality
- **含义**: 死亡风险等级
- **取值**: 1-4（仅APR-DRG）
  | 值 | 说明 |
  |---|------|
  | 1 | Minor（低风险） |
  | 2 | Moderate（中等风险） |
  | 3 | Major（高风险） |
  | 4 | Extreme（极高风险） |

## DRG体系说明

### APR-DRG (All Patient Refined DRG)
- 更精细的分组，包含严重度和死亡风险子分类
- 每个基础DRG可细分为4个严重度等级和4个死亡风险等级
- 用于更精确的病例分析和费用预测

### HCFA/MS-DRG
- 美国Medicare使用的标准DRG
- 主要用于Medicare患者的费用报销
- 不包含严重度和死亡风险细分

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |

## 使用示例

### 查询患者的DRG编码

```sql
SELECT
    subject_id,
    hadm_id,
    drg_type,
    drg_code,
    description,
    drg_severity,
    drg_mortality
FROM drgcodes
WHERE hadm_id = 12345678;
```

### 统计最常见的DRG

```sql
SELECT
    drg_code,
    description,
    COUNT(*) as count
FROM drgcodes
WHERE drg_type = 'APR'
GROUP BY drg_code, description
ORDER BY count DESC
LIMIT 20;
```

### 分析APR-DRG严重度分布

```sql
SELECT
    drg_severity,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
FROM drgcodes
WHERE drg_type = 'APR'
GROUP BY drg_severity
ORDER BY drg_severity;
```

## ETL映射建议

1. **DRG分组器**: 使用官方DRG分组软件或逻辑对病例进行分组
2. **编码体系选择**: 确定使用APR-DRG还是MS-DRG
3. **严重度评估**: APR-DRG需要额外的严重度评估逻辑

## 注意事项

1. **一对多关系**: 同一次住院可能有多个DRG编码（不同体系）
2. **计费导向**: DRG主要用于计费，可能存在一定的"向上编码"倾向
3. **年度更新**: DRG分组逻辑每年可能更新，分析时需考虑版本差异
4. **并非所有住院都有**: 部分住院可能没有DRG编码
