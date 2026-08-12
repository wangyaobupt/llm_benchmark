# 检查检验选择任务协议

## 当前结论

本协议只注册第一阶段的 `pattern/rule-concordance`：给定冻结条件 X，答案是 development 真实世界数据中同一 comparison class 内最可能被选择的检查。它不是单病例 next event，也不声称是临床最佳决策。

当前 `protocol.yaml` 为机器可校验的 draft，不是冻结协议。split 比例、ED scope、时间窗、候选目录版本、统计阈值和 validation 阈值仍未决定；锁定命令必须拒绝该配置。

## 单一规范源

- 科学协议：`config/investigation-selection/protocol.yaml`
- reason code：`config/investigation-selection/reason-code-registry.yaml`
- 协议 Schema：`schemas/investigation-selection-protocol.schema.json`
- 假设空间 Schema：`schemas/hypothesis-space-manifest.schema.json`
- 验证与锁定实现：`evaluation_pipeline.governance`

`scientific_protocol` 中的字段决定假设空间、统计、gold 或发布集合。线程和缓存仅属于 `runtime_configuration`。Git、依赖锁和输入 manifest 哈希属于 `audit_metadata`，不进入科学协议哈希。

## 锁定语义

同一 `scientific_protocol` 必须产生相同 `scientific_protocol_sha256`。完整 protocol、reason registry 和 Schema 内容完全相同时，产生相同 `protocol-lock.json`。锁文件不记录生成时间，也不把包含自身的 Git commit 作为哈希输入，从而避免循环引用。

正式运行时另需在 `audit_metadata` 记录上游基线 commit、`uv.lock` 哈希和输入 manifest 哈希。改变这些审计输入会改变完整锁，但不会改变科学协议哈希。

## 使用

```powershell
.\.venv\Scripts\python.exe -m evaluation_pipeline.governance validate `
  --protocol config\investigation-selection\protocol.yaml `
  --schema schemas\investigation-selection-protocol.schema.json `
  --reason-registry config\investigation-selection\reason-code-registry.yaml
```

只有 `protocol_status: frozen`、`unresolved_decisions` 为空、科学协议无 `null` 且 Schema/注册表均通过时，才允许将 `validate` 改为 `lock --output artifacts\protocol-lock.json`。

## 停止条件

- 任一构念共用未标注的 gold 字段；
- 未冻结候选目录或 comparison class；
- final-test 原始数据、派生统计、失败日志或候选缺失率参与开发；
- FDR family 不能在统计前机械枚举；
- validation 的并列、缺失、零分母或 `inconclusive` 无机械政策；
- 协议存在未决科学字段却被标记为 frozen。
