# E5 EHR-observable Gold 迁移决策

## 当前数据的结论

当前 normalization 数据只能用于方法学探索，不能形成合适的 EHR-observable Gold：

- `order_create_any_status` 覆盖高，但订单几乎全部为 `Inactive`，且多答案和缺失候选 key 严重；
- `order_create_active_only` 语义严格但覆盖仅约 0.12%；
- `normalized_result` 覆盖约 88.09%，但唯一答案率约 1.24%，结果不能替代订单行为；
- `mapped_imaging_order` 的唯一答案率为退化现象，因为全局只有一个 normalized concept。

因此当前状态保持 `exploratory-only`，不生成正式 gold。

## 给香港 RWD 的推荐 Gold 层级

### Primary：`observed_order_selection`

目标是“index time 后，同一比较类中实际记录的有效检查订单”。它是行为观察 Gold，不是临床最佳决策。必须同时具备订单 ID、发生时间、可用时间、生命周期状态、冻结后的检查 concept 和 comparison class。

零候选、多候选、取消/失效订单、时间不确定或映射未冻结时，统一拒答，不回退到全局高频答案。

### Secondary：`order_with_result_confirmation`

用于敏感性分析：订单之后在 target window 内出现可追溯结果。它要求稳定的 order-result grouping key；不能把结果行直接当作订单 Gold，也不能自行发明 specimen received time。

### 独立 normative Gold：`clinical_best_decision`

必须来自指南和专家裁决，不能由 EHR 频率、Lift、TF-IDF、BM25 或观察行为推断。

## 换数据时的执行顺序

1. 先运行 E1 schema/coverage audit；
2. 冻结香港 RWD 的 order lifecycle 和 terminology mapping；
3. 复用 W2–W5 的 encounter、snapshot、episode、decision contract；
4. 对 primary/secondary Gold 重新计算 coverage、唯一性、拒答和泄漏；
5. 在看到 final-test 前预注册门禁；
6. 只有 primary Gold 通过后才运行方法比较；
7. 最后才建立新的 subject-level split 和 official final-test。

当前数据的样本标签、阈值和旧 split 均不得迁移到香港 RWD。

机器可读规范见 [exploratory-gold-migration-manifest.json](../exploratory-gold-migration-manifest.json)。
