# microbiologyevents 表

## 概述

`microbiologyevents` 表存储微生物学检验结果，包括细菌培养、病原体鉴定和药物敏感性试验结果。这是研究感染和抗生素使用的关键数据源。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `microevent_id` | INTEGER | NOT NULL, 主键 | 微生物事件唯一标识 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | 可空 | 住院唯一标识 |
| `micro_specimen_id` | INTEGER | NOT NULL | 微生物标本标识 |
| `order_provider_id` | VARCHAR(10) | 可空 | 开单医生标识 |
| `chartdate` | TIMESTAMP(0) | NOT NULL | 记录日期 |
| `charttime` | TIMESTAMP(0) | 可空 | 记录时间 |
| `spec_itemid` | INTEGER | NOT NULL | 标本类型标识 |
| `spec_type_desc` | VARCHAR(100) | NOT NULL | 标本类型描述 |
| `test_seq` | INTEGER | NOT NULL | 测试序号 |
| `storedate` | TIMESTAMP(0) | 可空 | 结果存储日期 |
| `storetime` | TIMESTAMP(0) | 可空 | 结果存储时间 |
| `test_itemid` | INTEGER | 可空 | 测试项目标识 |
| `test_name` | VARCHAR(100) | 可空 | 测试名称 |
| `org_itemid` | INTEGER | 可空 | 微生物标识 |
| `org_name` | VARCHAR(100) | 可空 | 微生物名称 |
| `isolate_num` | SMALLINT | 可空 | 分离株编号 |
| `quantity` | VARCHAR(50) | 可空 | 菌落数量 |
| `ab_itemid` | INTEGER | 可空 | 抗生素标识 |
| `ab_name` | VARCHAR(30) | 可空 | 抗生素名称 |
| `dilution_text` | VARCHAR(10) | 可空 | 稀释度文本 |
| `dilution_comparison` | VARCHAR(20) | 可空 | 稀释度比较符 |
| `dilution_value` | DOUBLE PRECISION | 可空 | 稀释度数值 |
| `interpretation` | VARCHAR(5) | 可空 | 敏感性解读 |
| `comments` | TEXT | 可空 | 备注 |

## 字段详解

### 标本信息

#### micro_specimen_id
- **含义**: 微生物标本的唯一标识
- **用途**: 同一标本的所有检测共享此ID

#### spec_itemid / spec_type_desc
- **含义**: 标本类型的代码和描述
- **常见取值**:
  | spec_type_desc | 说明 |
  |----------------|------|
  | BLOOD CULTURE | 血培养 |
  | URINE | 尿液 |
  | SPUTUM | 痰液 |
  | MRSA SCREEN | MRSA筛查 |
  | STOOL | 粪便 |
  | BRONCHIAL WASHINGS | 支气管冲洗液 |
  | WOUND | 伤口分泌物 |

### 测试信息

#### test_seq
- **含义**: 区分同一标本的多次测试
- **说明**: 同一标本可能进行多次培养或检测

#### test_itemid / test_name
- **含义**: 测试类型的代码和名称
- **示例**: "CULTURE", "GRAM STAIN", "FUNGAL CULTURE"

### 微生物信息

#### org_itemid / org_name
- **含义**: 检出微生物的代码和名称
- **说明**: 培养阴性时此字段为空
- **常见病原体**:
  | org_name | 说明 |
  |----------|------|
  | STAPHYLOCOCCUS AUREUS | 金黄色葡萄球菌 |
  | ESCHERICHIA COLI | 大肠杆菌 |
  | PSEUDOMONAS AERUGINOSA | 铜绿假单胞菌 |
  | KLEBSIELLA PNEUMONIAE | 肺炎克雷伯菌 |
  | ENTEROCOCCUS | 肠球菌 |
  | CANDIDA ALBICANS | 白色念珠菌 |

#### isolate_num
- **含义**: 分离株编号
- **说明**: 同一标本可能培养出多种细菌，每种细菌单独编号

#### quantity
- **含义**: 菌落计数或定量结果
- **取值示例**: ">100,000 CFU/ML", "MANY", "FEW"

### 药敏信息

#### ab_itemid / ab_name
- **含义**: 测试的抗生素代码和名称
- **常见抗生素**:
  | ab_name | 说明 |
  |---------|------|
  | VANCOMYCIN | 万古霉素 |
  | GENTAMICIN | 庆大霉素 |
  | CIPROFLOXACIN | 环丙沙星 |
  | PIPERACILLIN/TAZO | 哌拉西林/他唑巴坦 |

#### dilution_text / dilution_comparison / dilution_value
- **含义**: 最小抑菌浓度（MIC）相关信息
- **示例**: dilution_text = "<=2", dilution_comparison = "<=", dilution_value = 2

#### interpretation
- **含义**: 敏感性解读结果
- **取值**:
  | 值 | 含义 |
  |---|------|
  | `S` | 敏感 (Susceptible) |
  | `R` | 耐药 (Resistant) |
  | `I` | 中介 (Intermediate) |
  | `P` | 待定 (Pending) |

## 数据层次结构

```
标本 (micro_specimen_id)
  └── 测试 (test_seq)
        └── 微生物 (org_itemid)
              └── 分离株 (isolate_num)
                    └── 抗生素药敏 (ab_itemid)
```

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |

## 使用示例

### 查询血培养阳性的患者

```sql
SELECT DISTINCT
    subject_id,
    hadm_id,
    org_name,
    chartdate
FROM microbiologyevents
WHERE spec_type_desc = 'BLOOD CULTURE'
  AND org_name IS NOT NULL
ORDER BY chartdate;
```

### 统计病原体分布

```sql
SELECT
    org_name,
    COUNT(DISTINCT micro_specimen_id) as specimen_count
FROM microbiologyevents
WHERE org_name IS NOT NULL
GROUP BY org_name
ORDER BY specimen_count DESC
LIMIT 20;
```

### 查询特定细菌的药敏结果

```sql
SELECT
    ab_name,
    interpretation,
    COUNT(*) as count
FROM microbiologyevents
WHERE org_name = 'STAPHYLOCOCCUS AUREUS'
  AND ab_name IS NOT NULL
GROUP BY ab_name, interpretation
ORDER BY ab_name, interpretation;
```

## ETL映射建议

1. **标本管理**: 为每个标本分配唯一的 `micro_specimen_id`
2. **病原体编码**: 标准化微生物名称，建议使用标准命名
3. **药敏结果**: 标准化敏感性解读为S/R/I
4. **时间记录**: 区分采样时间和出结果时间

## 注意事项

1. **阴性培养**: 培养阴性时 `org_name` 为空
2. **中间结果**: 此表只包含最终结果，不包含中间报告
3. **多重感染**: 同一标本可能培养出多种病原体
4. **数据冗余**: 为便于查询，层级较高的信息（如标本、微生物）在下级记录中重复
