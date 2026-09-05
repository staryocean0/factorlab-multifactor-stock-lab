# 状态—因子 Stage 0–6 状态机 V2 工作流

先读 [`语义本体`](../ops/reaka_multifactor_semantic_ontology_whitepaper.md)和[`V2白皮书`](../ops/state_factor_research_state_machine_v2_whitepaper.md)，再读取机器合同 `state_factor_research_state_machine@2.0.json`。

执行每个阶段前先验证 `stage_scope`。Stage3–5 的任何产物若包含 `K2_allowed`、`K3_allowed`、`operator_count_N_selected`、`N_effective`、`discrete_operator_expert_allowed` 或 operator supervision mapping，立即失败关闭。

```bash
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/build_reaka_multifactor_infrastructure_v1.py
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/validate_reaka_multifactor_infrastructure_v1.py
.venv/bin/python -m pytest -q tests/unit/test_reaka_multifactor_infrastructure_v1.py
```

状态定义改变时从 Stage3 重开；Stage3 只产生 `observable_context_support_certificate`。Stage4/5 完成并获得用户 checkpoint 后，模型从头训练；有效 operator 数量只由后续 K 准入链产生。
