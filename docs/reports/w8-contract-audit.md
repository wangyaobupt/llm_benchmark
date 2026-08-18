# W8 多诊断审计与增量抽取契约

## 结论

W8 的工程契约已实现并通过 4 项合成测试。诊断映射保留原始 code、映射状态和版本；域审计按主体去重，选择 manifest 记录每个域的规模、来源覆盖、时间可构建率和入选/排除理由。

## 已实现的规则

- 只接受预注册的七个 diagnosis family；
- 未映射 code 不丢失，标记为 `unmapped`；
- 诊断域主体数与事件数分开记录；
- ED/HOSP/Note/POE/lab 来源覆盖和时间可构建率进入审计；
- 至少四个域通过主体规模和时间门禁，否则 fail-closed；
- 入选域超过最小入选域两倍时机械排除；
- 没有读取 final-test 内容，也没有新增诊断专属清洗管线。

## 验证

```text
tests/investigation_selection/test_cohort.py
4 passed
```

## 正式数据状态

当前仅验证契约。正式七域覆盖、candidate entropy、class/tail coverage 和增量抽取必须等 W1 解冻独立主体后运行；本阶段不产生正式域选择或最终统计结论。
