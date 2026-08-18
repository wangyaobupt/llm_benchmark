# W5 决策文档与目标窗口审计

## 结论

W5 的工程契约已实现并通过测试：每个 decision document 固定绑定主体、旅程、索引时点、track、snapshot lineage、输入清单哈希、候选状态、可见证据和目标窗口。零候选主体会保留为正式记录，不能静默删除。

正式 benchmark 产物仍未生成。W1 已确认指定规范化事件源的 20,136 个主体全部落入旧 split，且 `previous_exposure=none` 为 0；因此在新 validation/final-test 主体和正式协议锁定前，W5 只能完成可审计的工程契约验证。

## 已实现的 fail-closed 规则

- snapshot lineage 不是 `boundary_authenticated` 时拒绝生成正式决策文档；
- target event 与 visible evidence 发生交集时拒绝该 decision；
- target event 不存在、目标窗口不合法或 decision ID 重复时拒绝；
- `zero_candidate_observed` 保留在文档中，零候选不被过滤；
- 输出按 decision ID、evidence ID、target ID 稳定排序，并生成 corpus manifest hash。

## 验证

```text
tests/investigation_selection/test_decision_documents.py
tests/investigation_selection/test_episodes.py
tests/investigation_selection/test_snapshot_adapter.py
9 passed
```

## 未决项

正式执行仍依赖 W1 决定 `formal_exposure_population`，并重新定义不复用旧 split 的 validation/final-test 主体。该决策完成前不读取或发布 final-test 结果。
