# 全患者与冠状动脉疾病谱原始归档规模估算

## 1. 结论

| 范围 | 患者数 | 住院数 | 预计最终JSONL | 预计磁盘峰值 | 预计耗时 | 判断 |
|---|---:|---:|---:|---:|---:|---|
| 全部MIMIC-IV住院 | 223,452 | 546,028 | 172.9 GiB（约145–210） | 351.8 GiB（约295–430） | 60–100分钟 | 当前G盘可运行但安全余量不足，不建议立即执行 |
| 冠状动脉疾病谱相关住院 | 46,062 | 108,833 | 51.7 GiB（约42–65） | 105.3 GiB（约85–132） | 20–40分钟 | 推荐先执行 |
| 疾病谱患者的所有住院 | 46,062 | 168,473 | 不作为当前目标 | 不作为当前目标 | 不作为当前目标 | 会引入59,640次未命中疾病谱编码的其他住院 |

当前G盘可用空间为441.52 GiB。磁盘峰值包含 staging、JSONL分片和合并后的最终JSONL；分片在验收前不删除。

## 2. 队列定义

- ICD-9：410–414。
- ICD-10：I20–I25。
- 包含稳定性冠心病、冠状动脉粥样硬化、不稳定型心绞痛、心肌梗死及其他ACS。
- 不纳入全身或外周动脉粥样硬化440/I70。
- 编码只用于离线选取住院，不写入raw JSON顶层，也不作为模型决策时点输入。
- 入选后保存该次住院全部32张纳入表数据，不裁剪为心血管字段。

准确统计：166,211条诊断编码命中，共覆盖108,833次住院、46,062名患者。主诊断命中19,819次住院；至少一条次诊断命中103,481次住院，两组存在重叠。

| ICD版本 | 诊断行 | 住院数 | 患者数 |
|---|---:|---:|---:|
| ICD-9 | 83,176 | 54,450 | 24,694 |
| ICD-10 | 83,035 | 54,385 | 27,097 |

## 3. 估算依据

10,000次住院验证运行的实测结果：

- 最终JSONL：3.166 GiB。
- 总耗时：356.4秒。
- 全体平均：331.98 KiB/住院。
- 样本中冠状动脉疾病谱：1,938次住院、1,611名患者。
- 疾病谱平均：498.50 KiB/住院，是总体平均的1.502倍。
- 疾病谱P50：210.76 KiB；P95：1.675 MiB。

时间估算没有直接把5分57秒乘以住院倍数，而是拆分为：

1. 全部32张gzip源表扫描，主要是固定成本；
2. staging结果写入，随入选事件量增长；
3. 每1,000次住院的分片组装，近似随输出体积增长；
4. 最终JSONL合并，随输出字节数增长。

全量提取的主要瓶颈将从源表扫描转为约546个分片的组装和约173 GiB文件合并。疾病谱提取约109个分片，规模和磁盘风险明显更可控。

## 4. 患者隔离

疾病谱selection已经按`subject_id`哈希分区：

| 分区 | 住院数 |
|---|---:|
| development | 21,577 |
| final_test | 87,256 |

同一患者不会跨分区。分区字段只存在外部selection manifest，不进入原始住院JSON。

selection文件位于：

```text
G:\Projects\llm_benchmark\data\cohorts\coronary-disease-spectrum-selection.jsonl
```

SHA-256：`1E4E2502D28D7018C12FDBEFEFD50E7CEEEE3FB5425B87E79C18B70ADE9845DE`

## 5. 推荐执行命令

规模确认后，使用独立目标目录启动，不覆盖当前10,000例：

```powershell
.venv\Scripts\python.exe -m data_pipeline.mimic_raw_archive `
  --selection-input "G:\Projects\llm_benchmark\data\cohorts\coronary-disease-spectrum-selection.jsonl" `
  --output-dir "G:\Projects\llm_benchmark\data\validation\mimic-admission-raw-coronary" `
  --merged-output "G:\Projects\llm_benchmark\data\validation\mimic-admission-raw-coronary.jsonl" `
  --shard-size 1000 --workers 2 --duckdb-threads 4
```

外部selection行数由命令行自动读取，无需手工填写`--sample-size`。正式运行前仍需单独确认。
