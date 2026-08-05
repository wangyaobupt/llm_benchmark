# pharmacy 表

## 概述

`pharmacy` 表存储药房配药的详细信息，是 `prescriptions` 表的补充。包含药物的详细给药计划、状态和特殊给药参数（如PCA设置）。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `pharmacy_id` | INTEGER | NOT NULL, 主键 | 药房记录唯一标识 |
| `poe_id` | VARCHAR(25) | 可空 | 医嘱标识 |
| `starttime` | TIMESTAMP(3) | 可空 | 用药开始时间 |
| `stoptime` | TIMESTAMP(3) | 可空 | 用药结束时间 |
| `medication` | TEXT | 可空 | 药物名称 |
| `proc_type` | VARCHAR(50) | NOT NULL | 处方类型 |
| `status` | VARCHAR(50) | 可空 | 处方状态 |
| `entertime` | TIMESTAMP(3) | NOT NULL | 录入时间 |
| `verifiedtime` | TIMESTAMP(3) | 可空 | 审核时间 |
| `route` | VARCHAR(50) | 可空 | 给药途径 |
| `frequency` | VARCHAR(50) | 可空 | 给药频次 |
| `disp_sched` | VARCHAR(255) | 可空 | 配药时间表 |
| `infusion_type` | VARCHAR(15) | 可空 | 输液类型 |
| `sliding_scale` | VARCHAR(1) | 可空 | 滑动比例标志 |
| `lockout_interval` | VARCHAR(50) | 可空 | PCA锁定间隔 |
| `basal_rate` | REAL | 可空 | 基础速率 |
| `one_hr_max` | VARCHAR(10) | 可空 | 每小时最大剂量 |
| `doses_per_24_hrs` | REAL | 可空 | 每日给药次数 |
| `duration` | REAL | 可空 | 持续时间数值 |
| `duration_interval` | VARCHAR(50) | 可空 | 持续时间单位 |
| `expiration_value` | INTEGER | 可空 | 有效期数值 |
| `expiration_unit` | VARCHAR(50) | 可空 | 有效期单位 |
| `expirationdate` | TIMESTAMP(3) | 可空 | 过期日期 |
| `dispensation` | VARCHAR(50) | 可空 | 配发来源 |
| `fill_quantity` | VARCHAR(50) | 可空 | 配发数量 |

## 字段详解

### 核心标识

#### pharmacy_id
- **含义**: 药房记录的唯一标识
- **用途**: 连接 `prescriptions`、`emar` 等表

### 用药时间

#### starttime / stoptime
- **含义**: 药物使用的起止时间
- **说明**: 与 `prescriptions` 表中的时间应一致

#### entertime / verifiedtime
- **含义**: 处方录入时间和药师审核时间
- **临床意义**: 反映处方的审核流程

### 用药方式

#### proc_type
- **含义**: 处方的类型
- **常见取值**:
  | 值 | 说明 |
  |---|---|
  | `IV Piggyback` | 静脉间歇输注 |
  | `Unit Dose` | 单位剂量 |
  | `Continuous Med` | 持续用药 |
  | `IV Push` | 静脉推注 |

#### route
- **含义**: 给药途径
- **取值**: 同 `prescriptions` 表

#### frequency
- **含义**: 给药频次代码
- **常见取值**: `Q6H`, `Q8H`, `TID`, `BID`, `DAILY`, `PRN`

#### disp_sched
- **含义**: 具体的配药时间安排
- **示例**: "06:00, 12:00, 18:00, 24:00"

### 输液相关

#### infusion_type
- **含义**: 输液的类型代码
- **取值**:
  | 值 | 说明 |
  |---|---|
  | `B` | 基础 |
  | `C` | 持续 |
  | `N` | 新袋 |
  | `N1` | 新袋类型1 |
  | `O` | 其他 |
  | `R` | 替换 |

### PCA相关（患者自控镇痛）

#### lockout_interval
- **含义**: PCA锁定时间
- **说明**: 两次患者自行给药的最小间隔

#### basal_rate
- **含义**: 基础输注速率（24小时）
- **单位**: 根据具体药物而定

#### one_hr_max
- **含义**: 每小时最大给药剂量
- **用途**: 安全限制

### 状态信息

#### status
- **含义**: 处方当前状态
- **取值**: `Active`（有效）, `Inactive`（无效）, `Discontinued`（已停）

### 有效期

#### expiration_value / expiration_unit / expirationdate
- **含义**: 药物的有效期信息
- **说明**: 配制后药物的稳定期限

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| prescriptions | pharmacy_id | 一对一 |
| emar | pharmacy_id | 一对多 |
| poe | poe_id | 多对一 |

## 使用示例

### 查询PCA设置

```sql
SELECT
    subject_id,
    hadm_id,
    medication,
    basal_rate,
    lockout_interval,
    one_hr_max
FROM pharmacy
WHERE lockout_interval IS NOT NULL
ORDER BY starttime;
```

### 统计处方类型分布

```sql
SELECT
    proc_type,
    COUNT(*) as count
FROM pharmacy
GROUP BY proc_type
ORDER BY count DESC;
```

## ETL映射建议

1. **与处方关联**: 确保 `pharmacy_id` 与 `prescriptions` 表一致
2. **PCA参数**: 如有PCA系统，映射相关参数
3. **状态管理**: 记录处方的状态变化
4. **频次标准化**: 将本地频次代码标准化

## 注意事项

1. **并非所有处方**: 不是所有 `prescriptions` 记录都有对应的 `pharmacy` 记录
2. **详细信息补充**: 此表提供比 `prescriptions` 更详细的给药参数
3. **时间一致性**: 注意与 `prescriptions` 表中时间的一致性
