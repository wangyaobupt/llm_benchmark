# mcq_visit_ner

对冻结的 visit 抽取 `visits.json` 做出院小结残余 span NER。另开输出目录，不覆盖抽取文件，不改写 DS/HPI 正文。非正式 gold。

本模块不是 `text_ner_v2`：不读事件聚合 Parquet，只读五类题型 visit 行文件。`prepare` 先从同一 visit 的结构化字段收集主诉、诊断、检查、检验、药物、操作等已知 surface，在叙事文本中本地定位并替换为短标记 `[S]`；模型只提取标记以外的新内容。模型返回 `surface_text` 与属性；字符偏移仍在未改写的原文中由 Python 接地。与已知 span 重叠或未接地的 mention 丢弃。

这不是只靠提示词排重：已结构化内容在 API 请求前已经被本地掩码。完全由结构化内容组成的切块直接写空结果，不调用模型。`documents.jsonl` 同时保留原始 `chunk_text` 和实际发送的 `model_text`，便于审计；两者都只保存在本地 `data/`。

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

`prepare` 输出以下成本指标：`known_spans`、`source_chars`、`model_chars`、`model_char_reduction_rate`、`skipped_chunks` 和 `api_candidate_chunks`。实际账单以 `run` 返回的 token usage 为准。

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

`compile` 写出 `visit_mentions.jsonl`（按住院合并、已接地、已排除结构化字段精确重复）。不改 `visits.json`。标准化实体名是后续步骤，用已审核同义词表映射 `surface_text`，本模块不做。

## 10 例残余 NER 验证

同一批 10 例、30 个切块与旧版全量 NER 对比：

| 指标 | 旧版全量 NER | 残余 NER | 变化 |
|---|---:|---:|---:|
| Prompt tokens | 48,541 | 45,025 | -7.24% |
| Completion tokens | 51,526 | 23,449 | -54.49% |
| Total tokens | 100,067 | 68,474 | -31.57% |
| 模型返回 mentions | 1,358 | 549 | -59.57% |

残余 NER 编译后为 540 个 mentions；与 visit 结构化字段的精确 surface 重复为 0，`[S]` 被提取为实体的数量为 0。该结果仍为 `exploratory_unreviewed`，不代表临床完整性通过。

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
