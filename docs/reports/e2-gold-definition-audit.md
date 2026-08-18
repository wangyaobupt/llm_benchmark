# E2 EHR-observable Gold 候选定义审计

> 本阶段只比较 EHR 可观测定义，不发布 formal gold。

## 候选定义

| 候选 | 可观测单位 | 当前主要门禁 |
|---|---|---|
| `observed_order_category` | order event/category | clinical/laboratory order 缺少 normalized concept；取消和无效生命周期需排除 |
| `normalized_result_observation` | mapped result/test concept | 结果不是订单；结果可用时间不能进入 index 前 evidence |
| `order_with_result_confirmation` | order + later result | 需要稳定 grouping key；不能虚构 specimen received time |

## 目标事件规模

- `clinical_ordered`：`4,015,636` 行
- `imaging_ordered`：`179,223` 行
- `imaging_reported`：`138,399` 行
- `laboratory_ordered`：`969,587` 行
- `laboratory_resulted`：`8,237,891` 行
- `microbiology_resulted`：`153,622` 行

## 初步选择原则

1. 行为 Gold 优先使用 source event 的有效订单，不用结果行替代订单；
2. 细粒度答案必须有稳定 concept 或经过人工冻结的 source label；
3. 取消、discontinue、inactive 订单不能直接算有效 target；
4. 结果确认可作为独立敏感性定义，但不能与 order Gold 混称；
5. 下一阶段按 decision/encounter 构造唯一 target，评估覆盖、拒答和 evidence 泄漏。

详细生命周期、标签和 concept 计数见同目录 JSON。
