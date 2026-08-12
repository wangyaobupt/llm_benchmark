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
