# final_test 盲测报告（一次性，exploratory_unreviewed）

> 状态：**探索性未审核**。本报告记录 final_test 首次也是唯一一次被使用的盲测结果。
> 盲测语义：development gold（dev 派生的「最可能/最具选择性」答案）在 final_test 独立患者上的 rank-1 一致性。
> 这不是模型评测，而是 **gold 泛化性检查**——dev 学到的规则在从未见过的患者上是否仍然成立。

## 1. 盲测前提（fail-closed）

| 检查项 | 结果 |
|---|---|
| final_test 患者数 | 4,027 subject（7,727 住院，5,373,365 事件行） |
| 全仓库是否存在 `output/*/final_test/` 产物 | 无（grep 命中的均为源码/config/schema/docs 定义） |
| 结论 | test 集在此次盲测前**零接触** |

数据指纹：

- events SHA256: `69f29e310a53c980857dd8159b1f2e4cedfa823719754e116935d7d2751bb7cf`
- split SHA256: `80f9b4e213102e40abedf86b6c7fa5fe6498ba69d22222e4bc1f5d6e79471846`
- split 来源: `tasks/investigation_selection/output/split/subject_split.parquet`（60/20/20 患者级）

## 2. 盲测结果（development gold → final_test rank-1 一致性）

| 任务 | dev rules | checked | rank-1 | top-3 |
|---|---:|---:|---:|---:|
| 检查检验选择（investigation） | 295 | 140 | **69.29%** | 88.57% |
| ├ imaging | | 45 | 71.11% | 100.00% |
| ├ clinical_order | | 30 | 90.00% | 96.67% |
| └ laboratory | | 65 | 58.46% | 76.92% |
| 临床诊断（diagnosis, PSR） | 38 | 13 | **76.92%** | 76.92% |
| 治疗处置 T1 开立（medication_ordered） | 93 | 48 | **50.00%** | 77.08% |
| 治疗处置 T2 执行（eMAR） | 82 | 37 | **54.05%** | 75.68% |
| 治疗处置 T3 手术（procedures） | 68 | 51 | **47.06%** | 74.51% |
| 转诊与科室选择（referral） | 147 | 65 | **66.15%** | 84.62% |

> `checked` 显著少于 `dev rules` 是预期行为：final_test 只占 20% 患者，单病种下 `<10` 住院的规则被
> `min_condition_support` 挡掉（记为 `insufficient_support`），不参与一致性计算。

## 3. 泛化缺口（validation vs final_test）

| 任务 | validation rank-1 | final_test rank-1 | 缺口 |
|---|---:|---:|---:|
| investigation | 71.0% | 69.3% | −1.7pp |
| diagnosis | 85.7% | 76.9% | −8.8pp |
| treatment T1 | 56.5% | 50.0% | −6.5pp |
| treatment T2 | 62.2% | 54.1% | −8.2pp |
| treatment T3 | 59.6% | 47.1% | −12.5pp |
| referral | 61.5% | 66.2% | +4.7pp |

## 4. 解读（探索性，未经临床审核）

1. **检查/转诊最稳**（~66–69%，缺口 <5pp）：这两个任务答案是高先验、低基线的选择性答案，
   gold 在独立患者上稳定。
2. **诊断 n 过小**（13 checked），76.9% 不可当作最终结论，只能算方向性信号；主诊断 + PSR 的
   前 3 条 discordant 全是「同谱系相邻诊断」（胰腺炎 vs 脓毒症、呼吸窘迫 vs 心衰），属可接受的
   临床邻近，不一定是规则错。
3. **治疗三层最弱**（47–54%，且 T3 缺口 12.5pp）：治疗是品类级映射 + 三层事件叠放，选择性弱、
   品类粗，dev 的「最可能」在 test 上漂移明显。这印证了 summary 里的预判——治疗类 gold 的
   语义和品类粒度需要在临床审核轮里重点重构（或降级为「品类集合」多选题而非单选最可能）。
4. **laboratory 子类 58.5%** 是检查任务的主拖累：血检面板候选多、先验分散，单选「最可能」天然
   不稳；这与既有 gold 语义结论（检查任务用 selectivity）一致，但面板粒度仍需细化。

## 5. 可复现命令

```powershell
.\.venv\Scripts\python.exe tasks/investigation_selection/src/run_validation.py --role final_test
.\.venv\Scripts\python.exe tasks/clinical_diagnosis/src/run_validation.py --role final_test
.\.venv\Scripts\python.exe tasks/treatment/src/validate.py --layer t1 --role final_test
.\.venv\Scripts\python.exe tasks/treatment/src/validate.py --layer t2 --role final_test
.\.venv\Scripts\python.exe tasks/treatment/src/validate.py --layer t3 --role final_test
.\.venv\Scripts\python.exe tasks/referral/src/validate.py --role final_test
```

> 注意：final_test 已启用，后续任何参数/gold/阈值调整都**不得**再读 final_test 来调参。
> 如需迭代，只能在 development + validation 上做；final_test 仅保留为发布前的一次性复检。
