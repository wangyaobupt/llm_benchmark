# mcq_visit_extract：从 MIMIC 原始表抽 visit 行文件

五类题型底座第三版实现。只读 `data/RawData` 的 CSV.GZ，按 `(subject_id, hadm_id)` 做纳入漏斗后确定性抽取，写出一行一次住院的 `visits.csv` / `visits.json`。非正式 gold。

设计合同：[`docs/design/20260820_出题数据抽取第三版-1万例随机Visit直接抽取执行计划.md`](../../docs/design/20260820_出题数据抽取第三版-1万例随机Visit直接抽取执行计划.md)。

## 断点续传

对同一 `--output-dir` 再次执行同一命令即续跑：

- `manifest.json` 身份（源文件 SHA-256 + sample/shard/pool）不一致则拒绝混跑。
- `selection.jsonl` 一旦写出只读，不会重抽 10,000 个住院。
- 漏斗清单、每张 staging 表、每个 Visit 分片各自 `status=complete` + sha256；`.partial` 续跑时删除重做。
- 已完成分片文件缺失或哈希变化 → 终止，不静默重算。
- 分片都齐、只缺 `visits.csv`/`visits.json` 时，从 `working/` 重投影，不重扫 MIMIC。

没有 `--resume` 开关。

## 进度页面

抽取过程会写 `monitor_activity.json`（只有阶段名，不含病历原文）。另开一个只读 HTML 页，每 2 秒刷新漏斗、staging、分片和交付进度。

单独打开（适合已经在跑或续跑的目录）：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_extract.monitor `
  --output-dir data\derived\mcq_visit_extract\pilot100_dev20 `
  --open-browser
```

抽取同时打开（默认 http://127.0.0.1:8766/）：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_extract `
  --data-root data\RawData `
  --output-dir data\derived\mcq_visit_extract\pilot100_dev20 `
  --sample-size 100 `
  --monitor
```

页面不读取 `visits.csv` / 出院小结原文。

## 命令

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_extract `
  --data-root data\RawData `
  --output-dir data\derived\mcq_visit_extract\pilot100_dev20 `
  --sample-size 100 `
  --shard-size 50 `
  --development-percent 20
```

正式 10,000 例把 `--sample-size` 改为 `10000`、`--shard-size 1000`，并换新 `output-dir`。

时间点（schema `3.1.2`）：`medications.starttime/stoptime`、`procedures.chartdate`、化验/影像 `storetime`、`medrecon.charttime`，以及 `admittime`/`dischtime`/`ed_intime` 等住院时钟。已冻结的 10k 若缺这些键，不要覆盖原目录，另跑补齐：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_extract.backfill_times `
  --extract-dir data\derived\mcq_visit_extract\random10k_dev20 `
  --output-dir data\derived\mcq_visit_extract\random10k_dev20_times `
  --expected-count 10000
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests.test_mcq_visit_extract tests.test_mcq_visit_extract_monitor tests.test_mcq_visit_extract_medtimes
```
