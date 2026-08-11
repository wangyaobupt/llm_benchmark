# MIMIC 数据处理管道

本目录按数据从原始表到临床事件模型的顺序，集中维护项目的数据层实现：

```text
Parquet/CSV 原始表
    ↓ parquet_to_jsonl
结构化 JSONL
    ↓ mimic_raw_archive
Admission 原始归档
    ↓ clean_clinical_archive
字典解码与 POE 临床可读归档
    ↓ mimic_episode
Episode 事件模型
```

## 模块

- `parquet_to_jsonl/`：源表格式转换、visit 组装和决策快照；
- `mimic_raw_archive/`：按 admission 聚合 HOSP、ICU、ED、NOTE 原始表；
- `mimic_dictionary/`：从授权 MIMIC 文件构建官方编码字典；
- `clean_clinical_archive/`：使用包内字典完成编码解码和 POE 解析；
- `mimic_episode/`：将原生记录组织为 episode 和事件输出。

`clean_clinical_archive/` 保持可单独复制运行。其 `dictionaries/` 是本地授权资源，受 `.gitignore` 保护，不随 Git 分发。

## 统一入口

在项目根目录使用完整模块路径：

```powershell
python -m data_pipeline.mimic_dictionary
python -m data_pipeline.mimic_raw_archive --help
python -m data_pipeline.clean_clinical_archive --help
python -m data_pipeline.mimic_episode --help
```

模块间依赖必须通过 `data_pipeline` 包路径或同一子包的相对导入表达，不再依赖项目根目录下的同名包。
