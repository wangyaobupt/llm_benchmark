# Event viewer

本目录提供本地只读 Parquet 查看器。它既接受单独的 cleaning 目录，也接受包含 `cleaning/` 和 `normalization/` 的完整 workflow 目录。

查看器不修改数据，不提供写接口，只监听 `127.0.0.1`。当提供源 JSONL 时，可通过 `raw_row_ref` 回查对应源数组元素。
