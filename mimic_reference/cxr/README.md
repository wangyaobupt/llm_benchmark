# CXR 模块（胸部X线）

## 概述

CXR模块（MIMIC-CXR）包含胸部X线影像数据及相关的元数据。该模块包含约377,110张胸部X线图像，对应227,835个影像学检查。数据来源于贝斯以色列女执事医疗中心。

## 数据组成

CXR模块主要包含以下数据文件：

| 文件名 | 说明 |
|--------|------|
| `cxr-record-list.csv.gz` | 图像记录列表 |
| `cxr-study-list.csv.gz` | 检查记录列表 |
| `cxr-provider-list.csv.gz` | 医疗提供者列表 |
| DICOM影像文件 | 实际的胸部X线图像 |
| 放射学报告 | 对应的文本报告 |

## 核心标识符

| 标识符 | 格式 | 说明 |
|--------|------|------|
| `subject_id` | 8位数字，以1开头 | 患者唯一标识 |
| `study_id` | 8位数字，以5开头 | 影像检查唯一标识 |
| `dicom_id` | 40字符十六进制 | 单张图像唯一标识 |

## 数据文件详解

### cxr-record-list.csv

图像记录列表，将单张DICOM图像映射到检查和患者。

| 字段名 | 数据类型 | 说明 |
|--------|----------|------|
| `dicom_id` | VARCHAR(40) | 图像唯一标识（40字符哈希） |
| `study_id` | INTEGER | 检查唯一标识 |
| `subject_id` | INTEGER | 患者唯一标识 |

### cxr-study-list.csv

检查记录列表，将检查映射到患者。

| 字段名 | 数据类型 | 说明 |
|--------|----------|------|
| `study_id` | INTEGER | 检查唯一标识 |
| `subject_id` | INTEGER | 患者唯一标识 |

### cxr-provider-list.csv

医疗提供者列表，记录每个检查相关的医生信息。

| 字段名 | 数据类型 | 说明 |
|--------|----------|------|
| `study_id` | INTEGER | 检查唯一标识 |
| `ordering` | VARCHAR | 开单医生标识 |
| `attending` | VARCHAR | 主治医生标识 |
| `provider` | VARCHAR | 住院医生标识（如适用） |

## 与其他模块的关联

| 关联模块 | 关联字段 | 说明 |
|----------|----------|------|
| hosp.patients | subject_id | 关联患者基本信息 |
| hosp.admissions | subject_id | 关联住院记录 |
| note.radiology | subject_id | 关联放射学报告 |

## 使用示例

### 查询患者的胸部X线检查

```sql
SELECT
    study_id,
    subject_id
FROM cxr_study_list
WHERE subject_id = 12345678
ORDER BY study_id;
```

### 统计每位患者的检查次数

```sql
SELECT
    subject_id,
    COUNT(DISTINCT study_id) as study_count
FROM cxr_study_list
GROUP BY subject_id
ORDER BY study_count DESC
LIMIT 100;
```

### 关联CXR与放射学报告

```sql
SELECT
    c.subject_id,
    c.study_id,
    r.note_id,
    r.charttime,
    LEFT(r.text, 200) as report_preview
FROM cxr_study_list c
INNER JOIN radiology r ON c.subject_id = r.subject_id
WHERE c.subject_id = 12345678
ORDER BY r.charttime;
```

## 应用场景

### 1. 医学影像AI
- 胸部X线图像分类
- 自动检测异常（如肺炎、气胸）
- 辅助诊断系统开发

### 2. 影像-报告关联研究
- 研究影像特征与报告描述的对应关系
- 训练影像描述生成模型

### 3. 临床研究
- 研究特定疾病的影像学表现
- 追踪疾病进展

## ETL映射建议

1. **标识符关联**: 使用 `subject_id` 和 `study_id` 建立与其他模块的关联
2. **影像存储**: DICOM文件需要专门的存储和处理系统
3. **报告匹配**: 通过时间和患者ID匹配影像与报告

## 注意事项

1. **一检查多图像**: 一次检查（study）可能包含多张图像（如正位片和侧位片）
2. **一检查一报告**: 每次检查只有一份放射学报告
3. **DICOM格式**: 图像以DICOM格式存储，需要专门工具处理
4. **去标识化**: 图像和报告已经去标识化
5. **文件大小**: 完整的影像数据集非常大（约500GB）
6. **与radiology表区别**: CXR模块包含实际影像，而 `radiology` 表仅包含报告文本
