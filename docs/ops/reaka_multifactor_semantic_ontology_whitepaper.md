# REAKA 多因子选股核心语义本体白皮书

## 一屏结论

本文件只定义对象、所有者和合法推论。它不保存单次结果，不选择参数，不开放训练。

```text
用户/项目输入 S_obs、因子、收益与执行语义
  -> encoder/gate 学习 Z
  -> selector 在有界 codebook 中选择/混合模型学习的 K_i
  -> 训练与可识别证据选择 N_effective
```

`S_obs` 与 `S_latent` 不是同一个对象；外部状态数量、episode 数量和 operator 数量没有一一映射。

## 对象与所有者

| 对象 | 形成方式 | 所有者 | 可以决定 | 不能决定 |
|---|---|---|---|---|
| 产品目标 | 用户冻结 target/horizon/cadence/universe/execution | 用户 | 金融问题身份 | 模型参数 |
| 因子 | PIT 数据与因子研究 | 项目+数据 | 输入候选与方向证据 | operator 标签 |
| `S_obs` | 用户金融假设+PIT 状态公式 | 用户+项目 | 条件输入身份 | `K_i`、`N_effective` |
| `S_factor` | 因子在 `S_obs` 内外的效力证据 | 数据研究 | 条件机制是否保留 | 潜状态名称 |
| `H_x/H_y` | 两路 encoder 输出 | 模型 | latent 融合材料 | 人工状态字典 |
| `Z/S_latent` | gate 后的潜表示 | 模型 | selector 的状态表示 | 宏观状态命名真值 |
| `K_i` | Koopman loss 下学习的矩阵 | 模型 | 潜空间一步动力 | 用户可填写特征 |
| `N_max` | 结果前有界容量边界 | 数学主控 | 最多尝试几个 operator | 有效 operator 数 |
| `N_effective` | K1→K2→K3 逐级训练与可识别证据 | 模型+证据 | 当前任务有效容量 | 市场永恒状态数 |
| residual | `Z_next-K_s Z` 的剩余结构 | 模型+证据 | 是否补充主动力 | 掩盖输入/K失败 |
| score | 冻结模型输出 | 模型 | 股票排序候选 | 自动获得账户权 |
| account | score+组合+成本+成交真值 | 账户审计 | 金融结果 | 反向重训模型 |

## REAKA 论文的精确边界

论文中 `a=SelectorNet(Z,H_y)`；训练用 Gumbel-Softmax 得到 `alpha_i`，形成 `K_s=sum(alpha_i K_i)`；推理用 argmax。论文没有用户命名状态接口，也没有披露 operator count `N`。FactorLab 把 `S_obs` 放入特征/条件路径属于项目适配，不能把它变成 operator supervision。

## 六条不可补偿不变量

1. `observable_state_equals_latent_operator_state=false`；
2. `user_supplies_operator_count=false`；
3. `model_learns_operator_matrices=true`；
4. `model_learns_operator_assignments=true`；
5. `stage3_may_select_operator_count=false`；
6. `effective_operator_count_is_post_training_evidence=true`。

附加不变量：`portfolio_top_k_is_operator_count=false`。任何文档、合同或结果违反其中一项，都失去 current 规范权。

## Stage 权限

- Stage3 只审计 `S_obs` 的 PIT、scope、episode、持续、转移和时间/截面支持；其 operator 裁决权限为零。
- Stage4 只审计 `S_obs×factor` 的金融机制、覆盖和跨期证据。
- Stage5 冻结 `S_obs` 怎样进入 `H_x`、gate、显式交互或风险上下文；不得给样本预填 operator 标签。
- Stage6 及其 operator-capacity 子流程才训练 `K_i` 与 selector，并逐级选择 `N_effective`。
- residual、SSA 和账户依次位于有效 K 身份冻结之后。

## 能证明与不能证明

外部状态 episode 少可以证明该状态的条件效应估计可能薄弱，也可能要求连续化、收缩或降为诊断；它不能单独证明 K2 不可识别。K2 训练失败可以证明当前输入、表示、目标或优化下没有识别出第二算子；它不能证明用户状态不存在，也不能证明市场只有一个状态。
