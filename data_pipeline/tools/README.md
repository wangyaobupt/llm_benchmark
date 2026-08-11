# 数据管道辅助工具

本目录存放不在每次主流程中执行的构建和维护工具。

`mimic_dictionary/` 从授权 MIMIC-IV 字典源表生成五份标准字典及查询文件。日常运行 `clean_clinical_archive` 时直接读取已经校验的包内字典，不需要重复构建。

```powershell
python -m data_pipeline.tools.mimic_dictionary --help
python -m data_pipeline.tools.mimic_dictionary.decode_archive --help
```
