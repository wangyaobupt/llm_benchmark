# W7 规则统计与收缩排名审计

## 结论

W7 的统计契约已实现并通过 4 项合成测试。所有统计量由 decision-level 二元集合形成的整数 2×2 表计算；零目标文档保留在 eligible development denominator 中，subject bootstrap 以主体为单位而不是以住院记录为独立样本。

## 已实现的规则

- `n_x`、`n_y`、`n_xy`、`n_total` 由去重后的 decision ID 集合计算；
- 输出 frequency、probability、lift、log-RR、收缩 log-RR、Wilson 区间所需量和标准误；
- 收缩使用预先固定的正先验，避免单次偶然共现直接获得无限排名；
- BH-FDR manifest 固定记录 family、完整 key 集合、p 值和 q 值，顺序稳定；
- bootstrap 单位为主体，主体的全部 decision documents 保持在同一个抽样单元内。

## 验证

```text
tests/investigation_selection/test_ranking.py
4 passed
```

## 正式统计状态

尚未对正式事件源运行规则枚举、p-value、bootstrap 或 validation 判断。W1 的 formal exposure population 和新 validation/final-test 主体仍未解冻，因此本阶段不生成任何正式规则表或临床结论。
