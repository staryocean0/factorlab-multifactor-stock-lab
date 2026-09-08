# R3 transfer target-lineage readiness

Date: 2026-09-08.

Current local task: `LCL-R3-TRANSFER-TARGET-LINEAGE-20260908-01`.

Cloud conclusion before local data execution:

- `LCL-R3-TRANSFER-EVAL-20260908-01` correctly stopped at the failed target-anchor gate.
- The ordinary mature 2018--2020 anchors differ by about 0.011--0.017, so this is not a floating-point tolerance issue.
- 2020-12-31 is structurally immature for an H20 future target in the accepted 2007--2020 calendar and is excluded by the successor diagnostic anchor rule.
- TIMEISO `materialize_store()` copied `epsilon_history` / `epsilon_future` from the historical OT1 `stock_residual_surfaces.npz`; the current transfer label bridge reconstructs the target through current price, membership, basis and intraday OT code. Equivalence has not been established.

Cloud added `tests/unit/test_reaka_r3_transfer_target_lineage_diag.py` at commit `6693dbd3c0cf30f3ee6b5955c0313f901774529a`.

Frozen source identities for the handoff:

- diagnostic Git blob: `63aa3263d49f8709d152778f22afe94869c92ecc`
- guard-test Git blob: `c279d4bc3834a9e9f986eae82e07c408acc73674`

Local execution order:

```bash
python3 -m pytest -q tests/unit/test_reaka_r3_transfer_target_lineage_diag.py
python3 scripts/reaka_r3_transfer_target_lineage_diag.py --self-test
export FACTORLAB_ROOT="/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab"
python3 scripts/reaka_r3_transfer_target_lineage_diag.py \
  --output-root "$FACTORLAB_ROOT/tmp/LCL-R3-TRANSFER-TARGET-LINEAGE-20260908-01/run01"
```

Hard stop remains: no label sidecar, archived-score preflight, model checkpoint reload, transfer score job, model fit, 2026 target, account or CloudRidge monthly experiment.

Interpretation rule:

1. If old P6 raw + old factor basis + current intraday OT code reproduces old `epsilon_future`, use the earlier layer comparisons to identify the first extension-path divergence.
2. If that historical artifact replay fails, do not repair the extension target by tuning tolerances or anchors. The missing identity is the historical target producer and/or historical membership semantics; recover that evidence before declaring a same-definition 2021--2025 target.

This readiness note is engineering/research routing only. It does not certify PIT, fresh OOS, target correctness, or production authority.
