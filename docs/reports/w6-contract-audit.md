# W6 TF-IDF/BM25 检索契约审计

## 结论

W6 的检索工程契约已实现并通过 5 项合成测试。实现对象是 decision-level 文档，不直接对事件行计数；索引只允许 development 文档拟合，validation 只能 transform/retrieve，final-test 不会进入词表、df 或 IDF。

## 已实现的规则

- 支持 `frequency`、`binary_tfidf`、`log_count_tfidf`、`bm25` 四种配置；
- binary TF-IDF 对同一文档重复特征去重，重复事件行不会改变二元表示；
- 按 `track_id/candidate_class/window_id` 隔离邻居集合；
- 同主体邻居强制排除；
- unresolved、post-hoc、身份字段和未冻结 NER 特征被排除并计入审计；
- OOV 特征计数，不回退到全局高频榜；无可用特征或邻居时返回明确 refusal reason；
- manifest 固定记录 vocabulary、document order、IDF 哈希及 development-only 状态；
- 邻居、相似度、特征贡献和拒绝原因可逐预测追溯。

## 验证

```text
tests/investigation_selection/test_retrieval.py
5 passed
```

## 正式实验状态

未使用当前正式数据执行检索实验。W1 尚未解决新 validation/final-test 主体与 formal exposure population，因而没有生成 Recall/MRR/NDCG 或 final-test 结果。负对照和 paired bootstrap 属于正式 split 解冻后的实验工作，不在本阶段伪造统计结果。
