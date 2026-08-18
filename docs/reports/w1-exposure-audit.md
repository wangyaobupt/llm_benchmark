# W1 exposure audit

状态：`failed`，原因码：`SPLIT_NO_UNEXPOSED_FORMAL_SUBJECTS`。

正式数据源固定为：

`G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet`

审计结果：

| 项目 | 数量 |
|---|---:|
| 正式事件源主体 | 20,136 |
| 旧 split 主体 | 20,136 |
| 旧 development | 12,082 |
| 旧 validation（已审计） | 4,027 |
| 旧 final-test（已查看） | 4,027 |
| `previous_exposure=none` | 0 |

结论：W1 不得生成新的 formal validation/final-test，也不得把旧 validation/final-test 升级。`protocol.yaml` 保持 `draft`，`protocol-lock.json` 不生成。审计可由以下命令重放：

```powershell
.\.venv\Scripts\python.exe scripts\build_w1_exposure_registry.py
```

机器可读输出位于被 `.gitignore` 忽略的 `data/derived/investigation_selection/w1/exposure-audit.json`；该文件不包含患者级原始数据。
