# 状态—因子 Stage 0–6 状态机 V2 白皮书

## V2 修复什么

V1 正确要求股票截面行不得冒充全局状态 episode，但错误地把 `S_obs` 的 episode 支持进一步编译成 `discrete_operator_expert` 权限。V2 将外部条件研究与潜动力容量研究拆开：Stage3–5 管输入内容，Stage6+ 才管模型学习的 operator。

V1 保持历史可查，但不再拥有 REAKA current 规范权。

## Stage 0–6

| Stage | 对象 | 必须产出 | 本阶段无权产出 |
|---:|---|---|---|
| 0 | 产品/时钟/证据边界 | target、horizon、cadence、universe、cost、data usage | 因子或模型胜负 |
| 1 | 因子 | 单一 PIT 效力画像与多重性 | 状态或 K 标签 |
| 2 | 因子三出口 | 长期、条件、可跟随证据 | 重复输入身份 |
| 3 | `S_obs` | scope、PIT、episode、转移、持续、占比、时间/截面支持 | `K_i`、K2/K3 权限、`N_effective` |
| 4 | `S_obs×factor` | 机制、active episode、年度/episode 分布、顾问回执 | 潜状态命名、operator 标签 |
| 5 | 输入装配 | `S_obs` 进入 `H_x`/gate/交互的方式、自由度、回退 | 手工 K 映射、有效 K 数量 |
| 6 | 模型与容量 | 从头训练、K1→K2→K3、矩阵/selector/归属、容量证据 | 用外部状态数量替代训练 |

## Stage3 的精确作用

Stage3 的 episode 数量用于判断外部条件效应是否需要收缩、连续化或只作诊断。它不等于 selector 的软占用 `n_k_eff`，也不等于潜空间 operator 的有效转移数。Stage3 certificate 统一改名为 `observable_context_support_certificate`。

允许的 Stage3 终态：

- `observable_context_ready_for_stage4`；
- `observable_context_requires_continuous_or_shrunk_pairing`；
- `observable_context_diagnostic_only`；
- `observable_context_data_blocked`；
- `observable_context_financial_review_pending`。

这些状态只约束 Stage4 条件研究，不约束 `N_max` 或 `N_effective`。

## K 容量的唯一权威

数学主控在训练前冻结有界 `N_max` 和停止规则；模型分别学习候选 codebook 的 `K_i` 与 selector；训练后的 operator 差异、软支撑、扰动、多 seed 和金融排序证据逐级选择 `N_effective`。K2 失败必须归因到信息、episode/support、表示、目标/优化或无增量，禁止写成市场单状态。

## 回退规则

状态定义改变仍然从 Stage3 重开，因为 `S_obs` 输入身份和条件证据变了；它不意味着 Stage3 接管 K 数量。Stage3→4→5完成后，Stage6 从新 checkpoint 重训，再启动 operator 容量准入。
