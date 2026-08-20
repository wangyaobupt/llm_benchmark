# mcq_visit_mining

在 Visit 时间线上按六个家族**分别**挖 X→y。每次只读该家族允许的特征，禁止后验泄漏。不出题。非正式 gold。

必须先跑 `python -m data_pipeline.mcq_visit_timeline`。

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_mining `
  --timeline-dir data\derived\mcq_visit_timeline\random10k_dev20_v1.0.0 `
  --output-dir data\derived\mcq_visit_mining\random10k_dev20_strict_v1.0.0\type1_investigation `
  --family type1_investigation `
  --profile strict `
  --expected-count 10000
```

六个家族请各跑一次、各写一个目录（见运行手册）。不要把诊断、化验结果、处方写进题型①。

`--family all` 会在 `--output-dir` 下建六个子目录顺序跑，仍彼此隔离。
