# Exploratory-only 项目状态决策

## 决策

当前项目降级为 `exploratory-only`。原因不是方法实现缺失，而是指定正式数据源中的 20,136 个主体全部已经出现在旧 split，`previous_exposure=none` 为 0。现有数据无法构造没有历史暴露的独立 final-test。

## 允许执行

- W0–W10 工程契约和离线测试；
- 使用 `fixture:` 主体的 final-test 流程演练；
- exploratory、unreviewed 的方法比较和审计报告。

## 禁止执行

- 将旧 split 内主体重新随机切分后称为 official final-test；
- 发布 official final-test 指标；
- 将 pattern rule concordance 增加为临床 gold；
- 将未签字题目计入批准数量。

## 恢复正式模式的条件

必须先获得旧 split 之外的新主体，完成 subject-level 互斥 split，证明 final-test 主体此前未暴露，并冻结 protocol lock、catalog、panel、diagnosis、feature whitelist 及其 hashes。恢复后复用 W10 `official` 门禁，final-test 只运行一次且不允许调参回流。

机器可读状态见 [exploratory-only-manifest.json](../exploratory-only-manifest.json)。
