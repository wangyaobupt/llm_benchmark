# Text NER API 配置与运行手册

本文说明如何从已经生成的1000例 aggregation 开始，配置一个 OpenAI-compatible API，依次完成 mention 实体识别、relation 关系抽取和最终 sidecar 编译。

当前正式输入为：

```text
data/test_1000_0812/event_pipeline_output/aggregation
```

当前请求规模为64,509个文本单元。所有模型输出在人工验收前均为 `unreviewed_model_output`，不能称为 gold 或经过验证的实验结果。

## 1. 运行前边界

- API key 只放在 Git 忽略的本地 `.env` 或当前进程环境变量中，不写入代码、日志、运行产物或 Git。`.env` 是本地明文凭据文件，应限制访问权限。
- `data/test_1000_0812/event_pipeline_output/NER` 含受限临床原文和模型输出，必须继续由 Git 忽略。
- `--confirm-data-transfer-authorized` 只表示操作者明确发起外部传输，不证明第三方服务满足 MIMIC 或机构数据政策。
- 本地服务使用 `--endpoint-scope local`，且 URL 必须是 `localhost`、`127.0.0.1` 或 `::1`。
- 外部服务使用 `--endpoint-scope external --confirm-data-transfer-authorized`。

## 2. 打开 PowerShell 并设置路径

```powershell
Set-Location 'D:\Projects\llm_benchmark'

$pythonPath = '.\.venv\Scripts\python.exe'
$nerRoot = 'data\test_1000_0812\event_pipeline_output\NER'
$aggregationRoot = 'data\test_1000_0812\event_pipeline_output\aggregation'
$apiConfig = 'config\text_ner\openai-compatible-api.json'
$envFile = '.env'
$executionRoot = "$nerRoot\model_execution"
```

API 命令通过 `--env-file $envFile` 读取配置。程序不会执行文件内容，只接受 UTF-8 `KEY=VALUE`、空行和 `#` 注释；也不会在未传参数时隐式搜索当前目录。若同名进程环境变量存在，它会覆盖文件值。

## 3. 确认输入和请求包

当前仓库已经生成了正式请求包。先检查关键文件：

```powershell
$requiredFiles = @(
  "$aggregationRoot\aggregation_manifest.json",
  "$aggregationRoot\quality_report.json",
  "$nerRoot\input\text_ner_input_manifest.parquet",
  "$nerRoot\extraction_interface\requests\mention_requests.jsonl",
  "$nerRoot\extraction_interface\configuration\prompts\mentions.md",
  "$nerRoot\extraction_interface\configuration\prompts\relations.md"
)

$missingFiles = $requiredFiles | Where-Object { -not (Test-Path -LiteralPath $_) }
if ($missingFiles) {
  throw "NER input is incomplete: $($missingFiles -join ', ')"
}
```

如果需要从 aggregation 重新生成，应使用下面两条命令。输出目录必须不存在，工具不会覆盖既有运行：

```powershell
& $pythonPath -m data_pipeline.text_ner prepare-aggregation-manifest `
  $aggregationRoot `
  'config\text_ner\all-free-text-sources.json' `
  --output-dir "$nerRoot\input"

& $pythonPath -m data_pipeline.text_ner prepare-full-extraction `
  $aggregationRoot `
  "$nerRoot\input\text_ner_input_manifest.parquet" `
  --mention-prompt 'config\text_ner\prompts\two-stage-mentions.md' `
  --relation-prompt 'config\text_ner\prompts\two-stage-relations.md' `
  --output-dir "$nerRoot\extraction_interface"
```

## 4. 配置 DeepSeek

截至2026年8月15日，DeepSeek 官方 OpenAI-compatible base URL 为 `https://api.deepseek.com`；正式模型名为 `deepseek-v4-flash` 和 `deepseek-v4-pro`。旧的 `deepseek-chat` 与 `deepseek-reasoner` 已在2026年7月24日后进入停用范围，因此本手册不再使用旧名称。参考：[模型与价格](https://api-docs.deepseek.com/quick_start/pricing)、[更新日志](https://api-docs.deepseek.com/updates/)。

成本优先时，在仓库根目录创建或编辑 `.env`：

```dotenv
TEXT_NER_API_KEY=填写真实API-key
TEXT_NER_BASE_URL=https://api.deepseek.com
TEXT_NER_MODEL=deepseek-v4-flash
TEXT_NER_MODEL_VERSION=DeepSeek-V4-Flash
TEXT_NER_PROVIDER=deepseek
```

仓库已提供 NER 专用模板 `config\text_ner\openai-compatible-api.env.example`；新环境可复制为根目录 `.env` 后填写 key。当前本地 `.env` 已创建并由 `.gitignore` 排除。根目录 `.env.example` 是多个子系统共用的变量总览，不能整体传给这个严格接口。`.txt` 扩展名也可使用，例如 `--env-file api-settings.txt`；推荐 `.env`，因为忽略规则和用途更明确。

```powershell
if (-not (Test-Path -LiteralPath '.env')) {
  Copy-Item -LiteralPath 'config\text_ner\openai-compatible-api.env.example' -Destination '.env'
}
notepad.exe '.env'
```

`TEXT_NER_MODEL_VERSION` 是写入本地 provenance 的标签，不会发送给 API，也不能单独证明远端权重完全不可变。若服务商提供不可变 revision，应把该 revision 填入此变量。

当前接口会发送 `response_format={"type":"json_object"}`。DeepSeek 官方要求提示词同时明确要求 JSON；本项目的 mention 和 relation prompt 已满足这一点。参考：[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)。

如果不希望把 key 保存到磁盘，可只覆盖 `.env` 中的空 key：

```powershell
$secureApiKey = Read-Host 'API key' -AsSecureString
$env:TEXT_NER_API_KEY = [System.Net.NetworkCredential]::new('', $secureApiKey).Password
```

进程环境变量会覆盖 `.env` 中的空值。不要把真实 key 写入脚本或 `.env.example`。

## 5. 配置其他 OpenAI-compatible API

外部服务 `.env` 模板：

```dotenv
TEXT_NER_API_KEY=填写真实API-key
TEXT_NER_BASE_URL=https://provider.example/v1
TEXT_NER_MODEL=provider-model-id
TEXT_NER_MODEL_VERSION=immutable-model-revision
TEXT_NER_PROVIDER=provider-name
```

程序会在 base URL 后追加 `/chat/completions`。因此 base URL 应停在服务商的 API 根路径，不要自行追加 `/chat/completions`。

本地服务 `.env` 模板：

```dotenv
TEXT_NER_API_KEY=local-placeholder
TEXT_NER_BASE_URL=http://127.0.0.1:8000/v1
TEXT_NER_MODEL=local-model-id
TEXT_NER_MODEL_VERSION=local-checkpoint-sha256-or-revision
TEXT_NER_PROVIDER=local-openai-compatible
```

兼容服务必须支持 Chat Completions、system/user messages、`max_tokens`，并返回 `choices[0].message.content`。默认配置还要求支持 JSON object response format；如果服务不支持，不能直接运行当前配置，应先修改并重新验收该提供商配置。

## 6. 不泄露 key 的配置检查

```powershell
& $pythonPath -c "from pathlib import Path; from data_pipeline.text_ner.openai_compatible_api import load_api_config, resolve_environment, OpenAICompatibleSettings; c=load_api_config(Path(r'$apiConfig')); s=OpenAICompatibleSettings.from_environment(c, resolve_environment(Path(r'$envFile'))); print(s)"
```

该检查不会访问网络；`OpenAICompatibleSettings` 会把 API key 固定显示为 `<redacted>`。未知配置项、重复配置项、错误引号和缺失必填项会直接报错，而不会静默忽略。

### 6.1 启动每10秒刷新的 HTML 监测

在单独的 PowerShell 窗口执行下面的命令。监测器可以先于 API 任务启动；response/audit 文件尚不存在时，页面显示“等待任务启动”。

```powershell
$monitorHtml = "$executionRoot\mention_monitor.html"

& $pythonPath -m data_pipeline.text_ner monitor-openai-compatible-api `
  "$executionRoot\mention_responses.jsonl" `
  "$executionRoot\mention_api_audit.jsonl" `
  --output-html $monitorHtml `
  --expected-requests 64509 `
  --stage-label 'Mention 实体识别' `
  --refresh-seconds 10 `
  --stalled-after-seconds 300 `
  --watch
```

保持这个 PowerShell 窗口运行，然后在另一个窗口打开页面：

```powershell
Start-Process -FilePath $monitorHtml
```

监测进程每10秒增量读取新增 JSONL，并原子替换同一个 HTML；浏览器页面也每10秒自动刷新。页面显示：

- response 与 audit 共同存在的已完成 request 数；
- 完成比例、剩余请求、近5分钟速度和 ETA；
- response/audit 单边缺失、重复 request ID 和无效 JSONL；
- token usage、模型 provenance、最近结果时间；
- 超过300秒无新增时的“可能停滞”提示。

页面不包含临床正文、实体内容、API key 或具体 request ID。“可能停滞”只能说明结果文件没有继续增加，不能单独证明 API 进程已经退出；此时应同时检查执行 API 的 PowerShell 窗口。按 `Ctrl+C` 可停止监测，不会影响 API 任务。

relation 阶段将输入文件和标签替换为：

```powershell
& $pythonPath -m data_pipeline.text_ner monitor-openai-compatible-api `
  "$executionRoot\relation_responses.jsonl" `
  "$executionRoot\relation_api_audit.jsonl" `
  --output-html "$executionRoot\relation_monitor.html" `
  --expected-requests 64509 `
  --stage-label 'Relation 关系抽取' `
  --refresh-seconds 10 `
  --stalled-after-seconds 300 `
  --watch
```

## 7. 推荐：先完成10个文本单元的端到端小批运行

### 7.1 运行10个 mention 请求

外部 API：

```powershell
& $pythonPath -m data_pipeline.text_ner run-openai-compatible-api `
  "$nerRoot\extraction_interface\requests\mention_requests.jsonl" `
  "$nerRoot\extraction_interface\configuration\prompts\mentions.md" `
  "$executionRoot\mention_responses.jsonl" `
  "$executionRoot\mention_api_audit.jsonl" `
  $apiConfig `
  --env-file $envFile `
  --execute `
  --endpoint-scope external `
  --confirm-data-transfer-authorized `
  --maximum-requests 10
```

本地 API 将最后五行替换为：

```powershell
  $apiConfig `
  --env-file $envFile `
  --execute `
  --endpoint-scope local `
  --maximum-requests 10
```

成功摘要应显示：

```text
model_calls_this_run: 10
completed_total: 10
remaining: 64499
```

响应只有通过 request/response Schema、来源哈希和精确字符 span 校验后才会追加到文件。失败的响应不会写入，下次执行仍从该 request ID 继续。

### 7.2 编译 mention 并生成10个 relation 请求

编译器要求 relation response 文件存在。首次运行时创建空文件：

```powershell
if (-not (Test-Path -LiteralPath "$executionRoot\relation_responses.jsonl")) {
  New-Item -ItemType File -Path "$executionRoot\relation_responses.jsonl" -Force | Out-Null
}
```

```powershell
& $pythonPath -m data_pipeline.text_ner compile-model-responses `
  "$nerRoot\extraction_interface" `
  "$nerRoot\input\text_ner_input_manifest.parquet" `
  "$executionRoot\mention_responses.jsonl" `
  "$executionRoot\relation_responses.jsonl" `
  --output-dir "$executionRoot\smoke_relation_input"
```

检查 `$executionRoot\smoke_relation_input\compile_summary.json`：

- `mention_responses_validated` 应为10；
- `relation_requests_ready` 应为10；
- `compile_status` 仍应为 `pending_model_execution`，因为总体有64,509个单元。

### 7.3 运行10个 relation 请求

外部 API：

```powershell
& $pythonPath -m data_pipeline.text_ner run-openai-compatible-api `
  "$executionRoot\smoke_relation_input\requests\relation_requests.ready.jsonl" `
  "$nerRoot\extraction_interface\configuration\prompts\relations.md" `
  "$executionRoot\relation_responses.jsonl" `
  "$executionRoot\relation_api_audit.jsonl" `
  $apiConfig `
  --env-file $envFile `
  --execute `
  --endpoint-scope external `
  --confirm-data-transfer-authorized `
  --maximum-requests 10
```

本地 API 同样改用 `--endpoint-scope local` 并删除传输确认参数。

### 7.4 编译小批结果

```powershell
& $pythonPath -m data_pipeline.text_ner compile-model-responses `
  "$nerRoot\extraction_interface" `
  "$nerRoot\input\text_ner_input_manifest.parquet" `
  "$executionRoot\mention_responses.jsonl" `
  "$executionRoot\relation_responses.jsonl" `
  --output-dir "$executionRoot\smoke_result"
```

此时可检查：

- `smoke_result/sidecars/entity_mentions.parquet`；
- `smoke_result/sidecars/text_relations.parquet`；
- `smoke_result/candidates/section_annotations.jsonl`；
- `smoke_result/compile_summary.json`。

小批结果仍是 `pending_model_execution` 和 `unreviewed_model_output`，用途是检查模型是否遵守实体类型、字符 span、否定、时间属性和关系证据规则。

## 8. 小批验收后运行全部 mention

重复7.1中的 mention 命令，但删除 `--maximum-requests 10`。继续使用同一个 `mention_responses.jsonl` 和 audit 文件：

```powershell
& $pythonPath -m data_pipeline.text_ner run-openai-compatible-api `
  "$nerRoot\extraction_interface\requests\mention_requests.jsonl" `
  "$nerRoot\extraction_interface\configuration\prompts\mentions.md" `
  "$executionRoot\mention_responses.jsonl" `
  "$executionRoot\mention_api_audit.jsonl" `
  $apiConfig `
  --env-file $envFile `
  --execute `
  --endpoint-scope external `
  --confirm-data-transfer-authorized
```

程序读取已有 response request ID，自动跳过前10个并继续剩余请求。中断后执行同一条命令即可续跑。

当前配置限制为每分钟30个请求。仅 mention 阶段64,509次调用的理论速率下限约35.8小时，尚未包含服务端延迟和重试；relation 阶段还会产生最多64,509次调用。修改 `requests_per_minute` 前必须确认服务商限流和预算。

mention 完成后检查：

```powershell
$mentionResponseCount = (
  Get-Content -LiteralPath "$executionRoot\mention_responses.jsonl" |
    Measure-Object -Line
).Lines

$mentionAuditCount = (
  Get-Content -LiteralPath "$executionRoot\mention_api_audit.jsonl" |
    Measure-Object -Line
).Lines

[pscustomobject]@{
  MentionResponses = $mentionResponseCount
  MentionAudits = $mentionAuditCount
  Expected = 64509
}
```

两项都应为64,509。若响应数和审计数不一致，应停止后续 relation 阶段并调查中断点。

## 9. 生成全量 relation 请求并运行

`relation_input` 是不可变编译目录，必须在首次生成前不存在：

```powershell
& $pythonPath -m data_pipeline.text_ner compile-model-responses `
  "$nerRoot\extraction_interface" `
  "$nerRoot\input\text_ner_input_manifest.parquet" `
  "$executionRoot\mention_responses.jsonl" `
  "$executionRoot\relation_responses.jsonl" `
  --output-dir "$executionRoot\relation_input"
```

确认 `relation_input/compile_summary.json` 中：

```text
mention_responses_validated = 64509
relation_requests_ready = 64509
```

然后运行 relation。小批阶段已经完成的10个 relation request ID 会被自动跳过：

```powershell
& $pythonPath -m data_pipeline.text_ner run-openai-compatible-api `
  "$executionRoot\relation_input\requests\relation_requests.ready.jsonl" `
  "$nerRoot\extraction_interface\configuration\prompts\relations.md" `
  "$executionRoot\relation_responses.jsonl" `
  "$executionRoot\relation_api_audit.jsonl" `
  $apiConfig `
  --env-file $envFile `
  --execute `
  --endpoint-scope external `
  --confirm-data-transfer-authorized
```

本地端点仍改用 `--endpoint-scope local`。

## 10. 编译最终实体和关系

```powershell
& $pythonPath -m data_pipeline.text_ner compile-model-responses `
  "$nerRoot\extraction_interface" `
  "$nerRoot\input\text_ner_input_manifest.parquet" `
  "$executionRoot\mention_responses.jsonl" `
  "$executionRoot\relation_responses.jsonl" `
  --output-dir "$executionRoot\final"
```

最终成功条件：

```powershell
Get-Content -LiteralPath "$executionRoot\final\compile_summary.json" |
  ConvertFrom-Json |
  Format-List
```

- `compile_status = complete_unreviewed_model_output`；
- `mention_responses_validated = 64509`；
- `relation_requests_ready = 64509`；
- `relation_responses_validated = 64509`；
- `model_calls_performed_by_compiler = 0`。

最终文件：

- `final/sidecars/entity_mentions.parquet`：实体、属性、来源和模型 provenance；
- `final/sidecars/text_relations.parquet`：显式关系及证据 span；
- `final/candidates/section_annotations.jsonl`：通过校验的 section 级候选；
- `final/compile_manifest.json`：输入和输出哈希。

实体数和关系数没有固定期望值，不能用“必须大于0”代替人工质量验收。

## 11. 常见停止原因

| reason code | 含义 | 处理 |
|---|---|---|
| `MODEL_EXECUTION_NOT_AUTHORIZED` | 没有显式传入 `--execute` | 确认确实要调用后再加入参数 |
| `EXTERNAL_DATA_TRANSFER_NOT_AUTHORIZED` | 外部端点未确认数据传输 | 完成合规判断后加入确认参数 |
| `GENERIC_API_ENVIRONMENT_MISSING` | `.env` 与进程环境合并后仍有配置缺失 | 补齐 `.env`，或在同一 PowerShell 中设置对应环境变量 |
| `GENERIC_API_ENV_FILE_*` | `.env` 不存在、编码或 `KEY=VALUE` 格式不合法 | 按报错行修正；不要加入未允许的配置名 |
| `API_MONITOR_*` | HTML 监测参数或输入类型错误 | 按 reason code 修正请求总数、刷新时间或文件路径 |
| `GENERIC_API_LOCAL_SCOPE_REQUIRES_LOOPBACK` | local 模式使用了非本机 URL | 修正 URL 或明确改用 external 模式 |
| `GENERIC_API_PROMPT_HASH_MISMATCH` | 请求包与提示词不是同一版本 | 重新生成请求包，不能跳过校验 |
| `GENERIC_API_ANNOTATION_JSON_INVALID` | 模型没有返回可解析 JSON | 检查模型兼容性和 prompt，不手工伪造响应 |
| `FULL_EXTRACTION_SOURCE_HASH_MISMATCH` | aggregation 正文和 manifest 不一致 | 停止执行并重新审计 aggregation |
| `RELATION_RESPONSE_BEFORE_VALIDATED_MENTIONS` | relation 没有对应的有效 mention | 先完成 mention 编译 |

## 12. 清除当前进程中的凭据

任务结束后：

```powershell
Remove-Item Env:TEXT_NER_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:TEXT_NER_BASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:TEXT_NER_MODEL -ErrorAction SilentlyContinue
Remove-Item Env:TEXT_NER_MODEL_VERSION -ErrorAction SilentlyContinue
Remove-Item Env:TEXT_NER_PROVIDER -ErrorAction SilentlyContinue
```

这只清除当前 PowerShell 进程的环境变量，不会修改 `.env`，也不会删除模型响应、审计日志或编译结果。若不再使用磁盘凭据，应从 `.env` 中清空 `TEXT_NER_API_KEY`。
