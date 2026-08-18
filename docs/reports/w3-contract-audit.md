# W3 合同级审计

状态：`engineering_contract_passed`；正式运行：`blocked_by_W1_protocol_lock`。

已实现 `snapshot_adapter.py`，仅调用 `evaluation_pipeline.snapshot` 的 authenticated boundary API，不复制 occurrence、availability、phase 或 split 判断。discharge NER 归一化结果固定为 `evidence_phase=post_hoc`、`review_status=pending`（缺省时）和 `formal_feature_eligible=false`。

验收命令：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest tests/investigation_selection/test_snapshot_adapter.py tests/test_snapshot_visibility.py tests/test_boundary_snapshot.py -q -p no:cacheprovider
```

结果：`21 passed, 3 subtests passed`。由于 W1 未产生 protocol lock，本阶段没有生成正式 snapshot 或 NER formal 输入。
