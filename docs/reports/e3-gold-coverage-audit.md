# E3 EHR-observable Gold 覆盖与泄漏审计

> 这是 encounter-level 探索性审计，不是 frozen protocol 或 official final-test。

- 探索性 index：每个 encounter 最早的 `patient_transferred`（`ED/admit`）`event_time`。
- target window：index 后 `24` 小时。
- 边界 encounter：`39,036`；边界 `available_time` 缺失，因此未伪造该字段。

| 定义 | eligible rows | encounter coverage | unique-answer rate | missing key | availability unknown | time leakage |
|---|---:|---:|---:|---:|---:|---:|
| `order_create_any_status` | 1,916,855 | 99.252% | 0.436% | 746,409 | 0 | 0 |
| `order_create_active_only` | 867 | 0.118% | 2.174% | 229 | 0 | 0 |
| `normalized_result` | 1,754,301 | 88.090% | 1.242% | 0 | 0 | 0 |
| `mapped_imaging_order` | 39,784 | 68.012% | 100.000% | 0 | 0 | 0 |

## 解释边界

- `order_create_any_status` 不能直接视为有效订单 Gold：当前数据中大量订单为 `Inactive`，需单独审核生命周期语义。
- `order_create_active_only` 是严格定义，若覆盖过低应拒答，而不是回退到 Inactive。
- `normalized_result` 是可观测结果定义，不等于 observed order；可作为敏感性 Gold，不得改名为订单 Gold。
- `mapped_imaging_order` 的 100% unique-answer rate 是退化结果：E2 显示全局只有一个 normalized imaging concept，不能据此判定 Gold 合适。
- 任一候选的 time leakage、missing key、multi-candidate 和 zero-candidate 都必须保留在 decision manifest。

详细计数见同目录 JSON。
