# MIMIC-IV 冠心病 100 个 admission：POE 可观察医嘱时间线验证

## 验证范围

- 输入：`data/validation/mimic-admission-raw-coronary-sample-100.jsonl`
- admission：100
- 原始 POE / 输出事件：12,773 / 12,773
- 解析方式：规则与显式键连接，不调用 LLM
- 官方语义依据：[MIMIC-IV v3.x POE 官方语义与时间线解析边界](../../data_pipeline/clean_clinical_archive/docs/mimic-poe-official-evidence.md)
- 完整机器指标：[mimic-poe-timeline-sample-metrics.json](mimic-poe-timeline-sample-metrics.json)

## 样本结论

### 1. POE 可以形成稳定的医嘱动作时间线

| 动作 | 数量 | 占比 |
|---|---:|---:|
| 新开 | 10,138 | 79.37% |
| 变更 | 1,388 | 10.87% |
| 停止 | 1,246 | 9.76% |
| 官方合法但语义未解释 | 1 | 0.01% |

2,634 个事件带前驱链接，其中 2,628 个在当前 admission 中找到目标，解析率 99.77%。另有 6 个前驱不在当前 admission 记录、10 个链接不完全双向、2 个前后类别不一致；解析器保留这些异常，不自动修补。唯一的 `H` 属于官方列出的合法事务代码，但官方没有解释其业务语义，因此输出为 `action=uninterpreted`，而不是错误地归为非法值或猜译为某个临床动作。

### 2. 不能只依赖 POE_DETAIL

- 只有 1,293 / 12,773（10.12%）事件带 POE_DETAIL；
- 4,050 / 12,773（31.71%）事件可连接处方；
- 合并主类型、子类型、POE_DETAIL 和处方后，9,525 / 12,773（74.57%）事件超越单纯类别：4,773 个达到具体药物实体，1,123 个有 detail 属性，3,629 个只有子类型；
- 仍有 3,248（25.43%）事件只有主类别。

因此，POEDETAIL 适合补充收治科室、复苏意愿、管路、会诊状态等属性；药物医嘱必须连接 `prescriptions/pharmacy` 才能获得药名、剂量、途径和频次。

`content_specificity` 描述内容具体到哪个层级，不表示临床置信度。药物字段完整度由 `medication_resolution` 分别统计。当前样本的 431 条 `Route` detail 是 v3.1 数据中的实际观察扩展；官方页面截至 v2.2 的字段列表未列出它，因此单独标记为 `observed_extension`，但不视为非法字段。

### 3. “Change”不一定能看到临床内容变化

1,388 个 `Change` 事件中，512 个（36.89%）可从当前可见字段观察到增量；876 个没有可观察内容差异。这不等于临床上没有变化，只说明当前 POE、POE_DETAIL、处方和药房字段不足以显示差异。

另有 76 个变更事件同时包含多条同名、同 `drug_type` 的药物记录，无法可靠进行逐字段一对一配对。解析器将其标为 `ambiguous_medication_pairing`，只报告药物记录组合发生变化，不生成可能错误的“剂量 A → B”结论。

## 可读事件示例

### 新开收治医嘱

```text
2154-02-05 19:01:17
新开入院、出院或转科医嘱，Admit，收治科室：Medicine
增量：新增收治到 Medicine
```

### 可观察到频次变化的用药医嘱

```text
2154-02-06 09:26:50
变更用药医嘱，Oxycodone SR (OxyconTIN)，40 mg，途径 PO，频次 QAM
增量：每日次数 2 → 1；给药频次 Q12H → QAM；计划起止时间发生变化
```

### 停止复合静脉用药

```text
2154-02-06 12:25:31
停止用药医嘱，Iso-Osmotic Dextrose 200 mL IV；Vancomycin 1000 mg IV，频次 Q48H
```

### 只有类别、不能还原具体检查

```text
2154-02-05 13:45:26
新开检验医嘱
质量标志：category_only_no_specific_order_content
```

这里不能写成“开具血常规”或其他具体项目，因为 POE 与 POE_DETAIL 没有提供该信息。

## 当前适用范围

当前输出可以用于：

- 住院内医嘱动作排序；
- 可见医嘱内容的新增、移除和字段变化；
- 变更/停止关系链；
- 下一步关联实际执行和结果的时间锚点。

当前输出不能单独用于断言：

- 医嘱已经执行；
- 药物已经实际给入；
- 检验或影像已经完成；
- POE 中只有 `Lab` 时具体开了哪个项目；
- 已还原完整 EHR 操作审计历史。

下一步应连接 eMAR、检验、影像、操作和 ICU 治疗事件，并把“下达意图—执行—结果”作为三个不同阶段保留。
