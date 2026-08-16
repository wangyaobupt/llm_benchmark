# benchmark_common — 共享基础设施

各评测任务（检查检验选择、临床诊断，以及后续治疗/转诊/离院）共用的基础代码。

## 模块

| 模块 | 内容 |
|---|---|
| `conditions.py` | 主诉归一化与抽取：`normalize_condition`、`extract_conditions`、同义词表、垃圾黑名单 |
| `stats.py` | 统计：`wilson_lower`、`binomial_greater_pvalue`、`benjamini_hochberg` |
| `io.py` | 哈希与 fail-closed 输入校验：`_sha256_file`、`_verify_normalized_events` |

## 使用

任务代码通过 `sys.path.insert(0, project_root)` 后 `from benchmark_common import ...` 导入。各任务包的 `pipeline.py` / `diagnosis.py` 已内置此引导。

```python
from benchmark_common import (
    extract_conditions, _verify_normalized_events, _sha256_file,
    wilson_lower, binomial_greater_pvalue, benjamini_hochberg,
)
```

## 设计约定

- 患者级划分（`subject_split.parquet`）是所有任务共用的，位于 `tasks/investigation_selection/output/split/`（后续可上移到更中性位置）。
- 主诉归一化词表（同义词 + 黑名单）是冻结待办，当前为占位。
- 新增第 3/4/5 个任务时，直接复用本包，不要从某个任务包反向 import。
