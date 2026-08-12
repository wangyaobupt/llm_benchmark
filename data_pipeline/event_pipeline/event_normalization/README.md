# Event normalization

本目录只接收 cleaning 层的 `cleaned_events.parquet` 和 `term_inventory.parquet`，执行冻结的确定性概念与单位归一化。

- `terminology.py`：映射版本、源编码有效性、审核同义词和单位别名；
- `pipeline.py`：生成 normalized events、mappings、review queue 和 manifest；
- `schemas.py`：归一化输出合同的公开入口；
- `io.py`：本阶段自己的 Parquet、SHA-256 和原子发布基础设施。

本目录不依赖 cleaning pipeline 的私有写入函数，不调用 LLM，不猜测 unresolved 概念。
