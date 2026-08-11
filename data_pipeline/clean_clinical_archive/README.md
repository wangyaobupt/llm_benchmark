# 临床可读归档清洗器

## 当前定位

这是当前推荐清洗主流程的第二步，也是把 admission 原始 JSONL 转为可直接分析资料的统一入口：

```text
mimic_admission_raw/1.0.0 JSONL
    ↓ 字典解码 + POE 解析
mimic_admission_clinical_readable/1.0.0 JSONL
```

它直接接收 `mimic_raw_archive` 输出，不需要运行 `mimic_episode` 或 `parquet_to_jsonl`。

本目录是完整可搬移的清洗包：一次读取 admission 级 raw JSONL，同时完成官方字典解码和 POE 医嘱时间线解析，输出可直接供后续分析使用的临床可读 JSONL。运行所需的项目代码、规则文档和五份授权字典都在本目录内；清洗主流程只需要 Python 3.12 标准库。

## 运行

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.clean_clinical_archive `
  data\mimic-admission-raw-coronary-all-three-modules-random-100.jsonl `
  --output data\clean_clinical_archive\random-100-clinical-readable.jsonl `
  --report data\clean_clinical_archive\random-100-clinical-readable.report.json
```

如果只复制了 `clean_clinical_archive` 文件夹，则在它的父目录执行：

```powershell
python -m clean_clinical_archive `
  input.jsonl `
  --output output-clinical-readable.jsonl `
  --report output-clinical-readable.report.json
```

默认读取包内 `dictionaries/`。可用 `--dictionary-dir` 显式指向同结构目录，用 `--limit N` 做小批量验证。输出和报告均不覆盖已有文件；任一确定性约束失败时删除未完成文件并报错。

首次使用或复制后先运行完整性自检：

```powershell
python -m clean_clinical_archive.verify_bundle
```

## 目录职责

- `decoder.py`：唯一共享解码内核，供本清洗器和旧字典解析入口共同调用；
- `pipeline.py`：输入 schema 校验、逐条解码、本地 POE 解析、输出 schema 和报告；
- `__main__.py`：统一命令行入口；
- `poe/`：完整 POE 时间线解析实现；
- `dictionaries/`：五份运行所需的官方字典 JSON；
- `bundle-manifest.json` 与 `verify_bundle.py`：便携包文件、字典行数、大小和哈希校验；
- `docs/decoding-rules.md`：编码—字典映射及失败条件；
- `docs/poe-rules.md`：POE 连接、动作和证据边界；
- `docs/schema-contract.md`：输入、输出及可逆性契约。

`data_pipeline.tools.mimic_dictionary.decode_archive` 仍提供只做字典解码的入口，但调用本目录中的唯一解码内核。POE 实现只保存在本目录的 `poe/`，不再维护独立兼容包。五份字典受 MIMIC 数据使用协议约束，随本地文件夹使用，不进入 Git 或公开分发。

本模块不调用 `rwd_pipeline.standardization.common`。该标准化包是否完整不会影响本清洗入口。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest -v `
  tests.test_clean_clinical_archive `
  tests.test_poe_timeline
```
