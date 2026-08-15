# Text NER API JSON 可靠性修复验收

## 结论

DeepSeek JSON Output 空内容导致整批 NER 中止的问题已修复。接口现在区分空内容、非法 JSON、完整 Markdown JSON 外层、Schema/span 合同错误、输出截断、内容过滤和系统资源中断，并根据原因决定有限重试或立即停止。

DeepSeek 官方文档明确说明 JSON Output 偶尔可能返回空 `content`；Chat Completions 文档同时说明 V4 默认启用 thinking，且 `finish_reason=length` 表示结果可能被截断。因此本次修复不是放宽标注合同，而是在进入合同校验前正确处理提供商的响应状态：[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)、[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion)。

## 实现边界

- DeepSeek NER 请求发送 `thinking={"type":"disabled"}`；其他 provider 不发送该字段。
- 空 `content`、非法 JSON 和 Schema/span 合同错误最多重试3次，总尝试上限4次。
- 仅移除完整的 Markdown JSON 代码围栏，不猜测缺失括号、不重写字段、不进行语义 JSON repair。
- `finish_reason=length`、`content_filter` 和意外 tool call 不执行无意义重试。
- 成功响应仍须通过来源哈希、精确字符 span、实体枚举和关系合同校验。
- 失败审计不保存模型正文、临床正文或 API key，只保存响应 ID、finish reason、内容长度/SHA-256、usage、reason code 和重试状态。
- `model_calls_this_run` 改为真实 API 尝试数，并分别报告成功响应、失败尝试、总 usage 与成功 usage。

## 验收证据

| 场景 | 结果 |
|---|---:|
| 空白 content 后重试成功 | passed |
| 完整 Markdown JSON 外层确定性移除 | passed |
| DeepSeek thinking disabled | passed |
| `finish_reason=length` 不盲目重试 | passed |
| 持续非法 JSON 在第4次后停止 | passed |
| 失败审计不含模型正文、临床正文或 API key | passed |
| 调用次数与失败/成功 token usage 对账 | passed |
| 既有成功响应断点续跑 | passed |
| Text NER、API monitor 与 aggregation 完整测试 | 46 passed, 0 failed |
| 本次修复触发真实模型调用 | 0 |

现有 `mention_responses.jsonl` 和 `mention_api_audit.jsonl` 未改写。修复前发生的空响应没有被旧版本持久化；重新执行相同命令时会跳过已有的1条成功响应，从下一个 request ID 继续。
