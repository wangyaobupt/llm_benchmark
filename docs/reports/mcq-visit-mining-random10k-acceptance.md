# 出题 Visit 规则挖掘验收（10,000 例，strict）

> 日期：2026-08-20  
> 输入：`data/derived/mcq_visit_timeline/random10k_dev20_v1.0.0/`  
> 输出：`data/derived/mcq_visit_mining/random10k_dev20_strict_v1.0.0/<family>/`  
> 状态：`exploratory_unreviewed`；`gold = 0`  
> 本文件不含病历原文、不含 `hadm_id`。

六个家族都已 `status=complete`。挖掘读 `presentation_facts.jsonl` + `visit_events.parquet`，不读 `visit_timelines.jsonl`。不出题。

## 总表

| 家族 | 窗口 | 有 y 的 Visit | 测过的 X→y | accepted | rejected | 主要卡关 |
|---|---|---:|---:|---:|---:|---|
| ① 检查检验 `type1_investigation` | 就诊后 4h | 5,611 | 54,309 | **30** | 2,346 | 概率不够 / Wilson / 只有一个 y |
| ② 诊断 `type2_diagnosis` | 24h 可见结果 + 出院 ICD（后验） | 10,000 | 4,748,951 | **2** | 43,801 | 诊断太碎；两条还是同义反复 |
| ③ 用药 `type3_medication` | 处方 24h | 9,732 | 597,742 | **154** | 6,715 | FDR / 与第二名分不开 |
| ③ 操作 `type3_procedure` | 日历日 24h（date） | 4,268 | 54,296 | **0** | 388 | 操作稀疏 + 日期精度 + 门槛 |
| ④ 科室 `type4_service` | Visit 级 | 10,000 | 17,196 | **353** | 4,353 | 基线是 Medicine |
| ⑤ 离院去向 `type5_disposition` | Visit 级，只要结构化去向 | 8,541 | 19,895 | **61** | 3,327 | 基线是 HOME |

合计 accepted **600**，rejected **60,930**。都不是 gold。

## 各家族读法

### ① 检查检验（30）

4 小时首波 + 高信号化验/影像/心内开单，避开了 CBC/BMP 基线陷阱。27 条答案是胸片（便携 AP 18、正侧位 9），另有 2 条 CT 头、1 条脂肪酶。

有临床形状的例子（统计关联，不是指南）：

- 腹痛 + 右侧腹痛 → 脂肪酶（n_x=9，lift≈15）
- 80 岁观察 + 精神状态改变 → CT 头
- 呼吸窘迫 + 气促 → 便携胸片（lift≈11）

代价：只有 56% Visit 在 4h 窗口里撞上目录内检查；accepted 的 n_x 中位约 21，偏小。

### ② 临床诊断（2）

出院主诊断 2,829 种，几乎一人一码，strict 下过不了支持度/区分度。仅有的 2 条都是「主诉 morbid obesity → 出院诊断 morbid obesity」，等于把同一句话当 X 又当 y。`standard_diagnosis_name` 在 facts 里是对象不是纯字符串，同名过滤没挡住。**这两条不能当诊断题种子。** 本家族整体标了 `discharge_icd_posthoc`。

### ③ 用药（154）

覆盖最好（97% Visit 窗口内有处方）。Heparin 占 accepted 的 94/154（约 61%），是预防性抗凝的高基线，类似旧链里的 CBC。更有区分度的是：

- 癫痫 → 左乙拉西坦（lift≈20）
- 水肿 + 气促 → 呋塞米
- 主诉 STEMI → 阿托伐他汀（n_x 很小）

Heparin 规则要单独看待，不能直接铺成「下一步开肝素」题。

### ③ 操作（0）

合法：4,268 例窗口内有操作，但 ICD 操作 2,176 种、时间只有日期，过不了 8 道门。本轮不要从操作家族出题。

### ④ 转诊科室（353）

y 只有 17 个科室码，所以过线最多。其中 **Medicine 约 308/353**，是住院内科基线，lift 往往贴门槛。真正抬起来的是专科：阴道出血→产科、髋/膝痛→骨科、硬膜下→神经外科。看规则时按答案科室筛，不要按条数以为内科转诊已经挖透。

### ⑤ 离院去向（61）

只要结构化 `discharge_location`。HOME 51/61。有信号的是：急诊 + 80 岁 + 跌倒 → 护理机构（SNF，n_x=70，lift≈4.9）。出院指导句子本轮没挖（无 NER）。

## 共同结论

1. 六个家族都跑通，隔离合同（① 无诊断/结果进 X）在产物快照里写着。
2. Strict 门槛在「高基线答案」（胸片、肝素、内科、回家）和「过碎答案」（ICD 诊断/操作）两端都会大量淘汰——这是门槛在工作，不是抽取失败。
3. 能当后续出题种子的，优先看 ① 里非单纯胸片、③ 里非肝素、④ 里非 Medicine、⑤ 里 SNF 那几条；②③操作不要进题。
4. 仍禁止：把 600 条 accepted 当 gold、调门槛覆盖同一目录、本轮出 A–D 题。

机器计数见同目录 `mcq-visit-mining-random10k-acceptance.json`。
