# REAKA 当前 K1 两账本更新工作流

口径见[白皮书](../ops/reaka_current_k1_account_ledgers_whitepaper.md)，项目级父契约见[`post_training_account_audit@1.1`](../ops/post_training_account_audit@1.1.json)。
当前合同为[`reaka_current_k1_account_ledgers@1.5`](../ops/reaka_current_k1_account_ledgers@1.5.json)；`@1.0--1.3` 保留结果前/验收前事故，`@1.4` 保留科学数据完整但包装未过门的两棵树。@1.5 只做 `result.json`/`execution_receipt.json` 包装修复，十个账本数据文件禁止重算或改写。

```bash
.venv/bin/python scripts/factor_rotation/finalize_reaka_current_k1_account_ledgers_v1.py \
  --formal-root output/factor-rotation/reaka_current_k1_account_ledgers_v1_2011_2026/formal \
  --isolated-root output/factor-rotation/reaka_current_k1_account_ledgers_v1_2011_2026/isolated
```

## 执行前确认

- 模型必须为 `d8-h8-K1-r0_fit_prefix_successor_incumbent`；
- 账户必须为 `N30_equal_backfill_unconstrained`、1×成本；
- 14:30/14:45 必须是两个独立账户；
- 2011--2020 与 2021--2026 保留两个 replay segment；
- 全部时间都是已消费 review，`fresh_oos=false`；
- 本次用户授权两本明细账，但结果不得用来改分数、TopN、时钟、成本或模型。

## 预检

```bash
scripts/run_factor_lab_rocm_gpu.sh --check

PYTHONPATH=src:. scripts/run_factor_lab_rocm_gpu.sh - <<'PY'
# 运行小型 FitJob 批量，检查 ROCm/CPU 系数、rank、condition 和观测数。
PY

.venv/bin/pytest -q tests/unit/test_reaka_current_k1_account_ledgers_v1.py
.venv/bin/ruff check \
  src/factor_lab/factor_rotation/reaka_current_k1_account_ledgers_v1.py \
  scripts/factor_rotation/run_reaka_current_k1_account_ledgers_v1.py \
  scripts/factor_rotation/validate_reaka_current_k1_account_ledgers_v1.py \
  tests/unit/test_reaka_current_k1_account_ledgers_v1.py
```

## formal 与 isolated

```bash
PYTHONPATH=src:. scripts/run_factor_lab_rocm_gpu.sh \
  scripts/factor_rotation/run_reaka_current_k1_account_ledgers_v1.py \
  --tree formal \
  --output-root output/factor-rotation/reaka_current_k1_account_ledgers_v1_2011_2026/formal

PYTHONPATH=src:. scripts/run_factor_lab_rocm_gpu.sh \
  scripts/factor_rotation/run_reaka_current_k1_account_ledgers_v1.py \
  --tree isolated \
  --output-root output/factor-rotation/reaka_current_k1_account_ledgers_v1_2011_2026/isolated
```

两条命令都会一次生成当前 K1 分数、重放两个时钟的两个账户 segment、批量拟合因子收益面，然后生成两本账。同一 tree 内不会为第二本账重新求分或重放账户。

## 输出

```text
account_snapshot/
  portfolio_daily.parquet
  holdings.parquet
  trades.parquet
  events.parquet
  snapshot_manifest.json

selection_opportunity_ledger.parquet
selection_opportunity_decision_summary.csv
selection_opportunity_annual.csv

factor_return_surface.parquet
realized_pnl_ledger.parquet
realized_pnl_annual.csv

result.json
execution_receipt.json
```

## 验证

```bash
.venv/bin/python \
  scripts/factor_rotation/validate_reaka_current_k1_account_ledgers_v1.py \
  --formal-root output/factor-rotation/reaka_current_k1_account_ledgers_v1_2011_2026/formal \
  --isolated-root output/factor-rotation/reaka_current_k1_account_ledgers_v1_2011_2026/isolated \
  --evidence-root docs/ops/evidence/reaka_current_k1_account_ledgers_v1_20260902
```

验证器必须同时证明：策略身份正确、机会标签严格在决策后、oracle是同集合上限、逐日 PnL 守恒、GPU/CPU 拟合等价、旧年度归因复现、formal/isolated 科学文件字节一致，且没有参数、fresh OOS 或生产权。
