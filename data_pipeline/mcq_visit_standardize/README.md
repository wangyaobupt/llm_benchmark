# mcq_visit_standardize

对 `mcq_visit_extract` 的 visit 行文件做确定性术语/单位/主诉症状统一。不覆盖抽取文件，不改写 HPI 与出院小结正文。非正式 gold。

计划：[`docs/design/20260820_出题Visit标准化计划-术语单位症状.md`](../../docs/design/20260820_出题Visit标准化计划-术语单位症状.md)

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_standardize `
  --input data\derived\mcq_visit_extract\pilot100_dev20\visits.json `
  --output-dir data\derived\mcq_visit_standardize\pilot100_dev20_v1.0.0 `
  --expected-count 100
```

## 审核界面（原文 → 建议 → 你确认或改成 xx）

先生成建议，再打开页面。默认 http://127.0.0.1:8767/ 。页面展示原文和自动建议；你点「确认建议」，或改成 xx 后再确认。也可审影像检查名、化验名称/单位。

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_standardize.propose
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_standardize.review_app --open-browser
```

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_standardize.review_app `
  --open-browser
```

结果统计与可视化（无病历原文）：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_standardize.dashboard --open-browser
```

产物：`docs/reports/mcq-visit-standardize-random10k-dashboard.html`。

出院小结 NER 是另开模块，不在本层调用 LLM：`python -m data_pipeline.mcq_visit_ner`。

审完后重新标准化（换新输出目录，并传入同义词表）：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_standardize `
  --input data\derived\mcq_visit_extract\random10k_dev20\visits.json `
  --output-dir data\derived\mcq_visit_standardize\random10k_dev20_v1.0.9 `
  --expected-count 10000 `
  --synonym-table data\derived\mcq_visit_standardize\reviewed_synonyms.jsonl
```

