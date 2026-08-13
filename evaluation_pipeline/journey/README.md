# Encounter boundary module

首版以住院为中心：一个 `hadm_id` 形成一个 journey；只有带原生
`hadm_id` 且患者一致、时间覆盖 admission handoff 的 ED stay 才纳入；独立 ED
进入 unresolved，留待后续独立轨道。ICU stay 是住院 journey 内的子阶段，
不会生成新的患者 journey。

模块的外部 interface 是 `EncounterInputs`、`JourneyScopePolicy`、
`build_encounter_boundaries` 和独立复核函数 `audit_encounter_boundary_manifest`。
调用方必须提供已经通过患者级 split 审计的 public
manifest 与 protected mapping，并指定单一 `subject_role`；一个输出不能混装
development、validation、final-test 或工程审计。输入中的 `subject_id`、`hadm_id`、ED/ICU stay ID
只在本地内存中用于原生连接；公开 manifest 使用调用方提供的 `subject_ref`
及 HMAC 派生引用，不写出这些原始标识。`reference_secret` 不进入产物，产物只
记录 `reference_key_id`。

构建器还必须接收完整 protocol lock 及其 freeze-ready source bundle，并验证
subject split 确实绑定到同一 lock；仅有一个格式正确的哈希或一份旧 split 不能启动边界构建。

输出绑定完整源输入摘要、上游 protocol lock 和 subject-split manifest 摘要，
并使用 `reference_secret` 对整个 boundary manifest 做 HMAC。独立复核必须同时
提供该密钥和预期上游摘要，因此不能把重算普通 SHA 后的来源重写误判为有效。

每条事件只能分配到一个 admission journey，否则进入 unresolved。具有相同
`event_time` 且为秒/亚秒精度的事件共享 `time_group_id`，没有人为顺序号，因此不会把并列事件
伪造成先后关系。输出保留输入的 `event_time` 与 `available_time` 原值，规范化
时间只在内部用于比较和并列分组。`permitted_use` 与
`rule_discovery_eligible` 把 development、validation、final-test 和工程审计的
用途机器化分开，final-test 不能进入规则发现；`engineering_audit` 固定不能进入
正式统计。

输入事件必须使用当前 clinical-event 合同的稳定 `evt:` 标识；每条公开 assignment
记录完整源事件摘要。`event_time` 的字符串形态必须与 `date`、`second` 或
`subsecond` 精度一致，矛盾记录进入 `JOURNEY_EVENT_TIME_INVALID`，不会产生伪造的
exact time group。

原生 `hadm_id` 只是候选连接：ED 还必须与 admission 时点发生 handoff，ICU
必须完整位于住院区间，事件必须位于“有效 ED 起点至出院”区间。缺失、非法或
越界时间全部进入稳定 reason code 的 unresolved。日期精度事件不会与精确午夜
事件伪造成 exact tie。生成器会立即运行独立语义审计，重算 manifest/policy 哈希、
计数、角色门禁、唯一性与 event→journey 引用。

该模块仍只是完整 patient journey 的 encounter-boundary 前置层；它不生成 state、
decision node 或 evidence edge。已实现的 boundary→snapshot 受审计连接器只闭合
前置层到通用快照的来源链，不替代完整 journey DAG 或任务科学协议。
