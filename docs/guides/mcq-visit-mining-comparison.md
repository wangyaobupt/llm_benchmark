# MCQ Visit 挖掘规则比较

该工具比较 `data/derived/mcq_visit_mining/` 下不同 profile 的完整六家族跑次，并生成自包含 HTML 页面。它只汇总规则级统计，不读取 `visit_transactions.jsonl`，也不输出患者级信息。

## 运行

从仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_mining.comparison `
  --input-root data\derived\mcq_visit_mining `
  --output-dir data\derived\mcq_visit_mining\comparison
```

可用 `--top-n 80` 调整每个方法、每个 family 在页面中保留的 Top 规则数，默认是 40。

生成文件：

- `data/derived/mcq_visit_mining/comparison/index.html`
- `data/derived/mcq_visit_mining/comparison/comparison_summary.json`
- `data/derived/mcq_visit_mining/comparison/说明文档.md`

直接用浏览器打开 `index.html`。页面支持按 family 和方法筛选，展示 accepted 数量、接受率、方法间 Jaccard 重合度和 Top 规则指标。

## 纳入与排除规则

一个跑次只有同时满足以下条件才会进入比较：

1. 六个 family 均存在。
2. 每个 family 均有 `summary.json`、`mining_manifest.json` 和 `conditional_rules.jsonl`。
3. 六个 family 的 `mining_manifest.status` 均为 `complete`。
4. 六个 family 使用同一个受支持的 profile。
5. 同一 family 在不同 profile 下的 `transactions_sha256` 完全一致。

不完整跑次不会被补齐或猜测，而是在页面底部明确列为排除项。如果同一个 profile 存在两个完整跑次，程序会直接失败，要求操作者消除歧义。

## 比较口径

跨 profile 不能使用 `rule_id` 对齐，因为 `rule_id` 的哈希输入包含 profile。工具使用以下稳定键：

```text
family + sorted(condition_feature_ids) + target_outcome_id
```

Jaccard 定义为：

```text
两种方法 accepted 规则交集数 / accepted 规则并集数
```

页面中的接受率定义为 `accepted / (accepted + rejected)`，不是 `accepted / tested_pairs`。

Top 规则按各 profile 在 `summary.json` 中记录的 `rank_key` 排序。需要注意，现有 profile 不仅改变排序键，也改变支持度和筛选门槛，因此 accepted 数量、重合度和排名变化反映的是“排序策略 + 门槛”的联合效果，不能解释为单一评分函数的纯因果比较。

比较页面中的所有内容均为 `exploratory_unreviewed`、`gold=0`，不能直接进入出题、人工批准或正式评测。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests.test_mcq_visit_mining_comparison
```

`data/` 按仓库规范不进入 Git。Git 保存比较器代码、测试和本说明；本地 HTML 由上述命令重复生成。
