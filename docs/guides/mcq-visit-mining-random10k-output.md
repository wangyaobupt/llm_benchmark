# 挖掘产物目录说明（random10k_dev20_strict_v1.0.0）

本地数据目录（gitignore，不入库）：

`data/derived/mcq_visit_mining/random10k_dev20_strict_v1.0.0/`

该目录内有一份同样内容的 [`生成说明.md`](../../data/derived/mcq_visit_mining/random10k_dev20_strict_v1.0.0/生成说明.md)，打开数据文件夹即可读。下面是入库副本。

结果数字见 [`docs/reports/mcq-visit-mining-random10k-acceptance.md`](../reports/mcq-visit-mining-random10k-acceptance.md)。运行命令见 [`mcq-visit-timeline-mining.md`](mcq-visit-timeline-mining.md)。

---

## 这是什么

V3 五类题型、**10,000 例** Visit、**strict** 门槛的规则挖掘输出。六个家族各一个子目录，全部 `status=complete`。`exploratory_unreviewed`，**`gold = 0`**。不是病历全文，不是题目。

目录名：`random10k` = 1 万例；`dev20` = 患者开发池 20%（哈希桶 0–19）；`strict` = 8 道正式统计门；`v1.0.0` = 本轮输出版本。

## 输入（只读）

```text
data/derived/mcq_visit_timeline/random10k_dev20_v1.0.0/
    presentation_facts.jsonl   → X
    visit_events.parquet       → 题型①②③ 的窗口内事件
```

不读 `visit_timelines.jsonl`，不读抽取/标准化里的出院小结。

## 子目录

| 文件夹 | 题型 | 窗口 |
|---|---|---|
| `type1_investigation` | ① 检查检验 | 就诊后 4h |
| `type2_diagnosis` | ② 诊断（出院 ICD，后验） | 24h 可见结果 |
| `type3_medication` | ③ 用药 | 处方 24h |
| `type3_procedure` | ③ 操作 | 日历日 24h |
| `type4_service` | ④ 科室 | Visit 级 |
| `type5_disposition` | ⑤ 离院去向 | Visit 级 |

每家文件：`mining_manifest.json`、`summary.json`、`catalog_snapshot.json`、`visit_transactions.jsonl`（含 `hadm_id`，勿提交）、`conditional_rules.jsonl`、`conditional_rules_rejected.jsonl`、`report.html`。

操作家族 `conditional_rules.jsonl` 长度为 0 表示 accepted=0，不是生成失败。

## 计数

accepted 合计 600（① 30 / ② 2 / 用药 154 / 操作 0 / ④ 353 / ⑤ 61）。② 的 2 条是 morbid obesity 同义反复，不能当诊断题种子。

## 不要做的事

不要当 gold、不要出题、不要改门槛覆盖本目录、不要把六家事务拼成一张表再挖、不要把 `visit_transactions.jsonl` 送外部模型。
