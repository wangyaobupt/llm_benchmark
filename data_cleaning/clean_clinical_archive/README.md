# 临床可读归档清洗器

本目录集中维护一条可复用的数据清洗流程：一次读取 admission 级 raw JSONL，同时完成官方字典解码和 POE 医嘱时间线解析，输出可直接供后续分析使用的临床可读 JSONL。

## 运行

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m data_cleaning.clean_clinical_archive `
  data\mimic-admission-raw-coronary-all-three-modules-random-100.jsonl `
  --output data\clean_clinical_archive\random-100-clinical-readable.jsonl `
  --report data\clean_clinical_archive\random-100-clinical-readable.report.json
```

默认从 `data/解析/json/` 读取五张官方字典。可用 `--dictionary-dir` 指向同结构目录，用 `--limit N` 做小批量验证。输出和报告均不覆盖已有文件；任一确定性约束失败时删除未完成文件并报错。

## 目录职责

- `decoder.py`：唯一共享解码内核，供本清洗器和旧字典解析入口共同调用；
- `pipeline.py`：输入 schema 校验、逐条解码、POE 解析、输出 schema 和报告；
- `__main__.py`：统一命令行入口；
- `docs/decoding-rules.md`：编码—字典映射及失败条件；
- `docs/poe-rules.md`：POE 连接、动作和证据边界；
- `docs/schema-contract.md`：输入、输出及可逆性契约。

`mimic_dictionary` 继续负责构建字典；`poe_timeline` 继续负责底层 POE 事件解析。本目录负责编排两者，不复制其实现。
