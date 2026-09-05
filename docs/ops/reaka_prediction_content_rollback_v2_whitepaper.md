# REAKA 预测内容改变后的 Stage 回退 V2 白皮书

## 核心修正

回退位置回答“哪些上游材料因输入身份改变而失效”，不是把下游对象的裁决权交给回退阶段。

| 改变 | 最早重开 | 失效内容 | 仍由谁决定 |
|---|---|---|---|
| 硬件、精度、求解器 | Stage5 参数闭包 | nuisance receipt | 模型数学不变 |
| latent/K/residual 模式 | Stage5/6 | 模型实例与 checkpoint | K 准入链决定有效 N |
| 因子×`S_obs` 机制 | Stage4 | 条件证据与 multiplicity | K 准入链决定有效 N |
| `S_obs` 定义、采样或 episode | Stage3 | 外部条件图鉴、配对和输入装配 | K 准入链决定有效 N |
| target/horizon/cadence/universe/因子身份 | Stage1/2 | 因子效力与全部下游 | K 准入链决定有效 N |

因此第二轮“只加状态”从 Stage3 开始是正确的；用 Stage3 外部 episode 数禁止 K2/K3 是错误的。Stage3→4→5只负责把新条件可靠地编译进输入；Stage6 从头重训后，模型与证据再选择 operator 数量。
