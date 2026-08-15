# Text NER API JSON 可靠性修复验收

## 结论

DeepSeek JSON Output 空内容或字符 span 错误导致整批 NER 中止的问题已修复。接口现在区分空内容、非法 JSON、完整 Markdown JSON 外层、Schema/span 合同错误、输出截断、内容过滤和系统资源中断，并根据原因决定确定性 span grounding、有限重试、隔离单条失败后继续或立即停止。

DeepSeek 官方文档明确说明 JSON Output 偶尔可能返回空 `content`；Chat Completions 文档同时说明 V4 默认启用 thinking，且 `finish_reason=length` 表示结果可能被截断。因此本次修复不是放宽标注合同，而是在进入合同校验前正确处理提供商的响应状态：[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)、[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion)。

## 实现边界

- DeepSeek NER 请求发送 `thinking={"type":"disabled"}`；其他 provider 不发送该字段。
- mention surface 与 relation evidence 优先通过大小写敏感的原文精确匹配校正 offset；精确匹配不存在时，只允许 casefold 和连续空白折叠，并从原文回填真实 surface。
- 不使用编辑距离、同义词或语义匹配，不改实体类型或其他语义属性。
- 唯一匹配直接落位；重复匹配只接受原 offset 对应的唯一最近候选；平局或原文不存在时保持失败。
- 每次成功调用在 audit 中保存不含正文的 span grounding provenance。
- 空 `content`、非法 JSON 和 Schema/span 合同错误最多重试3次；相同无效内容第二次出现时提前停止重复调用。
- 可隔离的内容失败写入 failure audit 后继续下一个文本单元；认证、配置、截断等非内容错误仍停止整批。
- 仅移除完整的 Markdown JSON 代码围栏，不猜测缺失括号、不重写字段、不进行语义 JSON repair。
- `finish_reason=length`、`content_filter` 和意外 tool call 不执行无意义重试。
- 成功响应仍须通过来源哈希、精确字符 span、实体枚举和关系合同校验。
- 失败审计不保存模型正文、临床正文或 API key，只保存响应 ID、finish reason、内容长度/SHA-256、usage、reason code 和重试状态。
- `maximum_requests` 限制不同文本单元尝试数；摘要分别报告文本单元尝试数、真实模型调用数、成功响应、失败单元、失败尝试、总 usage 与成功 usage。
- API 执行终端逐次打印调用、重试、成功、隔离失败和 token 进度。
- `--retry-failures-from` 只选择已有终止失败且尚未成功的 request ID，不顺带处理新文本。

## 验收证据

| 场景 | 结果 |
|---|---:|
| 空白 content 后重试成功 | passed |
| 完整 Markdown JSON 外层确定性移除 | passed |
| DeepSeek thinking disabled | passed |
| `finish_reason=length` 不盲目重试 | passed |
| 唯一 surface 精确匹配自动校正 offset | passed |
| casefold/空白归一化后从原文回填 surface | passed |
| 重复 surface 只接受唯一最近候选 | passed |
| relation evidence 只落位到覆盖 mentions 的候选 | passed |
| 无法校正的单条失败被隔离且批次继续 | passed |
| 相同非法 JSON 第二次出现时停止重复付费 | passed |
| 失败审计不含模型正文、临床正文或 API key | passed |
| 调用次数与失败/成功 token usage 对账 | passed |
| 既有成功响应断点续跑 | passed |
| failure audit 定向重试且不调用新文本 | passed |
| Text NER、API monitor 与 aggregation 完整测试 | 55 passed, 0 failed |
| 本轮诊断和代码修改新增模型调用 | 0 |

## 本次故障证据

修复前的 failure audit 共记录同一文本单元4次 `GENERIC_API_ANNOTATION_CONTRACT_INVALID`：4次模型内容长度均为859、内容 SHA-256 完全相同、每次1,322 tokens，合计5,288 tokens。这证明旧重试在 temperature 0 下重复获得同一无效结果，没有产生纠错价值。新实现会先进行确定性 span grounding；仍无效且第二次内容哈希相同时，以 `retry_stop_reason=identical_invalid_content` 停止该单元的后续重试并继续批次。

修复后的首个10文本单元小批从3条 checkpoint 开始：尝试10条，成功8条、失败2条、真实调用12次，checkpoint 增至11；总计16,986 tokens，其中成功响应9,808，失败尝试7,178。两个失败分别定位到 mention `m2` 和 `m1` 的 `MENTION_SURFACE_MISMATCH`，第二次返回均与第一次内容哈希相同；同时11条成功 audit 中有3条通过 `unique_exact_occurrence` 完成 span 校正。这些证据支持在精确匹配之后增加受限的 casefold/空白归一化，而不支持模糊字符串或语义匹配。

现有成功 response/audit checkpoint 未被本次代码修复改写。重新执行相同命令时会跳过已有成功 request ID，从下一个未成功文本单元继续。Codex 受限执行环境不能读取 `extraction_interface` 中的临床请求文件，因此真实 API 恢复没有在本次验收中代替用户发起；本次修复新增模型调用为0。
