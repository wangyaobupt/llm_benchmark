# procedures_icd 表

## 概述

`procedures_icd` 表存储患者住院期间执行的医疗操作/手术的ICD编码。这些操作编码由专业编码人员在出院后分配，用于医疗费用结算。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `seq_num` | INTEGER | NOT NULL | 操作序号 |
| `chartdate` | DATE | NOT NULL | 操作日期 |
| `icd_code` | VARCHAR(7) | NOT NULL | ICD操作编码 |
| `icd_version` | INTEGER | NOT NULL | ICD版本（9或10） |

**主键**: (`subject_id`, `hadm_id`, `seq_num`)

## 字段详解

### subject_id / hadm_id
- **含义**: 患者和住院标识
- **关联**: 连接到 `patients` 和 `admissions` 表

### seq_num
- **含义**: 操作的序号
- **说明**:
  - 按分配顺序排列，不一定是执行顺序
  - 与 `chartdate` 不一定对应

### chartdate
- **含义**: 操作执行的日期
- **注意**: 仅有日期，没有具体时间
- **用途**: 可用于确定操作的先后顺序

### icd_code
- **含义**: ICD操作编码
- **格式**:
  - ICD-9-PCS: 2-4位数字
  - ICD-10-PCS: 7位字母数字
- **示例**:
  | 编码 | 版本 | 含义 |
  |------|------|------|
  | 3961 | 9 | 体外膜氧合（ECMO） |
  | 9671 | 9 | 持续机械通气 <96小时 |
  | 5A1955Z | 10 | 呼吸机通气 <24小时 |
  | 02100Z9 | 10 | 冠状动脉旁路移植 |

### icd_version
- **含义**: ICD编码版本
- **取值**: `9`（ICD-9-PCS）或 `10`（ICD-10-PCS）

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| d_icd_procedures | icd_code, icd_version | 多对一 |

## 使用示例

### 查询患者的所有操作

```sql
SELECT
    p.subject_id,
    p.hadm_id,
    p.seq_num,
    p.chartdate,
    p.icd_code,
    def.long_title
FROM procedures_icd p
LEFT JOIN d_icd_procedures def
    ON p.icd_code = def.icd_code
    AND p.icd_version = def.icd_version
WHERE p.hadm_id = 12345678
ORDER BY p.chartdate, p.seq_num;
```

### 统计最常见的操作

```sql
SELECT
    p.icd_code,
    p.icd_version,
    def.long_title,
    COUNT(*) as frequency
FROM procedures_icd p
LEFT JOIN d_icd_procedures def
    ON p.icd_code = def.icd_code
    AND p.icd_version = def.icd_version
GROUP BY p.icd_code, p.icd_version, def.long_title
ORDER BY frequency DESC
LIMIT 20;
```

## 与其他操作数据源的区别

| 数据源 | 说明 | 适用场景 |
|--------|------|----------|
| procedures_icd | 出院后编码，用于计费 | 行政/计费分析 |
| procedureevents (ICU) | ICU实时记录 | 临床研究 |
| hcpcsevents | HCPCS/CPT计费编码 | 详细计费分析 |

## ETL映射建议

1. **编码映射**: 将本地手术/操作编码映射到ICD-PCS
2. **日期记录**: 记录每个操作的执行日期
3. **排序**: 可按日期或重要性分配 `seq_num`
4. **编码格式**: 移除小数点，保留前导零

## 注意事项

1. **仅限住院操作**: 此表仅包含医院计费的操作，不包括医生个人计费的操作
2. **编码粒度**: ICD操作编码可能不够详细，对于详细研究建议结合其他数据源
3. **ICD版本过渡**: ICD-10-PCS的编码粒度远高于ICD-9-PCS
