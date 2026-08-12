# Event pipeline 模块化验收报告

## 结论

`data_pipeline/event_pipeline` 已按功能拆为共享合同、事件化、确定性归一化、质量门禁和只读查看五个子目录；根目录只保留公开接口、唯一命令入口、总工作流和说明文档。

新的 `run` 命令已用真实 100 例完成以下完整链路：

```text
cleaning
→ cleaning 独立审计
→ normalization
→ normalization 独立审计
→ 不同 batch size 完整复跑
→ SHA-256、run ID 和计数比较
→ 原子发布
```

全部门禁通过，结构重构没有改变现有临床数据语义或数据文件字节。

## 目录边界

```text
data_pipeline/event_pipeline/
├── __init__.py
├── __main__.py
├── workflow.py
├── README.md
├── event_contracts/
├── event_cleaning/
├── event_normalization/
├── event_quality/
└── event_viewer/
```

- `event_contracts`：共享 Arrow/JSON schema 和状态值；
- `event_cleaning`：33 张源表合同、原生键、时间语义和事件化；
- `event_normalization`：有效源编码、冻结同义词和单位规则；
- `event_quality`：两层独立审计、三批回归和复现比较；
- `event_viewer`：同时查看 cleaning 与 normalization 的只读界面；
- 根级 `workflow.py`：固定执行顺序、失败门禁和原子发布。

原 1,144 行 `transformers.py` 已拆为 `common.py`、ED、检验、医嘱、药物、诊断操作、ICU、Note 八个模块和唯一 `registry.py`。根目录不存在旧实现或重复路由表。

## 唯一总入口

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline run `
  NEW-BATCH-clinical-readable.jsonl `
  --raw-source-jsonl NEW-BATCH-raw.jsonl `
  --output-dir data\derived\event_pipeline_NEW_BATCH
```

运行失败时不发布正式输出目录；cleaning audit 未通过时不会执行 normalization。Viewer 和回归仍由同一个根入口的 `view`、`regression` 子命令调用。

质量报告中的内部产物路径使用相对路径，输入以文件名和 SHA-256 标识；同一输入换一个输出目录，`workflow_manifest.json` 和质量报告哈希保持一致。

## 100 例字节级复验

正式运行 batch size 为 5,000，复跑 batch size 为 777。两次运行的全部数据文件、run ID 和计数一致。

| 项目 | 重构后结果 | 与基线 |
|---|---|---|
| cleaning run ID | `603d1f38f9a9975b42f30797` | 一致 |
| normalization run ID | `e15597823e4e268e1f8baf30` | 一致 |
| admissions | 100 | 一致 |
| cleaned events | 66,652 | 一致 |
| rejected | 43 | 一致 |
| term inventory | 3,895 | 一致 |
| normalized events | 66,652 | 一致 |
| review queue | 1,001 | 一致 |

核心 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `cleaned_events.parquet` | `bda93a98cf50f8de8961d7c6883e2e401f0c38618c83c08d7074fef5072997bb` |
| `cleaning_rejected.parquet` | `a571c5b8dec6d3fbf64910923b03e4007335ca4f493e42a3856a686584c8c8fe` |
| `encounter_manifest.parquet` | `8d90a4eada2237535a4767a96785bc1c5f2886a0951790b3d34b1f8ca179e4dc` |
| `term_inventory.parquet` | `d88dca8d27c7530a2d98156c684eda9b51edb992aecbe6641413b45405f00f69` |
| `source_reconciliation.json` | `a51dacc8a59a0b7d1984a4558105a06e65bc68d2f4e53d2d2ec82d48b72f9dad` |
| `normalized_events.parquet` | `50698a7cf988c98a1b0efc27a404ad37d7f054f7c3d6c28810dfe65a49647ed4` |
| `normalization_mappings.parquet` | `e7be0e83ecf51abfdde7fb612d20e3a9925eb999cfe6d8b4609c1dddc704c4c5` |
| `normalization_review_queue.parquet` | `57b373c15bfb42588b998c937c49d2312052161e7e7f17c56c709740f2439853` |

两层 audit 和 reproducibility report 的阻断列表均为空。

## 三批真实回归

三批均从源 JSONL 重新运行，不是只读取旧产物：

| 批次 | 事件数 | 结果 |
|---|---:|---|
| `sample_100` | 66,652 | 通过 |
| `random_1000_a` | 757,036 | 通过 |
| `random_1000_b` | 665,184 | 通过 |

三批的身份、时间、完整事件语义和拒绝语义均未漂移。

## 自动测试

- event 相关测试：35 项通过；
- 全仓测试：135 项中 133 项通过；
- 2 项既存错误与本次重构无关：旧 DeepSeek client 测试环境缺少 `socksio`，以及旧 `rwd_pipeline.standardization.common` 模块不存在。

新增门禁测试确认：

- 单一 workflow 命令能够完成全部阶段并发布 manifest；
- 不同 batch size 的结果一致；
- cleaning audit 失败时不发布输出且不进入 normalization；
- 完整 workflow 目录可被 Viewer 识别为 7 个数据集；
- 归一化修改非允许字段时独立 audit 会阻断。
