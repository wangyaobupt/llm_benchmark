# Text NER 输入准备

本模块只生成可追溯的文本 NER 输入清单，不执行实体识别，也不调用模型或外部 API。

当前同时冻结了 section 标注响应、mention sidecar 和显式关系 sidecar 的首版合同：

- `schemas/section-annotation.schema.json`
- `annotation_contracts.py`
- `annotation_validation.py`

标注规则见 `docs/design/text-ner-entity-annotation-protocol.md`。

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner prepare `
  data\mimic-admission-raw-coronary-all-three-modules-random-100.jsonl `
  --output-dir data\derived\text_ner_sample_100 `
  --pilot-size 200
```

输入规则：

- 纳入 ED `triage.chiefcomplaint`，但保留 `available_time=null`。
- 纳入 radiology，并以 `storetime` 作为可用时间。
- discharge summary 记录为 `POST_HOC_DISCHARGE`，不进入 NER。
- 原始文本不写入 Parquet，只记录来源、字符 span、字符数和 SHA-256。
- pilot 是人工审核样本，不创建 train/dev/test 数据划分；`split_group_id=subject_id` 为后续患者级划分提供稳定分组键。

独立验收：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner audit `
  data\mimic-admission-raw-coronary-all-three-modules-random-100.jsonl `
  data\derived\text_ner_sample_100 `
  --replay-directory data\derived\text_ner_sample_100_replay `
  --output-json docs\reports\text-ner-input-manifest-acceptance.json `
  --output-markdown docs\reports\text-ner-input-manifest-acceptance.md
```

对真实 pilot 做只输出聚合计数的标注范围演练：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner rehearse-scope `
  data\mimic-admission-raw-coronary-all-three-modules-random-100.jsonl `
  data\derived\text_ner_sample_100\text_ner_input_manifest.parquet `
  --expected-pilot-documents 200 `
  --output-json docs\reports\text-ner-annotation-scope-rehearsal.json `
  --output-markdown docs\reports\text-ner-annotation-scope-rehearsal.md
```

该命令读取真实 section 来统计否定、不确定、比较、建议、测量、侧别、器械和时间表达覆盖，但不会在报告中保存原文，也不会生成实体或调用模型。

生成患者隔离的人工双标包：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner prepare-annotation-package `
  data\mimic-admission-raw-coronary-all-three-modules-random-100.jsonl `
  data\derived\text_ner_sample_100\text_ner_input_manifest.parquet `
  --output-dir data\derived\text_ner_annotation_pilot `
  --calibration-documents 50
```

生成结果：

- `allocation/annotation_allocation.parquet`：200份文档的患者级分配。
- `calibration/annotator_a/tasks.jsonl`、`annotator_b/tasks.jsonl`：相同任务集合、不同确定性顺序。
- `evaluation/tasks.locked.jsonl`：状态为 `blocked_pending_calibration`，不得在calibration门禁通过前使用。
- `annotations/annotator_a|annotator_b|adjudicated/`：标注响应文件目录。
- `decisions/annotator_a.jsonl`、`annotator_b.jsonl`、`adjudication.jsonl`：追加式决定日志，初始为空。

任务文件包含受限MIMIC原文，只能保留在被Git忽略的`data/derived/`。A/B提交时分别把每个任务中的空白`annotation`填写后另存到自己的`annotations/`目录，再按`annotation-review-decision.schema.json`向自己的决定日志追加记录。裁决者只能在A/B均提交后工作，并在裁决日志中引用双方`decision_id`；不得覆盖原始决定。

独立验收：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner audit-annotation-package `
  data\derived\text_ner_annotation_pilot `
  --replay-directory data\derived\text_ner_annotation_pilot_replay `
  --output-json docs\reports\text-ner-annotation-package-acceptance.json `
  --output-markdown docs\reports\text-ner-annotation-package-acceptance.md
```
