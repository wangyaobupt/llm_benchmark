# Text NER 输入准备

本模块只生成可追溯的文本 NER 输入清单，不执行实体识别，也不调用模型或外部 API。

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
