# REAKA 多因子选股当前唯一工作流入口

## 当前状态

当前正在修复多因子选股基础设施的语义与入口。旧 Stage3 的 PIT 月份、episode、转移和持续测量保留；“外部状态 episode 决定独立 K 资格”的解释已撤权。Stage4、模型训练、K 容量、residual、SSA、账户、指针和生产均关闭。

## 首次阅读顺序

1. [`语义本体白皮书`](../ops/reaka_multifactor_semantic_ontology_whitepaper.md)；
2. [`current manifest`](../ops/reaka_multifactor_current_manifest@1.0.json)；
3. [`六位一体基础设施白皮书`](../ops/reaka_multifactor_six_surface_infrastructure_whitepaper.md)；
4. 当前任务对应的唯一阶段白皮书与机器合同；
5. [`当前 authority`](../ops/reaka_strategy_authority_registry@111.0.json)与[`succession`](../ops/reaka_controller_succession_audit@272.0.json)。

不要先遍历全部 `reaka*` 文件。未列入 current manifest 的材料默认没有当前规范权。

## 执行前语义 checksum

执行者必须先确认：

```text
observable_state_equals_latent_operator_state = false
user_supplies_operator_count = false
model_learns_operator_matrices = true
model_learns_operator_assignments = true
stage3_may_select_operator_count = false
effective_operator_count_is_post_training_evidence = true
portfolio_top_k_is_operator_count = false
```

任一回答不一致就停止，不得执行策略数据、模型或账户任务。

## 当前唯一下一动作

本基础设施验证并经用户审阅后，才允许另冻 REAKA V2 Stage4 的结果前合同。Stage4 只检验 `S_obs×factor`：指数与行业进入，规模不进入。Stage4 不选择 K；后续 Stage5 只冻结输入装配；从头训练后再由 K1→K2→K3 准入链选择有效 operator 数量。

## 基础设施复现

```bash
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/build_reaka_multifactor_infrastructure_v1.py
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/validate_reaka_multifactor_infrastructure_v1.py
.venv/bin/python -m pytest -q tests/unit/test_reaka_multifactor_infrastructure_v1.py
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/close_reaka_multifactor_infrastructure_v1.py
```

完成后仍须停在用户 checkpoint，不自动进入 Stage4。
