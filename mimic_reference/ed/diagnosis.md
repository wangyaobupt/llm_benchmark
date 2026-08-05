# diagnosis 表（急诊诊断）

## 概述

`diagnosis` 表存储急诊科患者的诊断信息，使用ICD编码系统（ICD-9或ICD-10）记录。此表记录的是急诊阶段的诊断，与住院诊断（`diagnoses_icd`）是不同的。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `stay_id` | INTEGER | NOT NULL | 急诊就诊唯一标识 |
| `seq_num` | INTEGER | NOT NULL | 诊断序号 |
| `icd_code` | VARCHAR(10) | NOT NULL | ICD诊断编码 |
| `icd_version` | INTEGER | NOT NULL | ICD版本（9或10） |
| `icd_title` | TEXT | NOT NULL | 诊断描述 |

## 字段详解

### subject_id
- **含义**: 患者的唯一标识符
- **关联**: 与 `edstays` 表关联

### stay_id
- **含义**: 急诊就诊的唯一标识
- **关联**: 外键关联 `edstays` 表

### seq_num
- **含义**: 诊断的优先序号
- **说明**: `seq_num = 1` 通常表示主诊断
- **注意**: 对于多个诊断，优先级确定可能存在困难

### icd_code
- **含义**: ICD诊断编码
- **格式**: ICD-9或ICD-10格式的编码字符串
- **示例**: `J189`（肺炎）, `I10`（高血压）

### icd_version
- **含义**: ICD编码版本
- **取值**:
  | 值 | 说明 |
  |---|---|
  | 9 | ICD-9-CM编码 |
  | 10 | ICD-10-CM编码 |
- **说明**: 2015年10月后美国医疗系统主要使用ICD-10

### icd_title
- **含义**: 诊断的文字描述
- **用途**: 便于理解诊断内容，无需查询编码字典

## 数据规模

- 总行数: 899,050 行
- 来源: 急诊科信息系统

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| edstays | stay_id | 多对一 |
| patients | subject_id | 多对一 |
| d_icd_diagnoses | icd_code, icd_version | 多对一 |

## 使用示例

### 查询急诊诊断

```sql
SELECT
    stay_id,
    seq_num,
    icd_code,
    icd_version,
    icd_title
FROM diagnosis
WHERE stay_id = 12345678
ORDER BY seq_num;
```

### 统计常见急诊诊断

```sql
SELECT
    icd_code,
    icd_title,
    COUNT(*) as count
FROM diagnosis
WHERE seq_num = 1  -- 主诊断
GROUP BY icd_code, icd_title
ORDER BY count DESC
LIMIT 20;
```

### 查找特定诊断的急诊就诊

```sql
SELECT
    e.subject_id,
    e.stay_id,
    e.intime,
    d.icd_code,
    d.icd_title
FROM edstays e
INNER JOIN diagnosis d ON e.stay_id = d.stay_id
WHERE d.icd_code LIKE 'I21%'  -- 急性心肌梗死
ORDER BY e.intime;
```

### 比较急诊诊断与住院诊断

```sql
SELECT
    e.stay_id,
    e.hadm_id,
    ed.icd_code as ed_diagnosis,
    ed.icd_title as ed_title,
    hd.icd_code as hosp_diagnosis,
    hd.icd_title as hosp_title
FROM edstays e
INNER JOIN diagnosis ed ON e.stay_id = ed.stay_id AND ed.seq_num = 1
LEFT JOIN diagnoses_icd hd ON e.hadm_id = hd.hadm_id AND hd.seq_num = 1
WHERE e.hadm_id IS NOT NULL
LIMIT 100;
```

### 按ICD版本统计

```sql
SELECT
    icd_version,
    COUNT(*) as diagnosis_count,
    COUNT(DISTINCT stay_id) as stay_count
FROM diagnosis
GROUP BY icd_version;
```

## 应用场景

### 1. 急诊疾病谱分析
- 分析急诊常见诊断分布
- 研究特定疾病的急诊就诊模式

### 2. 诊断准确性研究
- 比较急诊诊断与住院后最终诊断
- 评估急诊诊断的敏感性和特异性

### 3. 临床研究
- 筛选特定诊断的研究队列
- 分析合并症的影响

## ETL映射建议

1. **编码版本处理**: 注意区分ICD-9和ICD-10编码
2. **主诊断识别**: `seq_num = 1` 标识主诊断
3. **编码映射**: 可能需要将ICD编码映射到本地编码系统
4. **时间关联**: 通过 `stay_id` 关联就诊时间

## 注意事项

1. **急诊诊断**: 此表记录的是急诊阶段的诊断，可能与最终住院诊断不同
2. **诊断时机**: 急诊诊断通常在信息有限的情况下做出
3. **ICD版本混合**: 数据集中同时包含ICD-9和ICD-10编码
4. **与住院诊断区分**: 此表（ED模块）与 `diagnoses_icd`（HOSP模块）是不同的表
