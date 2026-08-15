# Text NER API HTML 监测验收

## 结论

HTML 监测接口验收通过。`monitor-openai-compatible-api --watch` 每10秒增量读取 response/audit JSONL，并原子更新自包含 HTML；监测器本身不调用模型、不读取 `.env`，也不把临床正文、实体内容、API key 或具体 request ID 写进页面。

## 监测口径

- 已完成数取 response 与 audit 唯一 request ID 的交集，避免单边写入被误算为成功。
- 同时报告单边 request ID、重复 ID、无效 JSONL、token usage 和模型 provenance。
- 近5分钟速度只根据监测进程启动后的增量计算；没有至少两个有效样本时不伪造 ETA。
- 结果文件超过300秒没有新增时标记为“可能停滞”，但不把文件静止错误解释为进程已经退出。
- HTML 自带10秒刷新；如果监测进程停止、HTML 超过30秒未重写，页面显示监测器停止提示。

## 验收证据

| 检查项 | 结果 |
|---|---:|
| HTML meta refresh | 10秒 |
| 增量 JSONL 读取 | passed |
| response/audit 交集计数 | passed |
| 单边写入、重复 ID、无效 JSONL检测 | passed |
| 临床正文和具体 request ID 不进入 HTML | passed |
| 原子 HTML 替换与 Ctrl+C 停止 | passed |
| API monitor 专项测试 | 3 passed, 0 failed |
| Text NER、API monitor 与 aggregation 完整测试 | 43 passed, 0 failed |
| 监测器触发模型调用 | 0 |

## 当前页面快照

2026-08-15 13:10:10 +08:00 生成的 mention 页面观察到：

- 共同完成：1 / 64,509；
- response/audit：1 / 1，无单边记录、重复 ID 或无效 JSONL；
- 最近结果写入：2026-08-15 13:05:04 +08:00；
- provider/model：DeepSeek / `deepseek-v4-flash` / `DeepSeek-V4-Flash`；
- usage：prompt 1,099、completion 2,518、total 3,617 tokens；
- 页面生成时超过300秒无新增，因此状态为“可能停滞”。

这1条是监测器启动前已经存在的模型响应；本次监测实现没有发出模型请求。实时状态以 Git 忽略目录中的 `model_execution/mention_monitor.html` 为准，本报告只记录验收时快照。
