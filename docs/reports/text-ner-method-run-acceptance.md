# Text NER 方法 dry-run 独立验收

结论：**通过**。本报告不包含临床原文。

## 核心计数

| 指标 | 数量 |
|---|---:|
| `calibration_text_units` | 171 |
| `mention_requests` | 171 |
| `relation_requests_pending` | 171 |
| `candidate_annotations` | 0 |
| `evaluation_access_count` | 0 |
| `model_calls` | 0 |

## 自动门禁

| 检查 | 结果 | 观察值 | 期望值 |
|---|---|---|---|
| `manifest_output_hashes` | 通过 | `{}` | `{}` |
| `summary_manifest_reconciliation` | 通过 | `{"candidate_annotations": 0, "mention_requests": 171, "model_calls": 0, "relation_requests_pending": 171, "text_units": 171}` | `{"candidate_annotations": 0, "mention_requests": 171, "model_calls": 0, "relation_requests_pending": 171, "text_units": 171}` |
| `calibration_only` | 通过 | `0` | `0` |
| `request_unit_uniqueness` | 通过 | `0` | `0` |
| `request_text_hashes` | 通过 | `0` | `0` |
| `two_stage_dependency` | 通过 | `{"dependency_errors": 0, "relations": 171}` | `{"dependency_errors": 0, "relations": 171}` |
| `candidate_output_empty` | 通过 | `0` | `0` |
| `human_gold_gate` | 通过 | `{"metrics": null, "status": "not_evaluable"}` | `{"metrics": null, "status": "not_evaluable"}` |
| `evaluation_locked` | 通过 | `0` | `0` |
| `model_calls` | 通过 | `0` | `0` |
| `repeat_run_hashes` | 通过 | `{}` | `{}` |

## 结论边界

- 当前产物是 `exploratory_candidate` 方法请求，不是人工gold。
- relation阶段必须等待mention通过Python校验，不能越过依赖直接运行。
- calibration原文只存在于Git忽略的本地请求目录；聚合报告不保存原文。
- evaluation未读取、模型未调用、性能指标固定为`not_evaluable`。
