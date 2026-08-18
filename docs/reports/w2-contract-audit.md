# W2 合同级审计

状态：`engineering_contract_passed`；正式运行：`blocked_by_W1_protocol_lock`。

已实现：

- `data_pipeline/investigation_selection/encounter_clock.py`：分别保留 ED arrival、ED registration、hospital admit、discharge；多 ED、缺失 origin、时间倒置均 fail-closed。
- `data_pipeline/investigation_selection/source_grouping.py`：普通检验使用 `specimen_id`，微生物使用 `micro_specimen_id`，医嘱使用 `poe_id`；缺少分组键产生 `SPECIMEN_GROUP_MISSING`。
- 不生成或推断 `specimen_received_time`；`charttime`、`storetime` 只作为源字段保留。

离线验收命令：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest tests/investigation_selection/test_encounter_clock.py tests/investigation_selection/test_time_semantics.py tests/test_evaluation_protocol.py tests/test_subject_split.py -q -p no:cacheprovider
```

结果：`31 passed, 2 subtests passed`。正式 W2 产物必须等待 W1 的新 formal exposure 和 protocol lock；旧 split 不得回收。
