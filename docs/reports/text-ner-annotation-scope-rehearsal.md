# Text NER 标注范围只读演练

结论：**通过**。真实 pilot 仅用于聚合结构和语言现象覆盖检查；报告不包含原始临床文本，也不构成实体 gold。

## Pilot 范围

| 指标 | 数量 |
|---|---:|
| `pilot_documents` | 200 |
| `pilot_text_units` | 828 |
| `pilot_subjects` | 99 |
| `ed_text_units` | 100 |
| `radiology_text_units` | 728 |
| `minimum_characters` | 3 |
| `median_characters` | 88 |
| `p95_characters` | 665 |
| `maximum_characters` | 2856 |

## 观察到的标注难点

| 现象 | 文本单元数 | 文档数 |
|---|---:|---:|
| `negation` | 278 | 90 |
| `uncertainty` | 75 | 47 |
| `historical_or_comparison` | 105 | 59 |
| `recommendation` | 21 | 15 |
| `measurement` | 100 | 45 |
| `laterality` | 214 | 92 |
| `device` | 77 | 40 |
| `temporal_expression` | 77 | 57 |

## 章节分布（前20）

| section | 数量 |
|---|---:|
| `chief_complaint` | 100 |
| `impression` | 85 |
| `findings` | 78 |
| `comparison` | 77 |
| `indication` | 76 |
| `technique` | 70 |
| `examination` | 53 |
| `dose` | 24 |
| `abdomen` | 12 |
| `history` | 11 |
| `pancreas` | 11 |
| `spleen` | 11 |
| `pelvis` | 10 |
| `lymph_nodes` | 9 |
| `adrenals` | 8 |
| `bones` | 8 |
| `gastrointestinal` | 8 |
| `hepatobiliary` | 8 |
| `reproductive_organs` | 8 |
| `urinary` | 8 |

## 边界与结论

- 词法信号只证明 pilot 中存在否定、不确定、比较、建议、测量、侧别、器械和时间表达等标注场景，不是 NER 结果。
- 九类 mention 和七类显式关系可以表达当前观察到的场景；标准概念映射、事件合并和医学常识推断不属于本层。
- 下一步必须先做人工双标校准并形成裁决 gold；尚未授权本地或外部模型调用。
