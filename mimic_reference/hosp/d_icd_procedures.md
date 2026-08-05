# d_icd_procedures 表

## 概述

`d_icd_procedures` 是ICD操作编码的维度表（字典表），为 `procedures_icd` 表中的ICD操作编码提供描述信息。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `icd_code` | CHAR(7) | NOT NULL | ICD操作编码 |
| `icd_version` | INTEGER | NOT NULL | ICD版本号 |
| `long_title` | VARCHAR(255) | 可空 | 操作的完整描述 |

**主键**: (`icd_code`, `icd_version`)

## 字段详解

### icd_code
- **含义**: ICD操作编码
- **格式**:
  - ICD-9-PCS: 2-4位数字
  - ICD-10-PCS: 7位字母数字

### icd_version
- **含义**: ICD编码版本
- **取值**: 9 或 10

### long_title
- **含义**: 操作编码的完整文字描述

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| procedures_icd | icd_code, icd_version | 一对多 |

## 常见操作编码示例

### ICD-9-PCS

| 编码 | 描述 |
|------|------|
| 3961 | Extracorporeal circulation auxiliary to open heart surgery (ECMO) |
| 9671 | Continuous invasive mechanical ventilation <96 hours |
| 9672 | Continuous invasive mechanical ventilation ≥96 hours |
| 3893 | Venous catheterization, not elsewhere classified |
| 8856 | Coronary arteriography using two catheters |

### ICD-10-PCS

| 编码 | 描述 |
|------|------|
| 5A1955Z | Respiratory Ventilation, Greater than 96 Consecutive Hours |
| 5A1945Z | Respiratory Ventilation, 24-96 Consecutive Hours |
| 02100Z9 | Bypass Coronary Artery, One Artery from Left Internal Mammary |

## ICD-10-PCS编码结构

ICD-10-PCS的7位编码结构：
| 位置 | 含义 | 示例（5A1955Z） |
|------|------|----------------|
| 1 | Section (部分) | 5 = Extracorporeal Assistance |
| 2 | Body System (身体系统) | A = Physiological Systems |
| 3 | Root Operation (根操作) | 1 = Performance |
| 4 | Body Part (身体部位) | 9 = Respiratory |
| 5 | Duration (持续时间) | 5 = Greater than 96 Hours |
| 6 | Function (功能) | 5 = Ventilation |
| 7 | Qualifier (限定符) | Z = No Qualifier |

## 使用示例

### 查询操作描述

```sql
SELECT
    icd_code,
    icd_version,
    long_title
FROM d_icd_procedures
WHERE icd_code = '9671';
```

### 搜索特定操作

```sql
SELECT
    icd_code,
    icd_version,
    long_title
FROM d_icd_procedures
WHERE long_title ILIKE '%mechanical ventilation%';
```

## ETL映射建议

1. **编码字典**: 从CMS获取官方ICD-PCS编码字典
2. **版本管理**: 区分ICD-9-PCS和ICD-10-PCS
3. **粒度差异**: ICD-10-PCS比ICD-9-PCS详细得多

## 注意事项

1. **仅PCS编码**: 此表仅包含操作编码（PCS），不包含诊断编码（CM）
2. **版本差异**: ICD-10-PCS的编码粒度远高于ICD-9-PCS
3. **小数点**: 编码存储时不含小数点
