# Event contracts

本目录只定义 event 各阶段共享的数据交换合同：临床事件、术语清单、拒绝记录、住院清单、映射及审核队列的 Arrow schema，以及临床事件 JSON Schema 和冻结状态值。

本目录不读取数据、不生成事件、不执行映射。合同变化必须显式升级版本，并验证 cleaning、normalization、quality 和 viewer 全部消费者。
