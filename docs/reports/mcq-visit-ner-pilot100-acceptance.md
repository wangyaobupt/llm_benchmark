# 出题 Visit NER 试点验收（100 例）

> 日期：2026-08-20  
> 管道：`mcq-visit-ner/1.0.0`  
> 模型：`openai-compatible/deepseek-v4-flash`  
> 状态：`exploratory_unreviewed`；`gold = 0`  
> 输入：冻结 `data/derived/mcq_visit_extract/random10k_dev20/visits.json`（只读，前 100 例）  
> 产物：`data/derived/mcq_visit_ner/pilot100_v1.0.0/mention_results.jsonl`  
> 本文件不含病历原文、不含 `hadm_id` 清单。机器指标：同名 `.json`。

## 结论

试点 **100 例、438 个出院小结切块全部完成**（失败 0）。已发布 mention 的 `surface_text` 与源切片 **100% 一致**（偏移由 Python 接地，不是模型给的）。未改写抽取文件，未改写 DS 正文。

可以当作全量 NER 的流程验收通过，**不能当 gold，不能当标准答案键**。模型仍有约两成提议无法接地被丢弃；每例 mention 密度偏高，出题前需要抽查。

## 计数

| 指标 | 值 |
|---|---:|
| 住院 / 唯一 hadm | 100 / 100 |
| 切块（`discharge_note_full`） | 438 |
| 切块有结果 / 失败 | 438 / 0 |
| 已接地 mention | 20,213 |
| 模型提议未接地而丢弃 | 4,904（约 19.5%） |
| 零 mention 切块 | 2 |
| 每例 mention 中位数（min–max） | 188（34–461） |
| 每切块 mention 中位数（min–max） | 44（0–152） |
| 住院级同 span+类型重复 | 667（3.3%；切块重叠 200 字） |
| prompt / completion tokens | 716,239 / 742,619 |
| 模型调用（含重试） | 444（6 个切块重试） |
| 墙钟（首末 `recorded_at_utc`） | 1.86 h |
| `mention_results.jsonl` | 6.09 MiB |

SHA-256：`F0380A773481A59B92032621418F256BA26C7082653AA6862EA972BEF9313851`。

## 类型与属性

| entity_type | n |
|---|---:|
| clinical_problem | 4,466 |
| measurement | 4,418 |
| symptom_or_sign | 3,062 |
| physical_exam_finding | 2,376 |
| medication_or_substance | 2,164 |
| procedure_or_test | 1,343 |
| imaging_finding | 1,296 |
| anatomical_site | 725 |
| device | 310 |
| temporal_expression | 53 |

断言：present 16,696 / absent 2,871 / possible 636 / unknown 10。否定没有被丢掉。时间：current 14,858 / historical 4,773 / future_planned 578。体验者几乎都是 patient（20,076），亲属 136。

词汇表外的 `entity_type` / `assertion`：0。裸形容词停用表命中：0。已发布 mention 切片与 `chunk_text` 不一致：0。`chunk_text_sha256` 与 `documents.jsonl` 不一致：0。

## 质量观察

1. **接地闸门有效。** 约 19.5% 模型 `surface_text` 不是原文子串，Python 丢弃。这是合同行为，不是漏写文件。全量时仍会有同样损耗。
2. **密度偏高。** 中位 188 mention/住院、测量类 44/例，容易把化验数值、短缩写（`cp`/`dm`/`pe`）都标上。出题前要抽查，不能按条数当覆盖成绩。
3. **切块重叠。** 重叠区约 2,311 条 mention 会在相邻切块再出现；`compile` 按 span+类型去重后约剩 3.3% 住院级重复。全量先 `compile` 再并回 visit。
4. **时间表达式偏少**（53）。叙事里的 “3 days ago / on HD2” 可能没抽全。
5. 无 `mention_failures.jsonl`。抽取目录未被写入。

## 全量建议

- 流程可放大；并行用 `--workers 8 --requests-per-minute 60`，新 `output-dir`。
- 仍读冻结 `visits.json`，不要读 times 补丁当 NER 原文。
- 非正式金标准。`compile` 之后再按 `hadm_id` 并到 `random10k_dev20_times`。
