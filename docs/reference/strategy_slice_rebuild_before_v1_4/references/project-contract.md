# FactorLab project contract

Use these project surfaces as the canonical implementation references:

- top-level discovery: `AGENTS.md`, `ai-readme.md`;
- generic annual-session workflow: `docs/user/strategy_slice_rebuild_workflow.md`;
- scientific rationale: `docs/ops/strategy_slice_rebuild_whitepaper.md`;
- current contract code: `src/factor_lab/market_state/timing_annual_session_rebuild.py`;
- materializer: `scripts/build_strategy_slice_rebuild_workflow.py`;
- validator: `scripts/validate_strategy_slice_rebuild_workflow.py`;
- regression tests: `tests/unit/test_strategy_annual_session_rebuild.py`;
- predecessor method: `docs/user/market_state_timing_block_material_rebuild_workflow.md`;
- V5 exemplar: `docs/user/market_state_timing_three_specialist_whole_rebuild_v5_workflow.md`.

The rolling V6 implementation remains historical negative evidence. Do not import its raw-window hard-veto selection rule into a successor. The current generic contract is `strategy_annual_session_rebuild@4.0`.

## Data / execution pairing (project default)

New research paths must use `src/factor_lab/data/session_offset_defaults.py`
and `src/factor_lab/data/services/standard_backtest_service.py`.

- Daily menu: `1d@11:30` + `same_day_afternoon`, and/or official `60m+0`
  selected at 14:00, and/or `30m+30` selected at 14:30. `60m+30` closes at
  11:00/14:30, not 14:00. Not a unique 11:30 default.
- Hourly menu: `30m+15`, `60m+30`, `60m+45`. No 60m+5.
- 15m menu: only `15m+5` and `15m+10`. No 15m+15 research default.
- Intraday execution: `next_tradable_after_bar_close`.
- Signal view may be `qfq_canonical`; fill view must be raw / pit.
- Official 15:00 V9 daily is legacy-only (`--legacy-official-session`).
- `backtest_signal()` is optimistic close-to-close, not trading truth.
- Offset bars are DataHub wall-clock products from the same 1m history.
  They are not a live/replay product. Terminal replay stays on 1m raw plus
  the same FactorLab strategy. FactorLab must not locally resample
  2m/3m/10m/20m or use `derive-shifted-bars` as a wall-clock factory.

Whitepaper: `docs/ops/timing_layer1_datahub_clock_split_whitepaper.md` and `docs/ops/unified_offset_data_and_backtest_whitepaper.md`.
Menus: `research_offset_schemes()` / `optional_remake_variants()`.
None of the schemes is a unique project default.
Workflow: `docs/user/unified_offset_data_and_backtest_workflow.md`.

Repeated heavy multifactor stock-selection/timing workloads are GPU-first
design problems. Freeze one causal CPU input materialization, a batched
device-resident ROCm math path, and CPU-only stable ranking/account tails. The
GPU path needs numerical, ordering, TopN, trade-path and account equivalence.
Ordinary throughput mode needs at least 1.20x end-to-end speedup; an explicit
user CPU-reservation policy may select a low-feeder ROCm path at 0.80x or better
to preserve CPU capacity. Do not grant permanent CPU authority from a naive GPU
port that retained Python loops or host/device churn.

Numerical equivalence across CPU and ROCm is scale-aware by default. For every
compared scalar or tensor element use
`abs(rocm-cpu) <= atol + rtol*abs(cpu)` and persist the maximum normalized mixed
residual. Independent global `max_abs<=atol AND max_rel<=rtol` is forbidden as
a generic gate because it is not scale invariant. Exact-byte identity remains
available only as an explicitly frozen reproducibility requirement.



The whole-policy rebuild rule is not a categorical ban on causal overlays. A low-DOF entry veto or two-way route may be evaluated as one complete candidate on consumed history. It must be repriced in the full account and judged by affected-year dispersion, not pooled return alone. The current promotion default requires at least three affected years, at least 60% positive affected years, a nonnegative affected-year median, and positive total increment. This is a candidate-promotion gate, not a progression-retention gate. A hard-valid improvement on a preregistered primary objective using the same comparator/account/cost basis must be retained when it exceeds frozen numerical replay tolerance, even if it fails promotion. A passing promotion result may be frozen only as a retrospective research candidate; it does not create fresh-OOS, routing, or production authority.

The current successor governance is `docs/ops/strategy_progressive_development@1.0.json` plus `docs/ops/post_training_account_audit@1.1.json`; `@1.0` remains immutable historical evidence. It preserves historical `strategy_annual_session_rebuild@4.0` bundles while separating hard validity, progression retention, candidate promotion, fresh validation, and production authorization. Koopman operator count and residual inclusion follow `koopman_residual_admission@1.0` before a trading score is frozen; K3 is not closed a priori. Every frozen model/factor/strategy score must complete strategy science acceptance (`post_training_strategy_science_acceptance@1.0`) before any A0--A7 account contract may be frozen; only then complete the A0--A7 post-training account audit before strategy closeout. Materialize a content-addressed complete account snapshot once, keep the hindsight selection/opportunity ledger separate from realised per-stock/per-trade P&L attribution, fit policy-independent factor-return surfaces once per segment, and derive later reports without rerunning models, scores, markets, or accounts. The blind prior-policy account test and complete-family repricing are separate commands; account results cannot mutate the frozen model.

The closeout dispersion gate has a v2 enhancement approved by the user on 2026-08-16 (contract `market_state_closeout_quarterly_distribution_gate@2.0`, preregistration `docs/ops/evidence/market_state_closeout_quarterly_distribution_gate_v2_preregistration_20260816.json`). The v1 annual gate above remains in force as historical evidence; branches already adjudicated under v1 are never retroactively re-judged. For branches started or adjudicated after the approval date, the v2 quarterly gate applies in addition to the economics gate (Δnet>0 and ΔSharpe>0 vs the frozen baseline):

- affected quarters: `|Δ净_季| >= 0.00025` (the annual threshold 0.001 divided by four, time-proportional);
- pass requires: at least 12 affected quarters, spanning at least 3 distinct natural years, at least 60% positive affected quarters, a nonnegative affected-quarter median, and positive total increment;
- significance reference: 48 samples with a 60% positive gate has binomial null p = 0.0967 (recorded for context; no z-gate is imposed);
- the monthly gate is not adopted: adjacent months share the same trades, so the independence assumption fails and its apparent significance (p = 0.0078) is inflated.

Implementation: `src/factor_lab/market_state/timing_closeout_distribution_gate.py` with regression tests in `tests/unit/test_market_state_timing_closeout_distribution_gate.py`. Parameter-surface discipline (also approved 2026-08-16): a parameter surface is diagnostic material, never a selection pool; only the preregistered mechanism-derived point may be promoted to a candidate, and if that point fails either gate the family verdict is `no_increment` — surface optima may only seed the next preregistration.

For the rejected V6 exemplar, use:

- workflow: `docs/user/market_state_timing_three_specialist_rolling_rebuild_v6_workflow.md`;
- whitepaper: `docs/ops/market_state_timing_three_specialist_rolling_rebuild_v6_whitepaper.md`;
- builder: `scripts/build_market_state_timing_three_specialist_rolling_rebuild_v6.py`;
- validator: `scripts/validate_market_state_timing_three_specialist_rolling_rebuild_v6.py`;
- artifact root: `artifacts/market_state/timing_three_specialist_rolling_rebuild_v6/`.

The V6 construction boundary remains strict:

- `2009-01-01 <= t < 2021-01-01` may be used for V6 material discovery and retrospective rebuilding;
- `2021-01-01 <= t < 2027-01-01` was consumed first as V5 aggregate blackbox evidence and later, after V6 was frozen, as a V6 candidate-specific repeat aggregate audit;
- V6 construction read zero post-2020 rows and used neither aggregate result for candidate selection;
- no future version may read this interval's detailed bars, yearly/monthly metrics, events, trades, charts, or reuse either aggregate result for selection;
- the repeat aggregate audit found V6 account-equivalent to V2 and below V5, so V6 is rejected as V5's successor; it still is not fresh OOS and grants no authority.

For an isolated annual rebuild branch, use twelve natural-year sessions over 2009--2020. Finish and persist each year's prior-policy blind backtest, event/graph ledger, manual analysis, bounded-family preregistration, whole-policy rebuild, frozen snapshot, and chained receipt before opening the next year. The first prior policy is the declared common root; every later prior policy is the preceding session's frozen snapshot. Evidence preparation may be automated one year at a time; interpretation, root promotion, candidate-family design, and policy selection may not be batch-generated. The 2021--2026 interval remains consumed and may not influence selection.

The following old V7 exemplar is **invalid for the isolated-branch method** and may be read only as historical negative evidence, never as design input:

- workflow: `docs/user/market_state_timing_three_specialist_annual_rebuild_v7_workflow.md`;
- whitepaper: `docs/ops/market_state_timing_three_specialist_annual_rebuild_v7_whitepaper.md`;
- one-year evidence preparer: `scripts/prepare_market_state_timing_three_specialist_annual_session_v7.py`;
- final builder: `scripts/build_market_state_timing_three_specialist_annual_rebuild_v7.py`;
- validator: `scripts/validate_market_state_timing_three_specialist_annual_rebuild_v7.py`;
- artifact root: `artifacts/market_state/timing_three_specialist_annual_rebuild_v7/`.

That old V7 reselected V5 behavior and therefore violated the newly clarified branch-isolation requirement. A replacement branch must declare V4 as its common root, forbid V5/V6/old-V7 artifacts, and cannot reuse any sibling policy, candidate, parameter, ledger, result, or conclusion.

The completed replacement exemplar is a parallel clean-room branch. Its stable
alias is `parallel_annual_clean_room_a12`; `v7` remains only in filenames for
compatibility and does not imply lineage:

- workflow: `docs/user/market_state_timing_three_specialist_isolated_annual_v7_workflow.md`;
- whitepaper: `docs/ops/market_state_timing_three_specialist_isolated_annual_v7_whitepaper.md`;
- branch preregistration: `docs/ops/evidence/market_state_timing_three_specialist_isolated_annual_v7_branch_preregistration_20260812.json`;
- one-year evidence preparer: `scripts/prepare_market_state_timing_three_specialist_isolated_annual_session_v7.py`;
- one-year whole-policy builder: `scripts/build_market_state_timing_three_specialist_isolated_annual_snapshot_v7.py`;
- one-year sealer: `scripts/seal_market_state_timing_three_specialist_isolated_annual_session_v7.py`;
- mechanical completion builder: `scripts/build_market_state_timing_three_specialist_isolated_annual_v7_bundle.py`;
- validator: `scripts/validate_market_state_timing_three_specialist_isolated_annual_v7.py`;
- artifact root: `artifacts/market_state/timing_three_specialist_isolated_annual_v7/`.

Its twelve separately reviewed sessions produced 49 materials and counted 71
complete candidate attempts. Three non-trivial temporary snapshots were
challenged by later years, but the final 2020 rebuild selected only the common
root. The scientific result is `no_incremental_successor_beyond_baseline`, not
a new strategy version. It read zero post-2020 rows and has no fresh-OOS,
parameter, routing, architecture-lock, or production authority.

The frozen V6 repeat-audit surfaces are:

- preregistration: `docs/ops/evidence/market_state_timing_three_specialist_rolling_rebuild_v6_blackbox_preregistration_20260812.json`;
- runner: `scripts/run_market_state_timing_three_specialist_rolling_rebuild_v6_blackbox.py` (already consumed; do not rerun);
- validator: `scripts/validate_market_state_timing_three_specialist_rolling_rebuild_v6_blackbox.py`;
- artifact root: `artifacts/market_state/timing_three_specialist_rolling_rebuild_v6_blackbox_2021_2026/`.

Run the project Skill validator with:

```bash
.venv/bin/python /home/starryocean/.codex/skills/.system/skill-creator/scripts/quick_validate.py .codex/skills/strategy-slice-rebuild
```

Run the generic infrastructure gates with:

```bash
.venv/bin/python scripts/build_strategy_slice_rebuild_workflow.py --overwrite
.venv/bin/python scripts/validate_strategy_slice_rebuild_workflow.py
.venv/bin/pytest -q tests/unit/test_strategy_annual_session_rebuild.py
.venv/bin/python scripts/build_strategy_progressive_development_workflow.py --overwrite
.venv/bin/python scripts/validate_strategy_progressive_development_workflow.py
.venv/bin/pytest -q tests/unit/test_strategy_progressive_development.py
```

Do not weaken an old contract in place. Add a schema/version and preserve the predecessor as historical evidence when semantics change.

For a completed historical bundle, `source_digests` bind the bytes used when the
bundle was sealed; they do not require mutable live sources to remain unchanged
forever. A validator must prove each digest from the current worktree or from an
exact Git-history blob. It must not rebind the sealed manifest to current bytes,
and it must fail closed when the recorded source bytes are no longer recoverable.
