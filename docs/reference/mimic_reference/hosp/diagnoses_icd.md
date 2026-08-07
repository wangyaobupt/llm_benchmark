# diagnoses_icd 表

## 概述

`diagnoses_icd` 表存储患者住院期间的诊断编码，使用国际疾病分类（ICD）编码系统。这些诊断由专业编码人员在出院后根据病历记录分配，主要用于医疗费用结算。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | NOT NULL | 住院唯一标识 |
| `seq_num` | INTEGER | NOT NULL | 诊断序号 |
| `icd_code` | VARCHAR(7) | NOT NULL | ICD诊断编码 |
| `icd_version` | INTEGER | NOT NULL | ICD版本（9或10） |

**主键**: (`subject_id`, `hadm_id`, `seq_num`)

## 字段详解

### subject_id / hadm_id
- **含义**: 患者和住院标识
- **关联**: 连接到 `patients` 和 `admissions` 表

### seq_num
- **含义**: 诊断的序号
- **取值范围**: 1 到 39（每次住院最多39个诊断）
- **临床意义**:
  - 较小的 `seq_num` 通常表示更重要的诊断
  - `seq_num = 1` 通常是主要诊断
- **注意**: 这个排序受计费规则影响，不一定严格按临床重要性排列

### icd_code
- **含义**: ICD诊断编码
- **格式**:
  - ICD-9: 3-5位字符，可能以 `E` 或 `V` 开头
  - ICD-10: 3-7位字符，以字母开头
- **示例**:
  | 编码 | 版本 | 含义 |
  |------|------|------|
  | 41401 | 9 | 冠状动脉粥样硬化 |
  | 5849 | 9 | 急性肾衰竭，未特指 |
  | I2510 | 10 | 动脉粥样硬化性心脏病 |
  | N179 | 10 | 急性肾衰竭，未特指 |

### icd_version
- **含义**: ICD编码版本
- **取值**:
  - `9`: ICD-9-CM（临床修订版）
  - `10`: ICD-10-CM
- **说明**: 美国在2015年10月从ICD-9过渡到ICD-10

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| d_icd_diagnoses | icd_code, icd_version | 多对一 |

## 使用示例

### 查询患者的所有诊断

```sql
SELECT
    d.subject_id,
    d.hadm_id,
    d.seq_num,
    d.icd_code,
    d.icd_version,
    def.long_title
FROM diagnoses_icd d
LEFT JOIN d_icd_diagnoses def
    ON d.icd_code = def.icd_code
    AND d.icd_version = def.icd_version
WHERE d.hadm_id = 12345678
ORDER BY d.seq_num;
```

### 统计最常见的诊断

```sql
SELECT
    d.icd_code,
    d.icd_version,
    def.long_title,
    COUNT(*) as frequency
FROM diagnoses_icd d
LEFT JOIN d_icd_diagnoses def
    ON d.icd_code = def.icd_code
    AND d.icd_version = def.icd_version
GROUP BY d.icd_code, d.icd_version, def.long_title
ORDER BY frequency DESC
LIMIT 20;
```

### 筛选特定诊断的患者

```sql
-- 查找所有急性肾衰竭的患者
SELECT DISTINCT subject_id, hadm_id
FROM diagnoses_icd
WHERE (icd_code LIKE '584%' AND icd_version = 9)
   OR (icd_code LIKE 'N17%' AND icd_version = 10);
```

## ICD编码体系说明

### ICD-9-CM 结构
- 001-999: 疾病和损伤
- E800-E999: 外因（外部原因）
- V01-V91: 补充分类（影响健康状态的因素）

### ICD-10-CM 结构
- A00-B99: 传染病和寄生虫病
- C00-D49: 肿瘤
- I00-I99: 循环系统疾病
- J00-J99: 呼吸系统疾病
- N00-N99: 泌尿生殖系统疾病
- ... 以此类推

## ETL映射建议

1. **编码版本**: 确定本地系统使用的ICD版本（9或10）
2. **编码格式**:
   - 移除编码中的小数点（如 "428.0" → "4280"）
   - 保留前导零
3. **主要诊断**: 将本地的主诊断映射为 `seq_num = 1`
4. **诊断排序**: 按诊断的重要性或本地系统的排序映射 `seq_num`
5. **编码验证**: 确保所有编码都能在 `d_icd_diagnoses` 表中找到

## 注意事项

1. **seq_num 的局限性**:
   - 不要完全依赖 `seq_num` 来判断诊断重要性
   - 某些计费规则要求特定诊断顺序（如感染因子必须在脓毒症前）

2. **编码质量**:
   - 诊断编码用于计费，可能存在"向上编码"（upcoding）现象
   - 部分诊断可能是为了支持医疗必要性而添加

3. **时间范围**:
   - 诊断代表整个住院期间的情况
   - 无法确定诊断的具体发生时间

4. **ICD版本过渡**:
   - 2015年前主要使用ICD-9
   - 2015年后主要使用ICD-10
   - 分析跨越此时间段的数据时需处理版本差异
