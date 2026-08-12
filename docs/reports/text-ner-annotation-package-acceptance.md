# Text NER 人工标注包独立验收

结论：**通过**。标注包仅保存在 `data/derived/`，模型调用次数为0。

## 核心计数

| 指标 | 数量 |
|---|---:|
| `pilot_documents` | 200 |
| `calibration_documents` | 50 |
| `evaluation_documents` | 150 |
| `calibration_subjects` | 24 |
| `evaluation_subjects` | 75 |
| `annotator_a_text_units` | 171 |
| `annotator_b_text_units` | 171 |
| `evaluation_locked_text_units` | 657 |
| `model_calls` | 0 |

## 自动门禁

| 检查 | 结果 | 观察值 | 期望值 |
|---|---|---|---|
| `allocation_arrow_schema` | 通过 | `"{b'schema': b'annotation-allocation/1.0.0'}"` | `"{b'schema': b'annotation-allocation/1.0.0'}"` |
| `pilot_document_reconciliation` | 通过 | `{"documents": 200, "duplicates": 0}` | `{"documents": 200, "duplicates": 0}` |
| `exact_partition_sizes` | 通过 | `{"calibration": 50, "evaluation": 150}` | `{"calibration": 50, "evaluation": 150}` |
| `patient_isolation` | 通过 | `0` | `0` |
| `calibration_source_balance` | 通过 | `{"ed.triage": 25, "note.radiology": 25}` | `{"ed.triage": 25, "note.radiology": 25}` |
| `calibration_stratum_coverage` | 通过 | `["radiology:AR:768_2047:full_report", "radiology:AR:lt256:full_report", "radiology:RR:256_767:full_report", "radiology:RR:256_767:sectioned", "radiology:RR:768_2047:full_report", "radiology:RR:768_2047:sectioned", "radiology:RR:ge2048:sectioned", "radiology:RR:lt256:full_report", "radiology:RR:lt256:sectioned"]` | `["radiology:AR:768_2047:full_report", "radiology:AR:lt256:full_report", "radiology:RR:256_767:full_report", "radiology:RR:256_767:sectioned", "radiology:RR:768_2047:full_report", "radiology:RR:768_2047:sectioned", "radiology:RR:ge2048:sectioned", "radiology:RR:lt256:full_report", "radiology:RR:lt256:sectioned"]` |
| `annotator_task_sets_equal` | 通过 | `0` | `0` |
| `annotator_task_orders_blinded` | 通过 | `false` | `false` |
| `task_document_allocation` | 通过 | `{"a_mismatch": 0, "b_mismatch": 0, "evaluation_mismatch": 0}` | `{"a_mismatch": 0, "b_mismatch": 0, "evaluation_mismatch": 0}` |
| `direct_patient_identifiers_absent_from_tasks` | 通过 | `[]` | `[]` |
| `evaluation_locked` | 通过 | `0` | `0` |
| `task_schema_and_text_hash` | 通过 | `0` | `0` |
| `task_unit_reconciliation` | 通过 | `{"a": 171, "b": 171, "cross_partition": 0, "evaluation": 657}` | `{"a": 171, "b": 171, "cross_partition": 0, "evaluation": 657}` |
| `decision_schema_examples` | 通过 | `0` | `0` |
| `decision_logs_initialized_empty` | 通过 | `{"adjudication": 0, "annotator_a": 0, "annotator_b": 0}` | `{"adjudication": 0, "annotator_a": 0, "annotator_b": 0}` |
| `run_output_hashes` | 通过 | `0` | `0` |
| `model_calls` | 通过 | `{"run": 0, "summary": 0}` | `{"run": 0, "summary": 0}` |
| `repeat_run_hashes` | 通过 | `{"allocation/annotation_allocation.parquet": "d570799fe279523b1d82ff94645b8f579d233cd6d187119a696b435e3c7005bc", "allocation/annotation_package_summary.json": "e5a21200424aacf8c712dc394556cd253ce506704d60815682e85db6178273ec", "calibration/annotator_a/tasks.jsonl": "78010c9fd14781adbc9eb2f3dab8c75e7af01f4c521a61f57adacd8de789d793", "calibration/annotator_b/tasks.jsonl": "0946c188f16c8a76a6020391e411bbb2b414eca702c37b19cbce7a821ba23072", "decisions/adjudication.jsonl": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "decisions/annotator_a.jsonl": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "decisions/annotator_b.jsonl": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "evaluation/tasks.locked.jsonl": "f57f39cfd0199a37d0e58117d341a253c18b502e6596b54e89d05b1e2a25e5ce", "run_manifest.json": "0db12a62bb8b987c289fb32270dba47b30326b50e8991afbd62f4705750dbc46"}` | `"identical to primary run"` |

## 边界

- A/B calibration任务集合一致、顺序不同，双方均看不到对方结果。
- evaluation包已生成但状态固定为 `blocked_pending_calibration`，不能提前标注或用于模型评测。
- 原始临床文本仅存在于被Git忽略的本地任务文件；Git报告只有聚合计数和文件哈希。
- 决策和裁决记录采用追加式Schema，第三方裁决必须引用至少两条输入决定，不覆盖A/B原始记录。
