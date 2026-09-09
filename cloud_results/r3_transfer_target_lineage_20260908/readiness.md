# R3 transfer target-lineage / entry-open repair readiness

Date: 2026-09-08.

`LCL-R3-TRANSFER-TARGET-LINEAGE-20260908-01` completed locally at commit `2329b24161649afc4f176bbac990a0de920565b3` and is accepted with limits: current intraday OT code exactly replays old beta/reliability/available, epsilon_history and epsilon_future when fed old P6 raw arrays and old factor basis. The first extension-path divergence is raw future H20.

Recovered historical P6 target semantics from the already accepted R2 independent auditor:

- history H20 = decision_close[t] / decision_close[t-20] - 1;
- future H20 = **entry_open[t+20] / entry_open[t] - 1**;
- entry_open is the first positive finite one-minute open with timestamp wall-clock strictly after the decision clock and <=15:00.

The failed v1 transfer label bridge used decision close for the future target and remains preserved as a historical failed runner.

Current local task: `LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01`.

Use:

- `scripts/reaka_r3_transfer_target_source_bridge.py`
- `scripts/reaka_r3_transfer_label_bridge_v1_1.py`
- `tests/unit/test_reaka_r3_transfer_target_source_bridge.py`
- `docs/ops/cloud_local_communication_R3_transfer_target_entryopen_20260908.md`

This task first validates the historical DataHub entry-open event rule on five structurally mature old D5 anchors and their t+20 dates, then builds only the 2021--2025 target tail. The accepted 2007--2020 P6 prefix is reused. No 2026 target month is opened by the successor target bridge.

Even if the successor label bundles pass both clocks, the local task stops before sidecar creation, archived-score preflight, checkpoint reload or the 24 transfer score jobs. Those remain a separate release after cloud review of the repaired target bundles.

`fresh_oos=false`, `PIT_certified=false`, `production_authority=false`.
