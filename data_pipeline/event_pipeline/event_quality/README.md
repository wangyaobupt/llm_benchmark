# Event quality

本目录保存独立质量门禁：

- `audit_cleaning.py`：全量来源、身份、时间、拒绝原因和逐表对账；event/rejected Parquet 按 batch 迭代，JSONL 使用字节偏移随机读取，source lineage 使用可指定工作目录的 DuckDB 批量对账，抽样采用确定性 reservoir，不复制整份 JSONL，也不把全表常驻内存；
- `audit_normalization.py`：schema、manifest、映射应用、review queue 和事实不变性；cleaned/normalized 事件按顺序流式配对，event ID 去重使用磁盘 SQLite；
- `reproducibility.py`：不同 batch size 两次运行的文件 SHA-256、run ID 和计数比较；
- `regression.py`：三批人工确认 cleaning fixture 的 capture/verify。
- `review_normalization.py`：绑定实时 SHA-256，生成归一化自动检查、分层事件样本和人工决策表。
- `consolidate_review.py`：按冻结术语键合并多批审阅包，阻断语义冲突并生成互斥的 100 条人工试审。

审计逻辑不能导入 transformer 或术语映射规则来复述生产实现。
