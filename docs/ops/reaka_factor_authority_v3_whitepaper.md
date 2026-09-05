# REAKA V3 论文主干与可选因子权限白皮书

日期：2026-08-26

机器合同：`docs/ops/reaka_factor_authority@3.0.json`

## 结论

REAKA 论文要求历史收益序列、个股特征序列、双路 LSTM/gate、潜状态、Koopman selector 和残差。它不要求 FactorLab 自建的两状态 transparent Context。

Context、行业、市值、风格和其他交互统一属于可选因子：

```text
有效 -> 可进入后续整案 ablation
无效 -> 只淘汰自己
任何候选因子 -> 不得成为论文主干、先验中性/方向约束或 Step7 阻断门
```

## 错误与纠偏

一号主控引入状态—因子透明 Context；二号主控继承；本任主控又把用户的因子化政策误写成 `transparent_core_frozen_as_neural_fidelity_reference=true`。

V3 不修改历史回执，而是用 `authority_correction_receipt.json` 撤销它们的当前衍生权限。V2/V2.1/V2.2 继续作为 Context 候选的负面材料，不得再解释为 REAKA 论文主干失败。

## 回滚点

```text
Step0--4  PIT/时钟/因子身份/H20任务对齐  -> 保留
Step5     把 Context 升格为联合核心       -> 失效，重做
Step6     强制保真 Context 增量             -> 失效，重做
Step7+                                            -> 从未合法开启
```

法定回滚点是 Step5 输入装配边界，不是 Step0，也不需重挖所有因子。

## 重执行结果

Step5 V3 仅冻结 `CORE_SPATIAL_H20` 48 因子与 `baseline_score`，Context 列读取 0，2009--2020 共 1,044,249 行。

Step6 V3 固定 h8/d8/K1/零残差/三种子/12周期，只对 baseline 做神经载体保真。三种子主要期排序相关为 `0.998679/0.998784/0.998364`，Top Jaccard 为 `0.90045/0.92193/0.90571`，Bottom Jaccard 为 `0.91736/0.91374/0.91031`，两次完整重建字节一致。

## 当前权限

```text
paper_core_neural_fidelity_status = passed
transparent_context_v1 = rejected_optional_factor_nonblocking
step7_koopman_capacity = passed_d8_k2_selected
step8_contract_freeze = controller_allowed
external_execution = false
residual/diffusion = false
production_authority = false
```
