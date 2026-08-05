# poe 表

## 概述

`poe`（Provider Order Entry，医嘱录入）表记录医生在电子医嘱系统中下达的各类医嘱。包括药物、检验、影像、会诊等各类医嘱的基本信息。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `poe_id` | VARCHAR(25) | NOT NULL, 主键 | 医嘱唯一标识 |
| `poe_seq` | INTEGER | NOT NULL | 医嘱序号 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | 可空 | 住院唯一标识 |
| `ordertime` | TIMESTAMP(0) | NOT NULL | 医嘱下达时间 |
| `order_type` | VARCHAR(25) | NOT NULL | 医嘱类型 |
| `order_subtype` | VARCHAR(50) | 可空 | 医嘱子类型 |
| `transaction_type` | VARCHAR(15) | 可空 | 操作类型 |
| `discontinue_of_poe_id` | VARCHAR(25) | 可空 | 被停止的医嘱ID |
| `discontinued_by_poe_id` | VARCHAR(25) | 可空 | 停止此医嘱的医嘱ID |
| `order_provider_id` | VARCHAR(10) | 可空 | 下达医嘱的医生标识 |
| `order_status` | VARCHAR(15) | 可空 | 医嘱状态 |

## 字段详解

### poe_id
- **含义**: 医嘱的唯一标识
- **格式**: 由 `subject_id` 和 `poe_seq` 组合而成
- **用途**: 连接 `poe_detail`、`prescriptions`、`emar` 等表

### poe_seq
- **含义**: 按时间顺序递增的医嘱序号
- **用途**: 确定医嘱的先后顺序

### ordertime
- **含义**: 医嘱下达的时间
- **临床意义**: 反映医疗决策的时间点

### order_type
- **含义**: 医嘱的主要类型
- **常见取值**:
  | 值 | 说明 |
  |---|---|
  | `Medications` | 药物医嘱 |
  | `Lab` | 检验医嘱 |
  | `Imaging` | 影像检查医嘱 |
  | `Procedures` | 操作/手术医嘱 |
  | `Consults` | 会诊医嘱 |
  | `Nutrition` | 营养医嘱 |
  | `Blood Bank` | 血库医嘱 |
  | `Respiratory` | 呼吸治疗医嘱 |
  | `ADT` | 入院/出院/转科医嘱 |

### order_subtype
- **含义**: 医嘱的详细子类型
- **示例**: 对于 `order_type = 'Lab'`，子类型可能包括 "Chemistry", "Hematology" 等

### transaction_type
- **含义**: 对医嘱执行的操作类型
- **取值**:
  | 值 | 说明 |
  |---|---|
  | `New` | 新建医嘱 |
  | `Change` | 修改医嘱 |
  | `D/C` | 停止医嘱 (Discontinue) |
  | `Renew` | 续签医嘱 |

### discontinue_of_poe_id / discontinued_by_poe_id
- **含义**: 医嘱停止关系
- **用途**:
  - `discontinue_of_poe_id`: 此医嘱是为了停止哪个医嘱
  - `discontinued_by_poe_id`: 此医嘱被哪个医嘱停止

### order_status
- **含义**: 医嘱的当前状态
- **取值**: `Active`（有效）, `Inactive`（无效）

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| poe_detail | poe_id, poe_seq | 一对多 |
| prescriptions | poe_id | 一对一 |
| emar | poe_id | 一对多 |

## 使用示例

### 查询患者的所有医嘱

```sql
SELECT
    poe_id,
    ordertime,
    order_type,
    order_subtype,
    transaction_type,
    order_status
FROM poe
WHERE hadm_id = 12345678
ORDER BY ordertime;
```

### 统计医嘱类型分布

```sql
SELECT
    order_type,
    COUNT(*) as count
FROM poe
GROUP BY order_type
ORDER BY count DESC;
```

### 追踪医嘱的修改历史

```sql
SELECT
    p1.poe_id,
    p1.ordertime,
    p1.transaction_type,
    p2.poe_id as discontinued_by
FROM poe p1
LEFT JOIN poe p2 ON p1.discontinued_by_poe_id = p2.poe_id
WHERE p1.hadm_id = 12345678
ORDER BY p1.ordertime;
```

## ETL映射建议

1. **医嘱类型映射**: 将本地医嘱分类映射到MIMIC的医嘱类型
2. **时间记录**: 记录医嘱下达的准确时间
3. **状态追踪**: 记录医嘱的状态变化（新建、修改、停止）
4. **医嘱关联**: 建立医嘱之间的关联关系（如停止医嘱与原医嘱）

## 注意事项

1. **基本信息表**: 此表只包含医嘱的基本信息，详细内容在 `poe_detail` 表
2. **与其他表的关系**: 药物医嘱的详细信息在 `prescriptions` 表
3. **门诊医嘱**: `hadm_id` 为空的记录可能是门诊医嘱
