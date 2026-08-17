# Visit archive P0 验证报告

## 结论

新的 `mimic_visit_archive` 1.0.0 已完成代码实现、合成 fixture 回归、100 episode 小样本和 1,000 episode 扩展验证。扩展候选中写出 983 条，冻结 schema 不合格 0 条，患者级 development/final_test 冲突 0 条，所有 `status=ready` 的决策快照均通过未来信息与后验信息泄漏检查。

本报告证明 P0 修复链路可运行，不代表 320,267 visits 已完成全量重抽取。现有 29GB JSONL 仍是 legacy 产物；在新全量产物通过相同验证前不能替换。

## P0 修复验证

| 修复项 | 真实样本结果 |
|---|---:|
| 有 ED triage 主诉 | 472 / 983 |
| 有出院小结回顾性主诉 | 967 / 983 |
| 有 POE | 982 / 983 |
| 有 POE detail | 982 / 983 |
| 有 eMAR detail | 480 / 983 |
| 有 episode 前 OMR baseline | 656 / 983 |
| 有 ED disposition | 472 / 983 |
| 有完整 ICU metadata | 181 / 983 |
| 有派生 cardiology evidence | 576 / 983 |
| 有派生 respiratory evidence | 769 / 983 |

这里的“有”是病例级非空覆盖，不要求所有病例都必须包含该类临床事件。cardiology/respiratory 不再是硬编码空数组，而是保留来源事件引用的专科证据视图。

## 五类决策快照

| 题型 | ready / 983 | evidence refs |
|---|---:|---:|
| 检查选择 | 982 | 3,312 |
| 临床诊断 | 470 | 30,953 |
| 治疗处置 | 983 | 18,902 |
| 转诊科室 | 983 | 26,311 |
| 离院随访 | 983 | 345,840 |

临床诊断只有 470 条 ready，是因为当前 gold 定义为同期 ED diagnosis；没有 ED diagnosis 的病例被标为 `excluded_missing_outcome`。不能用出院 ICD 补齐，因为 ICD 编码是后验资料。

每个 ready snapshot 已逐条验证：

- evidence 必须有明确 `available_time`；
- `available_time <= cutoff_time`；
- `evidence_phase=post_hoc` 不得进入；
- gold 只保存在 `hidden_outcome`，不复制到可见 evidence。

## 数据体积影响

扩展样本 983 条共 420.0MB，平均 448KB/visit；legacy 基线约 89.6KB/visit。增量主要来自 POE detail、eMAR detail 和快照 evidence 引用。若简单线性外推，全量体积约 140–145GB，但仍只能用于磁盘与运行窗口规划，不能作为最终产物指标。

## 验证证据

- 合成 fixture + episode pipeline：20/20 通过。
- 全仓库 `unittest discover`：43 项中 41 项通过，2 项既有旧管线错误。
- 旧错误 1：旧清洗客户端初始化读取 SOCKS 代理，但环境缺少 `socksio`。
- 旧错误 2：旧标准化测试导入不存在的 `rwd_pipeline.standardization.common`。
- 100 episode 聚合指标：[visit-archive-p0-validation.json](visit-archive-p0-validation.json)
- 1,000 episode 聚合指标：[visit-archive-expanded-validation.json](visit-archive-expanded-validation.json)
- 扩展样本 SHA-256：`24BC9047900D645F5FCE31A44104EA87217DCFA49B830BF633E5CBFA921E8E59`

真实样本位于本地 Git 忽略目录 `data/validation/`，不进入仓库。

## 全量重抽取门禁

1. 预留至少 180GB 临时与产物空间；最终空间按 1,000 条扩展样本重新估计。
2. 1,000 episode 扩展验证已通过。
3. 全量写入临时路径，运行 streaming schema/leakage validator。
4. 只有 `invalid_records=0`、`patient_partition_conflicts=0` 且所有 ready snapshot 无泄漏时，才原子替换 legacy 主文件。
