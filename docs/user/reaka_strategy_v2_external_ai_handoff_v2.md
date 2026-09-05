# REAKA V2 外部 AI 交接 V2：状态输入与 K 学习严格分层

## 先通过语义 checksum

```text
observable_state_equals_latent_operator_state = false
user_supplies_operator_count = false
model_learns_operator_matrices = true
model_learns_operator_assignments = true
stage3_may_select_operator_count = false
effective_operator_count_is_post_training_evidence = true
portfolio_top_k_is_operator_count = false
```

不能逐项确认时停止，不得执行。唯一 current 入口是 `docs/user/reaka_multifactor_current_workflow.md`，唯一规范清单是 `docs/ops/reaka_multifactor_current_manifest@1.0.json`。

## 本轮金融任务

第一轮模型和账户保持历史可查。第二轮不增加因子，只加入上一自然月 CloudRidge 1σ 趋势条件，研究它怎样影响指数与行业通道；规模不加该条件。状态/条件由用户和项目输入，具体 `K_i`、selector 与样本归属由模型学习。

## 为什么从 Stage3 重开

新增 `S_obs` 改变了输入状态身份、PIT 时点、条件配对和模型输入装配，因此最早从 Stage3 重开。Stage3 不决定 K 数量：它只检查状态定义、episode、转移、持续和时间/截面支持。原 Stage3 V1 的这些测量保留；由测量推出“独立 K 不允许”的解释已撤权。

## 后续顺序

1. Stage3：`S_obs` 图鉴，仅产生 observable-context support；
2. Stage4：指数/行业的 `S_obs×factor` 机制与覆盖；规模不配；
3. Stage5：冻结 `S_obs` 怎样进入 `H_x`、gate 或显式交互；不得分配 operator 标签；
4. Stage6：禁止旧 checkpoint，从头训练论文计算图；
5. operator admission：结果前冻结 `N_max`，按 K1→K2→K3 逐级训练和裁决 `N_effective`；
6. residual→SSA→A0-A7，各自等待 checkpoint。

## 当前权限

当前只完成基础设施语义修复。Stage4、训练、K容量、residual、账户、指针和生产全部关闭。外部执行者不得创建 controller acceptance，不得从历史 handoff 或 manifest 外文件自创下一动作。
