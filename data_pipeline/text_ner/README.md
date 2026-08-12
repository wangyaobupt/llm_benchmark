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

## 本地 A/B 双标与裁决界面

标注界面只监听 `127.0.0.1`，每个进程固定一个角色。A 与 B 的服务只加载各自任务和决定日志；裁决服务只有在同一标注单元的 A/B 决定均已追加后才开放详情。界面不调用模型或外部服务，任务原文和人工结果仍只保存在被 Git 忽略的本地标注包中。

分别启动三个角色（端口可自行调整）：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner.annotation_app `
  data\derived\text_ner_annotation_pilot --role annotator_a --port 8765

.\.venv\Scripts\python.exe -m data_pipeline.text_ner.annotation_app `
  data\derived\text_ner_annotation_pilot --role annotator_b --port 8766

.\.venv\Scripts\python.exe -m data_pipeline.text_ner.annotation_app `
  data\derived\text_ner_annotation_pilot --role adjudicator --port 8767
```

浏览器中的 exact span 会显式转换 JavaScript UTF-16 offset 到 Python Unicode code-point offset，并处理 CRLF/LF 差异；后端在写入前再次核对 surface text、关系 evidence 覆盖、输入哈希和两个 JSON Schema。每次提交生成新的 payload 文件并向角色日志追加一行；修改必须通过 `supersedes_decision_id` 引用旧决定，旧文件不会被覆盖。`blocked_pending_calibration` 状态的 evaluation 任务会返回锁定错误，不能从界面打开。

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
