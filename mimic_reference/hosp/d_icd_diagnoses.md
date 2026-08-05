# d_icd_diagnoses 表

## 概述

`d_icd_diagnoses` 是ICD诊断编码的维度表（字典表），为 `diagnoses_icd` 表中的ICD编码提供描述信息。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `icd_code` | CHAR(7) | NOT NULL | ICD诊断编码 |
| `icd_version` | INTEGER | NOT NULL | ICD版本号 |
| `long_title` | VARCHAR(255) | 可空 | 诊断的完整描述 |

**主键**: (`icd_code`, `icd_version`)

## 字段详解

### icd_code
- **含义**: ICD诊断编码
- **格式**:
  - ICD-9-CM: 3-5位，可能以E或V开头
  - ICD-10-CM: 3-7位，以字母开头
- **注意**: 编码中的小数点已移除

### icd_version
- **含义**: ICD编码版本
- **取值**: 9 或 10

### long_title
- **含义**: 诊断编码的完整文字描述
- **语言**: 英语

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| diagnoses_icd | icd_code, icd_version | 一对多 |

## 常见诊断编码示例

### ICD-9-CM

| 编码 | 描述 |
|------|------|
| 41401 | Coronary atherosclerosis of native coronary artery |
| 5849 | Acute kidney failure, unspecified |
| 42731 | Atrial fibrillation |
| 51881 | Acute respiratory failure |
| 99859 | Other postoperative infection |

### ICD-10-CM

| 编码 | 描述 |
|------|------|
| I2510 | Atherosclerotic heart disease of native coronary artery |
| N179 | Acute kidney failure, unspecified |
| I4891 | Unspecified atrial fibrillation |
| J9600 | Acute respiratory failure, unspecified |
| T8149XA | Infection following a procedure, unspecified |

## 使用示例

### 查询诊断描述

```sql
SELECT
    icd_code,
    icd_version,
    long_title
FROM d_icd_diagnoses
WHERE icd_code = '5849';
```

### 搜索特定疾病

```sql
SELECT
    icd_code,
    icd_version,
    long_title
FROM d_icd_diagnoses
WHERE long_title ILIKE '%diabetes%';
```

### 联合查询患者诊断

```sql
SELECT
    d.hadm_id,
    d.seq_num,
    d.icd_code,
    def.long_title
FROM diagnoses_icd d
LEFT JOIN d_icd_diagnoses def
    ON d.icd_code = def.icd_code
    AND d.icd_version = def.icd_version
WHERE d.hadm_id = 12345678
ORDER BY d.seq_num;
```

## ETL映射建议

1. **编码字典**: 从CMS获取官方ICD编码字典
2. **版本管理**: 区分ICD-9和ICD-10编码
3. **历史编码**: 包含历史上使用过但现已废弃的编码

## 注意事项

1. **小数点处理**: ICD编码存储时不含小数点
2. **版本差异**: ICD-9和ICD-10是不同的编码体系，不能直接对应
3. **编码演变**: 此表包含2008-2019年间有效的所有ICD编码
4. **仅CM编码**: 此表仅包含诊断编码（CM），不包含操作编码（PCS）
