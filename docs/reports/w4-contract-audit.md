# W4 合同级审计

状态：`engineering_contract_passed`；正式运行：`blocked_by_W1_protocol_lock`。

episode builder 已覆盖：

- POE 同一 `source_group_id` 的 burst 合并；取消/停用医嘱 fail-closed；
- category-only Lab 仅保留 generic 类语义，不伪造 analyte order；
- labevents/microbiology 结果按 source group 建 bundle；partial panel 不标为 complete；
- order 与 result proxy 维持独立 track，不因时间邻近建立伪造链接；
- candidate catalog 保留 `track_id`、`candidate_level` 和 `exploratory_unreviewed` 状态。

测试结果：W4 专项及 W2 grouping 测试 `8 passed`。正式 panel definitions 和 catalog 仍需 W1 lock 后才能进入数据运行。
