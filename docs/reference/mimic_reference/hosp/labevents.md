# labevents 表

## 概述

`labevents` 表存储患者的实验室检验结果，是MIMIC-IV中最重要和最常用的数据表之一。包含血液、尿液等各类标本的检验结果。

## 表结构

| 字段名 | 数据类型 | 约束 | 说明 |
|--------|----------|------|------|
| `labevent_id` | INTEGER | NOT NULL, 主键 | 检验事件唯一标识 |
| `subject_id` | INTEGER | NOT NULL | 患者唯一标识 |
| `hadm_id` | INTEGER | 可空 | 住院唯一标识 |
| `specimen_id` | INTEGER | NOT NULL | 标本唯一标识 |
| `itemid` | INTEGER | NOT NULL | 检验项目标识 |
| `order_provider_id` | VARCHAR(10) | 可空 | 开单医生标识 |
| `charttime` | TIMESTAMP(0) | 可空 | 标本采集时间 |
| `storetime` | TIMESTAMP(0) | 可空 | 结果入库时间 |
| `value` | VARCHAR(200) | 可空 | 检验结果（文本） |
| `valuenum` | DOUBLE PRECISION | 可空 | 检验结果（数值） |
| `valueuom` | VARCHAR(20) | 可空 | 计量单位 |
| `ref_range_lower` | DOUBLE PRECISION | 可空 | 参考范围下限 |
| `ref_range_upper` | DOUBLE PRECISION | 可空 | 参考范围上限 |
| `flag` | VARCHAR(10) | 可空 | 异常标志 |
| `priority` | VARCHAR(7) | 可空 | 检验优先级 |
| `comments` | TEXT | 可空 | 备注信息 |

## 字段详解

### labevent_id
- **含义**: 每行记录的唯一标识
- **用途**: 用于精确定位特定检验结果

### subject_id / hadm_id
- **含义**: 患者和住院标识
- **说明**: `hadm_id` 可能为空，表示门诊检验或无法关联到特定住院

### specimen_id
- **含义**: 标本的唯一标识
- **重要性**: 同一标本可能产生多个检验结果
- **用途**: 用于识别来自同一标本的多项检验（如血气分析的多个指标）

### itemid
- **含义**: 检验项目的标识符
- **关联**: 需要连接 `d_labitems` 表获取项目名称和说明
- **常见项目示例**:
  | itemid | 项目名称 |
  |--------|----------|
  | 50912 | 肌酐 (Creatinine) |
  | 50971 | 钾 (Potassium) |
  | 50983 | 钠 (Sodium) |
  | 51221 | 血红蛋白 (Hemoglobin) |
  | 51222 | 血细胞比容 (Hematocrit) |
  | 51265 | 血小板 (Platelet Count) |
  | 51301 | 白细胞 (White Blood Cells) |

### order_provider_id
- **含义**: 开单医生的匿名标识
- **格式**: 如 "P003AB" 或 "P00102"

### charttime
- **含义**: 标本采集的时间
- **临床意义**: 反映检验结果对应的实际临床时间点
- **ETL映射**: 对应医院LIS系统中的采样时间

### storetime
- **含义**: 检验结果在系统中可用的时间
- **临床意义**: `storetime` - `charttime` 的差值反映检验周转时间
- **用途**: 分析检验及时性

### value / valuenum
- **含义**: 检验结果
- **区别**:
  - `value`: 文本格式的原始结果（如 "Positive", ">100", "5.2"）
  - `valuenum`: 数值格式的结果（便于计算和分析）
- **说明**: 当结果非数值时，`valuenum` 为空

### valueuom
- **含义**: 计量单位
- **常见单位**: mg/dL, mmol/L, g/dL, 10*9/L 等
- **注意**: 单位可能因项目和时间而异，分析时需统一

### ref_range_lower / ref_range_upper
- **含义**: 正常参考范围的上下限
- **用途**: 判断结果是否在正常范围内
- **注意**: 参考范围可能因实验室方法、患者人群等因素而异

### flag
- **含义**: 异常结果标志
- **取值**: `abnormal`（异常）或空
- **判断依据**: 结果是否超出参考范围

### priority
- **含义**: 检验的优先级
- **取值**: `ROUTINE`（常规）, `STAT`（紧急）
- **临床意义**: STAT检验通常要求更快出结果

### comments
- **含义**: 检验相关的备注信息
- **说明**: 已去标识化，`___` 表示信息已被移除

## 外键关系

| 关联表 | 关联字段 | 关系 |
|--------|----------|------|
| patients | subject_id | 多对一 |
| admissions | hadm_id | 多对一 |
| d_labitems | itemid | 多对一 |

## 使用示例

### 查询患者肌酐值

```sql
SELECT
    l.subject_id,
    l.charttime,
    l.valuenum,
    l.valueuom,
    l.flag
FROM labevents l
INNER JOIN d_labitems d ON l.itemid = d.itemid
WHERE d.label = 'Creatinine'
  AND l.subject_id = 12345678
ORDER BY l.charttime;
```

### 统计异常结果比例

```sql
SELECT
    d.label,
    COUNT(*) as total,
    SUM(CASE WHEN l.flag = 'abnormal' THEN 1 ELSE 0 END) as abnormal_count
FROM labevents l
INNER JOIN d_labitems d ON l.itemid = d.itemid
GROUP BY d.label
ORDER BY total DESC;
```

## ETL映射建议

1. **项目映射**: 建立本地检验项目代码到 `itemid` 的映射
2. **单位标准化**: 确保计量单位与MIMIC一致，必要时进行单位换算
3. **标本管理**: 为同一标本的多项检验分配相同的 `specimen_id`
4. **时间处理**:
   - `charttime` 应为标本采集时间
   - `storetime` 应为结果审核/发布时间
5. **参考范围**: 从LIS系统提取各项目的参考范围

## 注意事项

1. **数据量巨大**: 这是MIMIC中最大的表之一，查询时注意性能
2. **单位不一致**: 同一检验项目可能存在多种单位，分析前需标准化
3. **门诊数据**: `hadm_id` 为空的记录可能来自门诊或无法匹配的检验
4. **标本类型**: 同一检验项目在不同标本类型（动脉血、静脉血等）中结果可能不同
5. **重复检验**: 同一时间点可能有多次检验，需要根据研究目的选择处理方式
