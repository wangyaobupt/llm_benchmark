# mcq_visit_ner

对冻结的 visit 抽取 `visits.json` 做出院小结 span NER。另开输出目录，不覆盖抽取文件，不改写 DS/HPI 正文。非正式 gold。

本模块不是 `text_ner_v2`：不读事件聚合 Parquet，只读五类题型 visit 行文件。模型只返回 `surface_text` 与属性；字符偏移在 Python 里接地（精确匹配，否则大小写/空白折叠）。未接地的 mention 丢弃。

默认空跑（`prepare`）。真正把受限 MIMIC 文本发到外部 API 必须同时满足：

1. `--execute`
2. `--confirm-data-transfer-authorized`
3. 本地环境 `MCQ_VISIT_NER_EXTERNAL_API_APPROVED=YES`

API Key **只写本地 `.env`，不要贴到聊天、issue 或提交。**

计划：[`docs/design/20260820_出题Visit出院小结NER计划-DeepSeek-v4-flash.md`](../../docs/design/20260820_出题Visit出院小结NER计划-DeepSeek-v4-flash.md)

## 凭据

复制 `config/mcq_visit_ner/openai-compatible.env.example` 到仓库根 `.env`（或单独文件，用 `--env-file`）：

```
MCQ_VISIT_NER_API_KEY=
MCQ_VISIT_NER_BASE_URL=https://www.dmxapi.cn/v1
MCQ_VISIT_NER_MODEL=deepseek-v4-flash
MCQ_VISIT_NER_MODEL_VERSION=DeepSeek-V4-Flash
MCQ_VISIT_NER_PROVIDER=openai-compatible
MCQ_VISIT_NER_EXTERNAL_API_APPROVED=
```

不要复用 `TEXT_NER_*`。`text_ner` 的 DeepSeek 官方适配器对 `restricted_mimic` 硬阻断；本模块走通用 OpenAI 兼容端点，因此用单独闸门。

## 命令

先切 100 例试点，不要直接对 10,000 例调用外部 API。

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_ner prepare `
  --input data\derived\mcq_visit_extract\random10k_dev20\visits.json `
  --output-dir data\derived\mcq_visit_ner\pilot100_v1.0.0 `
  --max-visits 100
```

`prepare` 只写 `documents.jsonl`（含病历原文，仅本地 `data/`）。同一 `--output-dir` 再跑会续上；身份（输入指纹、字段、切块、prompt、max-visits）不一致则拒绝。

确认 `status` 后，才允许执行（会外传 MIMIC 文本）：

```powershell
$env:MCQ_VISIT_NER_EXTERNAL_API_APPROVED = "YES"
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_ner run `
  --output-dir data\derived\mcq_visit_ner\pilot100_v1.0.0 `
  --env-file .env `
  --execute `
  --confirm-data-transfer-authorized
```

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_ner status --output-dir data\derived\mcq_visit_ner\pilot100_v1.0.0
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_ner compile --output-dir data\derived\mcq_visit_ner\pilot100_v1.0.0
```

`compile` 写出 `visit_mentions.jsonl`（按住院合并、已接地）。不改 `visits.json`。标准化实体名是后续步骤，用已审核同义词表映射 `surface_text`，本模块不做。

若 `prepare` 时未加 `--max-visits`，`run` 必须再加 `--all-visits`，避免误发全量。

## 全量并行

试点 100 例串行约 2.5 小时，瓶颈是接口等待（约 20 秒/切块），不是本机 CPU/内存。全量约 4.4 万切块，串行约 10 天；8 路并发大约一天多。本机 16 核 / 32 GB，8 个 HTTP worker 几乎不占内存。网关并发上限不明，先 8 路；若大量 `429` 降到 4。

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_ner prepare `
  --input data\derived\mcq_visit_extract\random10k_dev20\visits.json `
  --output-dir data\derived\mcq_visit_ner\random10k_v1.0.0 `
  --max-visits 10000

$env:MCQ_VISIT_NER_EXTERNAL_API_APPROVED = "YES"
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_ner run `
  --output-dir data\derived\mcq_visit_ner\random10k_v1.0.0 `
  --env-file .env `
  --execute `
  --confirm-data-transfer-authorized `
  --all-visits `
  --workers 8 `
  --requests-per-minute 60
```

`--workers 1` 仍是默认（与试点一致）。可断点续跑；不要写进冻结抽取目录。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests.test_mcq_visit_ner
```
