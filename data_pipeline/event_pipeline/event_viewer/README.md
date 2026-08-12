# Event viewer

本目录提供本地只读 Parquet 查看器。它既接受单独的 cleaning 目录，也接受包含 `cleaning/` 和 `normalization/` 的完整 workflow 目录。完整目录执行 `review` 后，会额外显示事件抽审样本和人工决策表，共 9 个数据集。

查看器不修改数据，不提供写接口，只监听 `127.0.0.1`。当提供源 JSONL 时，可通过 `raw_row_ref` 回查对应源数组元素。

`review_app.py` 由 `event_pipeline review` 复制到每个 `review/`。它读取审阅元数据，并把人工决定追加写入独立 JSONL 日志，不修改上游 Parquet。
