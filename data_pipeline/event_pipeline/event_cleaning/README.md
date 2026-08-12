# Event cleaning

本目录把 admission 级临床可读 JSONL 转换为可追溯的原子临床事件。

- `source_catalog.py`：33 张表的 event/support/context 角色、原生键、时间策略和事实归属；
- `ids.py`：稳定 `source_row_id`、`event_id` 和 `entity_id`；
- `time_resolver.py`：源端时间与泄漏安全有效时间；
- `validation.py`：输入合同、事件 schema、来源和时间门禁；
- `pipeline.py`：流式写出 cleaning 产物、逐表对账和 manifest；
- `transformers/`：按临床域拆分的事件转换规则和唯一 registry。

该阶段不写入标准概念，不调用归一化或 LLM。
