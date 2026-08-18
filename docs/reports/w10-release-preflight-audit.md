# W10 发布前审计与 final-test 演练

## 项目模式

本项目当前明确为 `exploratory-only`。现有 20,136 个主体全部出现在旧 split，不能从中伪造新的独立 final-test。因此正式 final-test 尚未运行，也没有正式 final-test 指标或 gold 增量。

## 已实现的两种运行模式

### `rehearsal`

用于摸通流程，只接受 `fixture:` 前缀的合成主体。它可以验证：

- development/validation/final-test 主体互斥；
- artifact、split 和主体清单 hash 生成；
- final-test 单次运行记录；
- 指标不回流调参；
- `official_final_test=false`；
- `gold_mutated=false`。

运行命令：

```powershell
python scripts\run_final_test_rehearsal.py
```

### `official`

只有在 protocol frozen、protocol lock 存在、旧暴露之外的新 final-test 主体已证明、三组主体互斥且全部 artifact manifest 冻结后才允许运行。正式运行只允许一次，且不允许调参回流。

## 验证

```text
tests/investigation_selection/test_release_preflight.py
4 passed
python scripts\run_final_test_rehearsal.py
exit code 0
```

演练输出不进入 gold、不改变正式协议，也不代表 benchmark 已完成 final-test。
