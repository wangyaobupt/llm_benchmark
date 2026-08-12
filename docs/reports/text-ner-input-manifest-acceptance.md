# Text NER 输入清单独立验收

结论：**通过**。本阶段只生成可追溯输入清单，模型调用次数为 0。

## 核心计数

| 指标 | 数量 |
|---|---:|
| `manifest_rows` | 2812 |
| `included_text_units` | 2724 |
| `excluded_documents` | 88 |
| `ed_chief_complaint_documents` | 100 |
| `radiology_documents` | 443 |
| `discharge_documents_excluded` | 88 |
| `pilot_documents` | 200 |
| `pilot_subjects` | 99 |
| `model_calls` | 0 |

## 自动门禁

| 检查 | 结果 | 观察值 | 期望值 |
|---|---|---|---|
| `arrow_schema` | 通过 | `"{b'schema': b'text-ner-input-manifest/1.0.0'}"` | `"{b'schema': b'text-ner-input-manifest/1.0.0'}"` |
| `schema_version` | 通过 | `["text-ner-input-manifest/1.0.0"]` | `["text-ner-input-manifest/1.0.0"]` |
| `raw_text_columns_absent` | 通过 | `[]` | `[]` |
| `manifest_row_ids_unique` | 通过 | `0` | `0` |
| `source_hash_and_locator` | 通过 | `0` | `0` |
| `included_spans_exact` | 通过 | `0` | `0` |
| `section_coverage_exact` | 通过 | `0` | `0` |
| `source_document_reconciliation` | 通过 | `0` | `0` |
| `time_policy` | 通过 | `0` | `0` |
| `post_hoc_exclusion` | 通过 | `0` | `0` |
| `pilot_document_count` | 通过 | `200` | `200` |
| `pilot_source_balance` | 通过 | `{"ed.triage": 100, "note.radiology": 100}` | `{"ed.triage": 100, "note.radiology": 100}` |
| `model_calls` | 通过 | `{"run": 0, "summary": 0}` | `{"run": 0, "summary": 0}` |
| `input_hash` | 通过 | `"e864e858c7352bedd12fc4a704e52965d77d1c9d28a7e393b841d6a21a3a928e"` | `"e864e858c7352bedd12fc4a704e52965d77d1c9d28a7e393b841d6a21a3a928e"` |
| `repeat_run_hashes` | 通过 | `{"run_manifest.json": "521528981bcf5ca676efad04f90a16ccc06dd46606f9e2f01314a781d1ebe9aa", "text_ner_input_manifest.parquet": "7dc5106214da7becbf2a9409cf5a1766996262a3e03179b8580a731cb1eab4e1", "text_ner_input_manifest_summary.json": "9137593d8e25d8e031720d847581196cc472aec09da212cf9df98d2770e9b5e4"}` | `"identical to primary run"` |

## 边界

- 清单不保存原始临床文本，只保存来源定位、字符 span 和 SHA-256。
- ED chief complaint 的可用时间保持未知，不使用 ED 入科时间替代。
- discharge summary 全部以 `POST_HOC_DISCHARGE` 排除。
- 本验收不证明任何 NER 模型质量，也不授权模型调用。
