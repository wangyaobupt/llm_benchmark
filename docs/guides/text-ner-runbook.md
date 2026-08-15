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

当前接口会发送 `response_format={"type":"json_object"}`。DeepSeek 官方要求提示词同时明确要求 JSON、提供格式示例，并合理设置 `max_tokens`；本项目的 mention 和 relation prompt 已满足前两项。官方同时明确说明 JSON Output 偶尔会返回空 `content`，因此接口把空内容和非法 JSON 设为有限重试，而不是直接把整批任务终止。参考：[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)。

DeepSeek V4 默认启用 thinking。NER 是受 Schema 和精确字符 span 约束的抽取任务，不需要开放式推理；当前 `openai-compatible-api.json` 仅在 provider 为 `deepseek` 时发送 `thinking={"type":"disabled"}`，避免 reasoning token 挤占 JSON 输出预算。其他 OpenAI-compatible provider 不会收到该字段。`finish_reason=length` 表示结果已被 `max_tokens` 或上下文长度截断，此时重复同一请求不能解决问题，接口会停止并要求提高 `request.max_tokens` 或缩短 section。参考：[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion)。

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

从仓库根目录可直接复制执行：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner monitor-openai-compatible-api `
  'data\test_1000_0812\event_pipeline_output\NER\model_execution\mention_responses.jsonl' `
  'data\test_1000_0812\event_pipeline_output\NER\model_execution\mention_api_audit.jsonl' `
  --expected-requests 64509 `
  --stage-label 'Mention 实体识别' `
  --watch `
  --interval-seconds 10
```

必须使用项目的 Python 3.12 虚拟环境；裸 `python` 可能指向系统中另一个未安装项目依赖、甚至版本不兼容的解释器。可用 `& $pythonPath -c "import sys; print(sys.executable)"` 确认当前路径。`--interval-seconds` 是 `--refresh-seconds` 的兼容别名。省略 `--output-html` 时，上述 audit 文件会自动对应到同目录的 `mention_monitor.html`。命令中的两个 JSONL 路径是实际路径，不要再添加尖括号。

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

监测进程启动后会立即在终端打印一行状态，此后每10秒打印一次心跳，同时增量读取新增 JSONL，并原子替换同一个 HTML；浏览器页面也每10秒自动刷新。终端输出类似：

```text
[监测器：不发起 API 调用] 2026-08-15 14:00:00 +0800 | Mention 实体识别 | 可能停滞 | 完成 1/64,509 (0.00%) | 剩余 64,508 | 速度 0.00 requests/分钟 | HTML data\...\mention_monitor.html
```

监测命令只读取结果，不会启动 NER 模型调用。必须在另一个 PowerShell 窗口执行第7节的 `run-openai-compatible-api --execute`，response/audit 才会继续增加。页面显示：

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

推荐使用仓库脚本。它不依赖当前 PowerShell 会话中的 `$pythonPath`、`$nerRoot` 等变量，会自行定位仓库和文件，并在调用前检查 Python 3.12、请求、prompt、API 配置和 `.env`。

先执行只读预检；该命令不会调用 API：

```powershell
Set-Location 'D:\Projects\llm_benchmark'
& '.\scripts\Run-TextNerMentionSmoke.ps1' -ValidateOnly
```

预检通过后，明确确认外部临床文本传输并运行最多10个文本单元：

```powershell
& '.\scripts\Run-TextNerMentionSmoke.ps1' -ConfirmExternalDataTransfer
```

如需改变小批数量，例如只运行2个文本单元：

```powershell
& '.\scripts\Run-TextNerMentionSmoke.ps1' `
  -MaximumRequests 2 `
  -ConfirmExternalDataTransfer
```

下面是脚本内部对应的外部 API 命令，仅用于理解参数。只有已执行第2节变量初始化的同一个 PowerShell 会话才能直接复制这一形式：

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
attempted_requests_this_run: 10
model_calls_this_run: 10
successful_responses_this_run: 10
failed_requests_this_run: 0
failed_attempts_this_run: 0
completed_total: 11
remaining: 64498
```

上述当前值包含已经存在的1条 checkpoint；如果从空 checkpoint 启动，则 `completed_total` 为10。`--maximum-requests 10` 限制本次最多尝试10个不同文本单元，而不是要求必须取得10个成功结果，避免持续无效输出时失控扩大费用。`model_calls_this_run` 表示真实 API 调用次数；发生重试时它会大于 `attempted_requests_this_run`，避免低估调用量和成本。

API 执行期间会立即打印已载入数量，随后逐次打印“调用/重试/成功/失败并继续”、累计成功/失败数和本次 token usage。响应只有通过 request/response Schema、来源哈希和精确字符 span 校验后才会追加到成功文件。

模型给出的 mention 或 relation evidence offset 不准确时，接口先执行确定性 span grounding。第一层使用原文中大小写敏感的精确 `surface_text`/`evidence_text`；找不到时，第二层仅允许 Unicode casefold 和连续空白折叠匹配，并把结果 surface 回填为原文真实子串。唯一匹配直接落位，多次匹配仅在原 offset 指向唯一最近候选时落位，平局或归一化后仍不存在时拒绝。关系 evidence 还必须覆盖 source/target mentions。接口不改实体类型或其他语义属性，不使用编辑距离、同义词或语义猜测。成功 audit 的 `span_grounding` 保存原始/校正 offset、候选数、规则及是否从原文回填 surface，不保存临床文字。

空内容、非法 JSON 或无法校正的合同错误会有限重试；连续两次得到相同内容 SHA-256 时提前停止，避免确定性模型重复产生同一无效输出。该文本单元写入 failure audit 后，批次继续处理下一个单元。截断、认证、端点或配置等非内容错误仍立即停止整批。失败审计只保存 reason code、具体标注校验原因、finish reason、响应 ID、内容长度/SHA-256、usage 和重试状态，不保存模型正文、临床正文或 API key。下次执行仍从未成功的 request ID 继续。

只重试 failure audit 中已经终止且尚未成功的文本单元，不调用新的 pending 文本：

```powershell
& '.\scripts\Run-TextNerMentionSmoke.ps1' `
  -RetryFailuresOnly `
  -ConfirmExternalDataTransfer
```

脚本会向 CLI 传递 `--retry-failures-from mention_api_audit.failures.jsonl`。终端启动行应显示 `模式 terminal_failures_only`；`候选`是当前尚未成功的失败 request 数，可能少于 `-MaximumRequests`。

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

程序读取已有 response request ID，自动跳过前10个并继续剩余请求。中断或空响应重试耗尽后，执行同一条命令即可续跑；现有成功响应不会重新调用。

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
| `GENERIC_API_ANNOTATION_CONTENT_EMPTY` | JSON Output 返回空内容 | 程序自动有限重试；耗尽后检查 failure audit，再执行同一命令续跑 |
| `GENERIC_API_ANNOTATION_JSON_INVALID` | 模型返回非 JSON；程序已有限重试 | 检查 failure audit 中的 finish reason、长度和 SHA，不手工伪造响应 |
| `GENERIC_API_OUTPUT_TRUNCATED` | `finish_reason=length`，JSON 被截断 | 提高配置中的 `max_tokens` 或缩短 section；同参数盲目重试无效 |
| `GENERIC_API_OUTPUT_CONTENT_FILTERED` | 输出被服务商过滤 | 停止并审查该服务商是否适合处理此数据，不自动绕过过滤 |
| `GENERIC_API_ANNOTATION_CONTRACT_INVALID` | JSON 可解析但不满足 Schema/span 合同 | 程序有限重试；检查 failure audit 和模型兼容性 |
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
