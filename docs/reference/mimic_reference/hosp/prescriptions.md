# prescriptions 表

## 概述

`prescriptions` 表存储医生开具的药物处方信息，包括药物名称、剂量、给药途径和时间等。此表记录的是处方医嘱，而非实际给药记录（实际给药见 `emar` 表）。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `pharmacy_id` | INTEGER | NOT NULL | 药房记录标识 |
| `poe_id` | VARCHAR(25) | 可空 | 医嘱标识 |
| `poe_seq` | INTEGER | 可空 | 医嘱序号 |
| `order_provider_id` | VARCHAR(10) | 可空 | 开单医生标识 |
| `starttime` | TIMESTAMP(3) | 可空 | 处方开始时间 |
| `stoptime` | TIMESTAMP(3) | 可空 | 处方结束时间 |
| `drug_type` | VARCHAR(20) | NOT NULL | 药物成分类型 |
| `drug` | VARCHAR(255) | NOT NULL | 药物名称 |
| `formulary_drug_cd` | VARCHAR(50) | 可空 | 医院药物目录代码 |
| `gsn` | VARCHAR(255) | 可空 | 通用序列号 |
| `ndc` | VARCHAR(25) | 可空 | 国家药品编码 |
| `prod_strength` | VARCHAR(255) | 可空 | 药品规格 |
| `form_rx` | VARCHAR(25) | 可空 | 药品剂型 |
| `dose_val_rx` | VARCHAR(100) | 可空 | 处方剂量值 |
| `dose_unit_rx` | VARCHAR(50) | 可空 | 处方剂量单位 |
| `form_val_disp` | VARCHAR(50) | 可空 | 单次给药量 |
| `form_unit_disp` | VARCHAR(50) | 可空 | 单次给药单位 |
| `doses_per_24_hrs` | REAL | 可空 | 每24小时给药次数 |
| `route` | VARCHAR(50) | 可空 | 给药途径 |

## 字段详解

### pharmacy_id
- **含义**: 关联 `pharmacy` 表和 `emar` 表的标识符
- **用途**: 可用于追踪处方的填充和执行情况

### poe_id / poe_seq
- **含义**: 关联到 `poe`（医嘱录入）表的标识符
- **用途**: 追踪处方的原始医嘱

### drug_type
- **含义**: 药物在处方中的成分类型
- **取值**:
  | 值 | 说明 |
  |---|---|
  | `MAIN` | 主要成分 |
  | `BASE` | 基础液体（如生理盐水） |
  | `ADDITIVE` | 添加剂 |
- **说明**: 一个处方可能有多行记录（主药+溶媒+添加剂）

### drug
- **含义**: 药物的自由文本描述
- **示例**: "Vancomycin", "Insulin Regular Human", "Normal Saline"

### formulary_drug_cd
- **含义**: 医院药物目录中的代码
- **用途**: 医院内部药物标准化标识

### gsn (Generic Sequence Number)
- **含义**: First Databank的通用序列号
- **用途**: 药物标准化编码，便于跨系统映射

### ndc (National Drug Code)
- **含义**: 美国国家药品编码
- **格式**: 10-11位数字（如 "0009-0100-01"）
- **结构**: 厂商-产品-包装

### prod_strength
- **含义**: 药品的规格和浓度
- **示例**: "12 mg / 0.8 mL", "500 mg", "10 units/mL"

### form_rx
- **含义**: 药品的剂型/包装形式
- **常见取值**: `TABLET`, `VIAL`, `BAG`, `AMP`, `SOLN`

### dose_val_rx / dose_unit_rx
- **含义**: 医生处方的剂量和单位
- **示例**: dose_val_rx = "500", dose_unit_rx = "mg"

### form_val_disp / form_unit_disp
- **含义**: 单次配发的药量和单位
- **说明**: 药房配发的最小单位

### doses_per_24_hrs
- **含义**: 每24小时的给药频次
- **示例**:
  - Q6H → 4次/24小时
  - TID → 3次/24小时
  - Q8H → 3次/24小时

### route
- **含义**: 给药途径
- **常见取值**:
  | 值 | 说明 |
  |---|---|
  | `IV` | 静脉注射 |
  | `PO` | 口服 |
  | `IM` | 肌肉注射 |
  | `SC` | 皮下注射 |
  | `IVPCA` | 静脉患者自控镇痛 |
  | `INH` | 吸入 |
  | `TOP` | 外用 |

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| pharmacy | pharmacy_id | 一对一 |
| poe | poe_id | 多对一 |
| emar | pharmacy_id | 一对多 |

## 使用示例

### 查询患者的抗生素处方

```sql
SELECT
    subject_id,
    hadm_id,
    drug,
    starttime,
    stoptime,
    dose_val_rx,
    dose_unit_rx,
    route
FROM prescriptions
WHERE drug ILIKE '%vancomycin%'
  AND hadm_id = 12345678
ORDER BY starttime;
```

### 统计最常用的药物

```sql
SELECT
    drug,
    COUNT(DISTINCT hadm_id) as admission_count
FROM prescriptions
WHERE drug_type = 'MAIN'
GROUP BY drug
ORDER BY admission_count DESC
LIMIT 20;
```

## ETL映射建议

1. **药物标准化**: 使用NDC或GSN进行药物标准化映射
2. **剂量信息**: 分别提取剂量值和单位
3. **给药频次**: 将本地频次代码转换为每日次数
4. **给药途径**: 标准化给药途径编码
5. **时间处理**: 记录处方的有效起止时间

## 注意事项

1. **处方 vs 给药**: 此表记录处方医嘱，实际给药情况见 `emar` 表
2. **多行记录**: 一个输液处方可能有多行（主药、溶媒、添加剂）
3. **医院特定编码**: `formulary_drug_cd` 是医院特定编码，不具通用性
4. **剂量单位变化**: 同一药物在不同处方中可能使用不同单位
