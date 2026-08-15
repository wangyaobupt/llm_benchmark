# Text NER API 配置与运行手册

本文说明如何从已经生成的1000例 aggregation 开始，配置一个 OpenAI-compatible API，依次完成 mention 实体识别、relation 关系抽取和最终 sidecar 编译。

当前正式输入为：

```text
data/test_1000_0812/event_pipeline_output/aggregation
```

当前请求规模为64,509个文本单元。所有模型输出在人工验收前均为 `unreviewed_model_output`，不能称为 gold 或经过验证的实验结果。

## 1. 运行前边界

- API key 只放在当前进程环境变量中，不写入代码、配置、日志或 Git。
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
$executionRoot = "$nerRoot\model_execution"
```

环境变量只对当前 PowerShell 进程及其子进程生效。当前 CLI 不会自动读取 `.env` 文件。

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

成本优先时配置 V4 Flash：

```powershell
$secureApiKey = Read-Host 'DeepSeek API key' -AsSecureString
$env:TEXT_NER_API_KEY = [System.Net.NetworkCredential]::new('', $secureApiKey).Password
$env:TEXT_NER_BASE_URL = 'https://api.deepseek.com'
$env:TEXT_NER_MODEL = 'deepseek-v4-flash'
$env:TEXT_NER_MODEL_VERSION = 'DeepSeek-V4-Flash'
$env:TEXT_NER_PROVIDER = 'deepseek'
```

`TEXT_NER_MODEL_VERSION` 是写入本地 provenance 的标签，不会发送给 API，也不能单独证明远端权重完全不可变。若服务商提供不可变 revision，应把该 revision 填入此变量。

当前接口会发送 `response_format={"type":"json_object"}`。DeepSeek 官方要求提示词同时明确要求 JSON；本项目的 mention 和 relation prompt 已满足这一点。参考：[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)。

不要把 key 直接写成 `$env:TEXT_NER_API_KEY='sk-...'` 后保存到脚本，因为这可能进入 PowerShell 历史。

## 5. 配置其他 OpenAI-compatible API

外部服务模板：

```powershell
$secureApiKey = Read-Host 'API key' -AsSecureString
$env:TEXT_NER_API_KEY = [System.Net.NetworkCredential]::new('', $secureApiKey).Password
$env:TEXT_NER_BASE_URL = 'https://provider.example/v1'
$env:TEXT_NER_MODEL = 'provider-model-id'
$env:TEXT_NER_MODEL_VERSION = 'immutable-model-revision'
$env:TEXT_NER_PROVIDER = 'provider-name'
```

程序会在 base URL 后追加 `/chat/completions`。因此 base URL 应停在服务商的 API 根路径，不要自行追加 `/chat/completions`。

本地服务模板：

```powershell
$env:TEXT_NER_API_KEY = 'local-placeholder'
$env:TEXT_NER_BASE_URL = 'http://127.0.0.1:8000/v1'
$env:TEXT_NER_MODEL = 'local-model-id'
$env:TEXT_NER_MODEL_VERSION = 'local-checkpoint-sha256-or-revision'
$env:TEXT_NER_PROVIDER = 'local-openai-compatible'
```

兼容服务必须支持 Chat Completions、system/user messages、`max_tokens`，并返回 `choices[0].message.content`。默认配置还要求支持 JSON object response format；如果服务不支持，不能直接运行当前配置，应先修改并重新验收该提供商配置。

## 6. 不泄露 key 的配置检查

```powershell
$requiredEnvironment = @(
  'TEXT_NER_API_KEY',
  'TEXT_NER_BASE_URL',
  'TEXT_NER_MODEL',
  'TEXT_NER_MODEL_VERSION',
  'TEXT_NER_PROVIDER'
)

$missingEnvironment = $requiredEnvironment | Where-Object {
  [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_))
}
if ($missingEnvironment) {
  throw "Missing API settings: $($missingEnvironment -join ', ')"
}

[pscustomobject]@{
  ApiKeyConfigured = -not [string]::IsNullOrWhiteSpace($env:TEXT_NER_API_KEY)
  BaseUrl = $env:TEXT_NER_BASE_URL
  Model = $env:TEXT_NER_MODEL
  ModelVersion = $env:TEXT_NER_MODEL_VERSION
  Provider = $env:TEXT_NER_PROVIDER
}
```

该检查不会访问网络，也不会打印 API key。

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
  --execute `
  --endpoint-scope external `
  --confirm-data-transfer-authorized `
  --maximum-requests 10
```

本地 API 将最后四行替换为：

```powershell
  $apiConfig `
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
| `GENERIC_API_ENVIRONMENT_MISSING` | 环境变量缺失 | 在同一个 PowerShell 中重新配置 |
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

这只清除当前 PowerShell 进程的环境变量，不会删除模型响应、审计日志或编译结果。
