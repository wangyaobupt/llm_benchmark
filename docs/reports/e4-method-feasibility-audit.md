# E4 探索性方法可评估性审计

> 由于当前 EHR 候选没有形成合适的唯一 Gold，本阶段不伪造 Recall/MRR/NDCG 或 validation 结论。

## Gold 门禁

本次探索性门禁采用：覆盖率 ≥ 50%、唯一答案率 ≥ 50%、无候选 key 缺失、无 target availability 泄漏。该门禁用于方法学筛查，不是临床有效性阈值。

| 候选定义 | 覆盖率 | 唯一答案率 | 结论 |
|---|---:|---:|---|
| `mapped_imaging_order` | 68.012% | 100.000% | `NO_UNIQUE_NON_DEGENERATE_GOLD` |
| `normalized_result` | 88.090% | 1.242% | `NO_UNIQUE_NON_DEGENERATE_GOLD` |
| `order_create_active_only` | 0.118% | 2.174% | `NO_UNIQUE_NON_DEGENERATE_GOLD` |
| `order_create_any_status` | 99.252% | 0.436% | `NO_UNIQUE_NON_DEGENERATE_GOLD` |

## 方法职责边界

| 方法 | 当前允许 | 当前禁止 |
|---|---|---|
| `frequency` | 候选生成 | 最终答案排名、Recall/MRR/NDCG 声称 |
| `lift` | 候选生成 | 最终答案排名、Recall/MRR/NDCG 声称 |
| `shrunk_log_rr` | 候选生成 | 最终答案排名、Recall/MRR/NDCG 声称 |
| `binary_tfidf` | 候选生成 | 最终答案排名、Recall/MRR/NDCG 声称 |
| `bm25` | 候选生成 | 最终答案排名、Recall/MRR/NDCG 声称 |

## 结论

当前数据不能提供足够可靠的 EHR-observable Gold。最主要问题不是算法，而是订单概念 unresolved、订单生命周期大量 Inactive、结果/订单语义不同以及候选多答案。换用香港 RWD 时应先迁移 Gold 定义与门禁，再重新计算 coverage/uniqueness/leakage，不能迁移当前样本标签。

详细输入 hash 和门禁见同目录 JSON。
