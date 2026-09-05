# REAKA V2 Stage3 可观测条件支持工作流

先读 [`白皮书`](../ops/reaka_v2_stage3_observable_context_whitepaper.md) 与结果前合同 `docs/ops/reaka_v2_stage3_observable_context@2.0.json`。

```bash
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/build_reaka_v2_stage3_observable_context_v2.py
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/run_reaka_v2_stage3_observable_context_v2.py --tree formal
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/run_reaka_v2_stage3_observable_context_v2.py --tree isolated
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/validate_reaka_v2_stage3_observable_context_v2.py
.venv/bin/python -m pytest -q tests/unit/test_reaka_v2_stage3_observable_context_v2.py
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/close_reaka_v2_stage3_observable_context_v2.py
```

Stage3 V2 只读取 authority correction 允许的四个 V1 原始测量文件。任何输出出现 operator 数量、K2/K3 权限或状态到operator映射都必须失败。

完成后停在用户 checkpoint，不自动执行 Stage4。
