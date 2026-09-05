# REAKA论文参数治理工作流

## 入口

必读[`参数治理白皮书`](../ops/reaka_paper_parameter_governance_whitepaper.md)和[`机器目录`](../ops/reaka_paper_parameter_catalog@1.1.json)。任何新REAKA训练先运行：

```bash
.venv/bin/python scripts/factor_rotation/build_reaka_parameter_governance.py
.venv/bin/python scripts/factor_rotation/build_reaka_prediction_root_routing.py
.venv/bin/python scripts/factor_rotation/build_reaka_stage5_parameter_compilation.py
.venv/bin/python scripts/factor_rotation/build_reaka_stage5_lr_boundary.py
.venv/bin/python scripts/factor_rotation/build_reaka_stage5_lr_boundary_v11.py
.venv/bin/python scripts/factor_rotation/build_reaka_stage5_lr_boundary_v12.py
.venv/bin/python scripts/factor_rotation/build_reaka_stage5_lr_boundary_v13.py
.venv/bin/python scripts/factor_rotation/build_reaka_stage5_capacity_lr_joint.py
.venv/bin/python scripts/factor_rotation/build_reaka_stage5_baseline_identity_closeout.py
.venv/bin/python scripts/factor_rotation/build_reaka_stage5_no_incremental_successor.py
.venv/bin/python scripts/factor_rotation/build_reaka_stage5_identity_factor_gates.py
.venv/bin/python scripts/factor_rotation/build_reaka_stage5_residual_identity.py
.venv/bin/python scripts/factor_rotation/build_reaka_stage5_paper_latent_k1_residual.py
.venv/bin/python scripts/factor_rotation/build_reaka_controller_succession_audit.py
```

只有当前装配门、用户顾问门、数学根路由门和本轮实例化门全部`passed`才可训练。当前继任合同是 `reaka_controller_succession_audit@1.1`；用户顾问门 C 已批准，三个根自由度在新的最小载体身份中闭合。当前 run-instantiation 仍必须由外部执行在阶段 A 用本次预检收据填满；未通过前不得开始阶段 B 训练。

## 参数填写顺序

1. 选择scope：作者数值复现、论文结构独立实现或FactorLab适配。
2. 固定论文明确项，不把它们和适配项混在同一身份。
3. 只裁决三个根自由度：确定性容量`h/d`、selector温度、残差denoiser容量族。
4. 机器按约束图填写5项公式强制值、3项产品合同值和6项条件派生值。
5. 运行有效秩、episode、有效样本、残差SNR、梯度、求解器和性能测量，填写5项数值nuisance。
6. 打开[`自由度审计`](../ops/evidence/reaka_paper_parameter_governance_v1_1_20260825/factorlab_training_degree_of_freedom_audit.json)，核对每个下游参数的root和证据。
7. 生成本轮`parameter_values`与`evidence_receipts`，调用`validate_training_parameter_instantiation()`；禁止从类默认值补缺。
8. 用户或作者证据必须形成单项决定receipt；新建catalog版本，旧版本保持只读。
9. 两道门清零后，再生成训练preregistration、性能预检和checkpoint候选。

## 重复运行

- 论文固定项不重复讨论；
- 项目政策只有版本变更时重审；
- `r_eff/n_eff/episode/residual/gradient/performance`随训练前缀变化，必须重测；
- 三个自由根不能因为上一次模型赚钱就自动继承；
- 其余19项不重复讨论，但必须按本轮上游量重新计算或验证；
- 所有候选尝试计入multiplicity，不允许删除失败参数。

## 当前停止线

当前允许：按 `reaka_neural_fidelity_successor@1.0` 外派步骤6；先做当前预检和 22 项实例化，门通过后才做固定 `h8/d8/K1/零残差` 保真测量。

当前禁止：把`gamma=0`当成再选一次学习率/hidden；把项目分数残差冒充论文latent残差；搜 hidden/lr/K/epoch；直接开diffusion、operator capacity 或残差。

历史 GateA 标签被继任审计更正：`hidden_selected=false`时只观测到受限求解器元组，参数身份未闭合。项目分数残差家族已消费并在该元组上塤0；论文latent公式探针只保留实现诊断。装配顺序仍是：透明核心 → 神经保真（零残差） → 算子容量 → 残差；但当前先补透明核心顾问门 C。

## Stage回退

历史 Stage5 封存只可重放，不指示当前动作。历史[`REAKA主控继任审计合同`](../ops/reaka_controller_succession_audit@1.0.json)保留阻断时点；当前使用[`v1.1继任合同`](../ops/reaka_controller_succession_audit@1.1.json)和[`Step6后继合同`](../ops/reaka_neural_fidelity_successor@1.0.json)。

## 右删失续作

当Stage6数值边界被主控验收为right-censored时，必须运行对应Stage5 successor builder。历史v1.0梯子`0.01→0.03→0.1`已消耗。当前H20合同是[`reaka_stage5_parameter_compilation@1.1.json`](../ops/reaka_stage5_parameter_compilation@1.1.json)。残差身份、两扇门、无增量继任、联合合同和LR-boundary只读。项目分数残差已消费并塌成gamma=0；论文latent身份探针已验收。下一步按装配手册做神经保真（零残差，对照透明核心），不是9格选参，也不是diffusion。

历史交接只读：[`Stage6 V2.2学习率边界交接`](reaka_stage6_v2_2_lr_boundary_external_ai_handoff.md)。v1.1封存：[`stage5_closeout.json`](../ops/evidence/reaka_stage5_lr_boundary_v1_1_20260825/stage5_closeout.json)。

V2.2主控验收：[`controller_acceptance.md`](../ops/evidence/reaka_stage6_lr_boundary_v22_controller_acceptance_v1_20260825/controller_acceptance.md)。

v1.2封存：[`stage5_closeout.json`](../ops/evidence/reaka_stage5_lr_boundary_v1_2_20260825/stage5_closeout.json)。

历史交接只读：[`Stage6 V2.3学习率边界交接`](reaka_stage6_v2_3_lr_boundary_external_ai_handoff.md)。

V2.3主控验收：[`controller_acceptance.md`](../ops/evidence/reaka_stage6_lr_boundary_v23_controller_acceptance_v1_20260825/controller_acceptance.md)。测量通过，整案边界未闭合。

v1.3封存：[`stage5_closeout.json`](../ops/evidence/reaka_stage5_lr_boundary_v1_3_20260825/stage5_closeout.json)。

联合合同封存：[`stage5_closeout.json`](../ops/evidence/reaka_stage5_capacity_lr_joint_v1_20260825/stage5_closeout.json)。

受限confirmation主控验收：[`controller_acceptance.md`](../ops/evidence/reaka_stage6_restricted_confirmation_h32_lr0p1_controller_acceptance_v1_20260825/controller_acceptance.md)。透明主干身份封存：[`stage5_closeout.json`](../ops/evidence/reaka_stage5_baseline_identity_closeout_v1_20260826/stage5_closeout.json)。无增量继任封存：[`stage5_closeout.json`](../ops/evidence/reaka_stage5_no_incremental_successor_v1_20260826/stage5_closeout.json)。两扇门封存：[`stage5_closeout.json`](../ops/evidence/reaka_stage5_identity_factor_gates_v1_20260826/stage5_closeout.json)。残差身份封存：[`stage5_closeout.json`](../ops/evidence/reaka_stage5_residual_identity_v1_20260826/stage5_closeout.json)。论文latent K1残差封存：[`stage5_closeout.json`](../ops/evidence/reaka_stage5_paper_latent_k1_residual_v1_20260826/stage5_closeout.json)。论文latent身份探针主控验收：[`controller_acceptance.md`](../ops/evidence/reaka_stage6_paper_latent_k1_residual_controller_acceptance_v1_20260826/controller_acceptance.md)。9格筛选交接已撤回，只读：[`Stage6论文latent K1残差校准筛选交接`](reaka_stage6_paper_latent_k1_residual_screening_external_ai_handoff.md)。步骤6交接当前也已阻断，只读待顾问门 C：[步骤6神经保真交接](reaka_step6_neural_fidelity_external_ai_handoff.md)。当前用户入口是[透明联合核心顾问门 C 审查请求](reaka_joint_core_freeze_review_request_20260826.md)。

换主控述职（给下一任控制器，不是执行提示词）：[`REAKA换主控述职交接 2026-08-26`](reaka_controller_succession_handoff_20260826.md)。
