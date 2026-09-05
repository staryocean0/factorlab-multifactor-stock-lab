# REAKA V2 Stage4 可观测条件×因子配对工作流

先读 [`白皮书`](../ops/reaka_v2_stage4_observable_factor_pairing_whitepaper.md) 和结果前合同 `docs/ops/reaka_v2_stage4_observable_factor_pairing@1.0.json`。

```bash
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/build_reaka_v2_stage4_observable_factor_pairing_v1.py
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/run_reaka_v2_stage4_observable_factor_pairing_v1.py --tree formal
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/run_reaka_v2_stage4_observable_factor_pairing_v1.py --tree isolated
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/validate_reaka_v2_stage4_observable_factor_pairing_v1.py
.venv/bin/python -m pytest -q tests/unit/test_reaka_v2_stage4_observable_factor_pairing_v1.py
PYTHONPATH=src .venv/bin/python scripts/factor_rotation/close_reaka_v2_stage4_observable_factor_pairing_v1.py
```

完成后只打开用户金融审核包。没有用户签署的 `advisor_interpretation_receipt`，不得进入 Stage5。
