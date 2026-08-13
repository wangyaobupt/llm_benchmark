# Text NER DeepSeek API 成本与合规评估

结论：**成本可估算，但当前禁止把受限MIMIC文本发送到DeepSeek API。**

## 输入与执行状态

- calibration文本单元：171
- section原文字符数：34293
- 来源分布：`{"ed.triage": 25, "note.radiology": 146}`
- evaluation访问：0
- 模型调用：0

## 费用情景（人民币）

| 情景 | 模型 | 全部输入未命中缓存 | 重复提示词理想命中 | 估算总tokens |
|---|---|---:|---:|---:|
| `lean` | `deepseek-v4-flash` | 0.180957 | 0.109735 | 148125 |
| `lean` | `deepseek-v4-pro` | 0.542871 | 0.326663 | 148125 |
| `planning` | `deepseek-v4-flash` | 0.443613 | 0.372391 | 312285 |
| `planning` | `deepseek-v4-pro` | 1.330839 | 1.114631 | 312285 |
| `stress` | `deepseek-v4-flash` | 1.144029 | 1.072808 | 750045 |
| `stress` | `deepseek-v4-pro` | 3.432087 | 3.215879 | 750045 |

费用是规划情景，不是账单：英文字符按DeepSeek官方约0.3 token估算；输出token是假设值，真实调用后必须用API `usage`重算。缓存理想值也不保证实际命中。

## 合规判断

PhysioNet要求第三方API具备零数据保留、不训练、无人审；若无法完整验证则不得使用。DeepSeek现行隐私政策说明会收集输入，并可能为服务、研发、安全等目的保留，未提供本项目可核验的零保留承诺。因此：

- `restricted_mimic`在代码中硬阻断；
- API key、base URL或其他环境变量均不能解除阻断；
- 适配器只能对合成文本或公开非临床文本进行模拟/接口测试；
- 若未来获得满足PhysioNet要求的DeepSeek企业零保留协议，必须重新审查并升级政策版本，不能直接改环境变量。

## 官方依据

- [PhysioNet：LLM与在线服务使用要求](https://physionet.org/news/post/llm-responsible-use/)
- [DeepSeek隐私政策](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html)
- [DeepSeek模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing)
- [DeepSeek token估算说明](https://api-docs.deepseek.com/quick_start/token_usage/)
