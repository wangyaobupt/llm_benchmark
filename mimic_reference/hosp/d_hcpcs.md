# d_hcpcs 表

## 概述

`d_hcpcs` 是HCPCS/CPT编码的维度表（字典表），为 `hcpcsevents` 表中的编码提供描述信息。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `code` | CHAR(5) | NOT NULL, 主键 | HCPCS/CPT编码 |
| `category` | SMALLINT | 可空 | 编码分类 |
| `long_description` | TEXT | 可空 | 完整描述 |
| `short_description` | VARCHAR(180) | 可空 | 简短描述 |

## 字段详解

### code
- **含义**: 5位的HCPCS或CPT编码
- **格式**: 字母数字混合

### category
- **含义**: 编码的大类
- **说明**: 用于对编码进行粗略分类

### long_description / short_description
- **含义**: 编码的完整和简短文字描述

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| hcpcsevents | hcpcs_cd → code | 一对多 |

## HCPCS编码体系

### Level I - CPT编码

由AMA（美国医学会）维护，主要用于医疗服务和操作。

| 范围 | 类别 |
|------|------|
| 00100-01999 | 麻醉 |
| 10021-69990 | 外科手术 |
| 70010-79999 | 放射学 |
| 80047-89398 | 病理学和检验医学 |
| 90281-99199 | 医疗服务 |
| 99201-99499 | 评估和管理 |

### Level II - HCPCS编码

由CMS维护，用于非医生服务、药品、设备等。

| 范围 | 类别 |
|------|------|
| A0000-A9999 | 运输、设备、供应品 |
| B4000-B9999 | 肠内和肠外治疗 |
| C1000-C9999 | 门诊PPS |
| J0000-J9999 | 药品（非口服） |
| L0000-L9999 | 矫形器和假肢 |

## 使用示例

### 查询编码描述

```sql
SELECT
    code,
    short_description,
    long_description
FROM d_hcpcs
WHERE code = '99291';
```

### 搜索特定服务

```sql
SELECT
    code,
    short_description
FROM d_hcpcs
WHERE short_description ILIKE '%critical care%';
```

### 联合查询

```sql
SELECT
    h.hadm_id,
    h.hcpcs_cd,
    d.short_description
FROM hcpcsevents h
LEFT JOIN d_hcpcs d ON h.hcpcs_cd = d.code
WHERE h.hadm_id = 12345678;
```

## ETL映射建议

1. **编码字典**: 从CMS和AMA获取官方编码字典
2. **年度更新**: HCPCS/CPT编码每年更新
3. **描述匹配**: 确保编码与正确版本的描述匹配

## 注意事项

1. **CPT版权**: CPT编码是AMA的注册商标，使用受版权保护
2. **年度变化**: 编码和描述每年可能更新
3. **不完整**: 此表可能不包含所有HCPCS编码
