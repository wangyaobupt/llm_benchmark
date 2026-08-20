# 出题 Visit 标准化验收（10,000 例）

> 日期：2026-08-20  
> 映射版本：`mcq-visit-standardize/1.0.0`  
> 状态：`exploratory_unreviewed`；`gold = 0`  
> 输入：`data/derived/mcq_visit_extract/random10k_dev20/visits.json`（只读）  
> 输出：`data/derived/mcq_visit_standardize/random10k_dev20_v1.0.0/`  
> 机器指标：同目录 `acceptance.json`；本文件不含患者原文。

## 结论

标准化已对 10,000 行跑完。原 45 列与抽取文件逐字段保留；派生列增加主诉概念、体温摄氏、检验/药物/科室标准名。未过审核的术语进入 `review_queue.jsonl`，**不得当 gold、不得单独当标准答案键**。

试点 100 例同步产物：`data/derived/mcq_visit_standardize/pilot100_dev20_v1.0.0/`。

## 计数

| 指标 | 试点 100 | 正式 10,000 |
|---|---:|---:|
| 行数 / 唯一 hadm_id | 100 / 100 | 10,000 / 10,000 |
| 原列未改写 | 是 | 是 |
| 主诉切出概念数 | 147 | 14,312 |
| 主诉概念 mapped 比例 | 0.3741 | 0.3538 |
| 体温 °F→°C 且可逆 | 43 / 43 | 4,307 / 4,307 |
| review_queue 行 | 823 | 16,173 |
| term inventory 行 | 2,068 | 28,914 |
| 标准化 JSON | — | 921.23 MiB |
| 标准化 CSV | — | 1005.73 MiB |

完整 SHA-256 见 `docs/reports/mcq-visit-standardize-random10k-acceptance.json`。

## 仍未完成

- 主诉约 65% 概念仍是 `unresolved`（长句、少见缩写、未进种子同义词表）。
- 药物/过敏大量商品名在种子表外，进审核队列。
- 未做 HPI 全文症状抽取，未调 LLM。
- 非正式金标准。
