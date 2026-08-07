# hcpcsevents 表

## 概述

`hcpcsevents` 表存储使用HCPCS（Healthcare Common Procedure Coding System）编码的计费事件，主要包含CPT（Current Procedural Terminology）编码的操作和服务。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `chartdate` | DATE | 可空 | 编码对应的日期 |
| `hcpcs_cd` | CHAR(5) | NOT NULL | HCPCS/CPT编码 |
| `seq_num` | INTEGER | NOT NULL | 序号 |
| `short_description` | VARCHAR(180) | 可空 | 编码简短描述 |

**主键**: (`hadm_id`, `seq_num`)

## 字段详解

### hcpcs_cd
- **含义**: HCPCS或CPT编码（5位字符）
- **编码结构**:
  - Level I (CPT): 主要是医疗服务和操作编码
  - Level II: 药品、设备、供应品等编码
- **格式示例**: "99223", "36556", "94003"

### seq_num
- **含义**: 同一次住院内HCPCS事件的序号
- **用途**: 区分同一次住院的多个编码

### short_description
- **含义**: 编码的简短文字描述
- **来源**: 从 `d_hcpcs` 维度表获取

### chartdate
- **含义**: 服务/操作执行的日期
- **注意**: 可能为空

## HCPCS编码体系说明

### CPT编码分类 (Level I)

| 编码范围 | 类别 |
|----------|------|
| 00100-01999 | 麻醉 |
| 10021-69990 | 外科手术 |
| 70010-79999 | 放射学 |
| 80047-89398 | 病理和检验 |
| 90281-99607 | 医疗服务 (E/M) |
| 99201-99499 | 评估和管理 |

### 常见ICU相关编码

| 编码 | 说明 |
|------|------|
| 99291-99292 | 危重症护理 |
| 94002-94003 | 呼吸机管理 |
| 36555-36556 | 中心静脉置管 |
| 31500 | 气管插管 |

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| d_hcpcs | hcpcs_cd → code | 多对一 |

## 与 procedures_icd 的区别

| 特性 | hcpcsevents | procedures_icd |
|------|-------------|----------------|
| 编码体系 | HCPCS/CPT | ICD-9-PCS / ICD-10-PCS |
| 粒度 | 更详细 | 相对粗略 |
| 来源 | 服务计费 | 医院计费 |
| 时间性 | 有日期 | 仅有日期 |

## 使用示例

### 查询患者的HCPCS编码

```sql
SELECT
    subject_id,
    hadm_id,
    chartdate,
    hcpcs_cd,
    short_description
FROM hcpcsevents
WHERE hadm_id = 12345678
ORDER BY chartdate, seq_num;
```

### 统计最常见的操作

```sql
SELECT
    hcpcs_cd,
    short_description,
    COUNT(*) as frequency
FROM hcpcsevents
GROUP BY hcpcs_cd, short_description
ORDER BY frequency DESC
LIMIT 20;
```

### 查找机械通气患者

```sql
SELECT DISTINCT
    subject_id,
    hadm_id
FROM hcpcsevents
WHERE hcpcs_cd IN ('94002', '94003')
ORDER BY subject_id;
```

## ETL映射建议

1. **CPT编码**: 从医生费用账单系统提取CPT编码
2. **日期记录**: 尽可能记录服务执行的日期
3. **编码验证**: 确保编码在 `d_hcpcs` 表中有定义

## 注意事项

1. **医院vs医生计费**: 此表主要是医院计费的HCPCS，不包括所有医生单独计费的服务
2. **编码更新**: HCPCS/CPT编码每年更新，分析时注意版本
3. **替代cptevents**: 此表替代了MIMIC-III中的 `cptevents` 表
