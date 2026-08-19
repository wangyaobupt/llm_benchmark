# Text NER v2 运行手册

本手册对应 `data_pipeline/text_ner_v2`：一个从头重写、刻意简化的两阶段临床实体识别与关系抽取管线。它读取已验收的 `event_pipeline_output/aggregation`，通过 OpenAI-compatible Chat Completions API（DeepSeek，凭据来自仓库根目录 `.env`）抽取实体 mention 与显式文本关系，并编译出带确定性字符 span 的实体/关系 sidecar。

## 为什么重做

旧版（`data_pipeline/text_ner`）在真实 smoke 运行中暴露了两类阻断性问题：

1. **`MENTION_SURFACE_MISMATCH` 循环重试**：旧版要求模型自己输出零基 Unicode 字符偏移，模型经常数错，导致反复重试并最终 `identical_invalid_content` 终止。
2. **`GENERIC_API_OUTPUT_TRUNCATED` 无限递归分块**：密集段落即使切到 1.4k 字符仍超过输出上限，旧版的递归二分把单个文本单元拖入大量重试。

v2 的核心改动：模型只输出 `surface_text`（逐字原文子串）与属性，**字符 offset 由 Python 确定性回填**（先精确匹配、再 casefold + 空白折叠；歧义或缺失则丢弃该条，不触发整单元重试）。关系阶段模型只引用已回填的 mention `local_id`，evidence span 由 Python 计算为覆盖两个端点的最小连续区间。长文本在首次调用前就按自然边界确定性分块，不做无界递归拆分。每个阶段都是可断点续跑的追加式 JSONL checkpoint。

## 运行前边界

- API key 只放在 Git 忽略的 `.env`（或进程环境变量）中，不写入代码、日志或产物。
- 输出目录 `data/ner_v2_v2` 含受限临床文本与模型输出，已由 `data/` 忽略规则排除出 Git。
- 向外部服务发送 MIMIC 派生文本需操作者自行确认满足 PhysioNet 与机构数据政策；本工具只负责技术执行，不代替合规判断。
- 所有模型输出在人工验收前均为 `unreviewed_model_output`，不能称为 gold 或验证过的实验结果。

## 快速开始

```powershell
Set-Location 'D:\Projects\llm_benchmark'

# 只读预检（不调用 API）
& '.\scripts\Run-TextNerV2.ps1' -ValidateOnly

# 端到端小批（每种来源 4 条，约 20 个文档）
& '.\scripts\Run-TextNerV2.ps1' -Stage all -SamplePerSource 4
```

## 四个阶段（可分别运行/续跑）

```powershell
# 1) 从 aggregation 构建分块文档（一次性，约 1 分钟）
.\scripts\Run-TextNerV2.ps1 -Stage prepare

# 2) mention 实体识别（断点续跑：已完成的 doc 会自动跳过）
.\scripts\Run-TextNerV2.ps1 -Stage mentions

# 3) 关系抽取（只处理 mention>=2 的文档）
.\scripts\Run-TextNerV2.ps1 -Stage relations

# 4) 编译实体/关系 sidecar
.\scripts\Run-TextNerV2.ps1 -Stage compile

# 查看进度
.\scripts\Run-TextNerV2.ps1 -Stage status
```

底层命令等价形式（以 mention 为例；脚本会自动优先用 `uv run`，不可用时回退到 venv python）：

```powershell
uv run --no-sync python -m data_pipeline.text_ner_v2 run-mentions `
  data\ner_v2_v2 `
  --env-file .env `
  --mention-prompt config\text_ner\prompts\ner-v2-mentions.md `
  --requests-per-minute 30
```

中断后原命令重跑即可续跑；`Ctrl+C` 会保留已落盘的 checkpoint。只重跑失败文档：

```powershell
.\scripts\Run-TextNerV2.ps1 -Stage mentions -RetryFailed
```

## 运行器说明（双进程现象的来源）

`scripts\Run-TextNerV2.ps1` 优先通过 `uv run --no-sync python` 启动解释器；当 `uv` 不在 PATH 或无法初始化缓存时，回退到 `.venv\Scripts\python.exe`。

注意：`.venv` 由 uv 创建，`.venv\Scripts\python.exe` 是 uv 的 Windows redirector（约 274KB，venv 内没有 `python312.dll`）。它每次会拉起真正的解释器 `C:\Python312\python.exe` 干活并 `WaitForSingleObject`，因此任务管理器里会同时出现一个"等待中的 venv 进程（0 CPU、约 5MB）"和一个"活跃的 C:\Python312 进程"。这是 Windows 上 uv venv 的标准行为，不是双执行、不是泄漏：任务只执行一次，两个进程在任务结束时一起退出。

## 产物

```text
data/ner_v2_v2/
  documents.parquet          分块文档（含全局 offset 与来源元数据）
  documents_summary.json
  mention_results.jsonl      mention checkpoint（每文档一行，含回填后的 mention）
  mention_failures.jsonl     失败文档
  relation_results.jsonl     关系 checkpoint
  relation_failures.jsonl
  sidecars/
    entity_mentions.parquet  实体 + 属性 + 精确 span + 来源
    text_relations.parquet   显式关系 + evidence span
  compile_summary.json
  review/
    entity_mentions.csv      实体验收表（Excel 可开）
    text_relations.csv       关系验收表
    preview.md               每来源一个文档的全文对照预览
```

## 规模与速率

- 文档 37,790，mention 分块 41,902（短注释 1 块，出院小结/影像报告按 3000 字符确定性分块）。
- 默认 30 请求/分钟。仅 mention 阶段理论下限约 23 小时，关系阶段另计；总时长取决于服务端延迟与重试。
- 修改 `-RequestsPerMinute` 前先确认服务商限流与预算。估算成本与 token 可通过各阶段 JSON 摘要的 `usage` 字段累计。

## 关键配置

- 凭据：`.env` 的 `TEXT_NER_*` 五键（与旧版同名，可直接复用）。
- 分块：`--max-chunk-chars`（默认 3000）、`--overlap-chars`（默认 200），见 `prepare`。
- 输出上限：mention `--max-tokens`（默认 6000）、relation（默认 8000）。
- 重试：`--maximum-retries`（默认 3）；空内容/非法 JSON/截断会附加不含临床文本的纠错指令后重试。
- 提示词：`config/text_ner/prompts/ner-v2-mentions.md`、`ner-v2-relations.md`。
