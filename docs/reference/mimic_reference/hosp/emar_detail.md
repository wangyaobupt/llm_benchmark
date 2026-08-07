# emar_detail 表

## 概述

`emar_detail` 表存储 `emar` 表中给药记录的详细信息，包括剂量、给药部位、输液速率等。采用类似EAV的扩展结构。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `emar_id` | VARCHAR(25) | NOT NULL | 给药记录标识 |
| `emar_seq` | INTEGER | NOT NULL | 给药序号 |
| `parent_field_ordinal` | VARCHAR(10) | 可空 | 父字段序号 |
| `administration_type` | VARCHAR(50) | 可空 | 给药类型 |
| `pharmacy_id` | INTEGER | 可空 | 药房记录标识 |
| `barcode_type` | VARCHAR(4) | 可空 | 条形码类型 |
| `reason_for_no_barcode` | TEXT | 可空 | 未扫码原因 |
| `complete_dose_not_given` | VARCHAR(5) | 可空 | 完整剂量是否未给 |
| `dose_due` | VARCHAR(100) | 可空 | 应给剂量 |
| `dose_due_unit` | VARCHAR(50) | 可空 | 应给剂量单位 |
| `dose_given` | VARCHAR(255) | 可空 | 实际给予剂量 |
| `dose_given_unit` | VARCHAR(50) | 可空 | 实际给予剂量单位 |
| `will_remainder_of_dose_be_given` | VARCHAR(5) | 可空 | 剩余剂量是否会给 |
| `product_amount_given` | VARCHAR(30) | 可空 | 产品给予量 |
| `product_unit` | VARCHAR(30) | 可空 | 产品单位 |
| `product_code` | VARCHAR(30) | 可空 | 产品代码 |
| `product_description` | VARCHAR(255) | 可空 | 产品描述 |
| `product_description_other` | VARCHAR(255) | 可空 | 其他产品描述 |
| `prior_infusion_rate` | VARCHAR(40) | 可空 | 之前输液速率 |
| `infusion_rate` | VARCHAR(40) | 可空 | 当前输液速率 |
| `infusion_rate_adjustment` | VARCHAR(50) | 可空 | 速率调整 |
| `infusion_rate_adjustment_amount` | VARCHAR(30) | 可空 | 速率调整量 |
| `infusion_rate_unit` | VARCHAR(30) | 可空 | 输液速率单位 |
| `route` | VARCHAR(10) | 可空 | 给药途径 |
| `infusion_complete` | VARCHAR(1) | 可空 | 输液是否完成 |
| `completion_interval` | VARCHAR(50) | 可空 | 完成时间间隔 |
| `new_iv_bag_hung` | VARCHAR(1) | 可空 | 是否挂新袋 |
| `continued_infusion_in_other_location` | VARCHAR(1) | 可空 | 是否在其他位置继续输液 |
| `restart_interval` | TEXT | 可空 | 重启间隔 |
| `side` | VARCHAR(10) | 可空 | 身体侧（左/右） |
| `site` | VARCHAR(255) | 可空 | 给药部位 |
| `non_formulary_visual_verification` | VARCHAR(1) | 可空 | 非处方目录药物视觉确认 |

## 字段详解

### parent_field_ordinal
- **含义**: 区分同一eMAR事件的多次给药
- **说明**:
  - NULL: 代表整个给药事件的汇总行
  - 数值(1, 2, ...): 代表每次扫描的药品单位
- **示例**: 如果给200mg药物，每瓶100mg，则会有：
  - 1行 `parent_field_ordinal = NULL`（汇总）
  - 2行 `parent_field_ordinal = 1, 2`（每瓶药）

### administration_type
- **含义**: 给药方式的类型
- **常见取值**: `IV Bolus`, `IV Infusion`, `Oral`, `Injection`

### dose_due / dose_given
- **含义**: 应给剂量和实际给予剂量
- **对比**: 两者可能不同（如部分给药）

### infusion_rate 相关字段
- **用途**: 记录输液的速率和速率调整
- **临床意义**: 对于持续输注的药物非常重要

### site / side
- **含义**: 给药的具体部位和身体侧
- **示例**: site = "Left Arm", side = "Left"

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| emar | emar_id, emar_seq | 多对一 |
| patients | subject_id | 多对一 |
| pharmacy | pharmacy_id | 多对一 |

## 使用示例

### 查询给药的详细剂量信息

```sql
SELECT
    e.charttime,
    e.medication,
    ed.dose_due,
    ed.dose_due_unit,
    ed.dose_given,
    ed.dose_given_unit,
    ed.route
FROM emar e
INNER JOIN emar_detail ed ON e.emar_id = ed.emar_id AND e.emar_seq = ed.emar_seq
WHERE e.hadm_id = 12345678
  AND ed.parent_field_ordinal IS NULL
ORDER BY e.charttime;
```

### 分析输液速率变化

```sql
SELECT
    e.charttime,
    e.medication,
    ed.prior_infusion_rate,
    ed.infusion_rate,
    ed.infusion_rate_adjustment
FROM emar e
INNER JOIN emar_detail ed ON e.emar_id = ed.emar_id AND e.emar_seq = ed.emar_seq
WHERE ed.infusion_rate IS NOT NULL
ORDER BY e.charttime;
```

## ETL映射建议

1. **剂量对照**: 记录应给剂量和实际给予剂量
2. **速率追踪**: 对输液药物记录速率变化
3. **部位记录**: 记录注射/输液的具体部位
4. **条形码系统**: 如有，记录条形码扫描信息

## 注意事项

1. **一对多关系**: 每个 `emar` 记录可能有多行 `emar_detail`
2. **汇总行**: `parent_field_ordinal = NULL` 的行包含整体给药信息
3. **明细行**: 其他行包含每个药品单位的详细信息
4. **字段分布**: 某些字段仅在汇总行有值，某些仅在明细行有值
