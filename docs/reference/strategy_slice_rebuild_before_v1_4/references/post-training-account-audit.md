# Post-training account audit

Read this reference after a model, factor score, or strategy score snapshot is frozen and before strategy closeout.

A frozen score must first complete strategy science acceptance (`docs/ops/post_training_strategy_science_acceptance@1.0.json`). SSA is S0 identity, S1 one diagnostic opportunity ledger plus one score-path diagnostic ledger, S2 factor/K-state/residual attribution, and S3 an outcome-neutral gate. It is not A0--A7, not a Cartesian account family, and not complete RealizedPnl. Only `diagnostic_signal_present_account_contract_may_open` may open an A0--A7 account contract. `docs/ops/post_training_account_audit@1.1.json` is unchanged.

## Stage atlas

1. **A0 — identity freeze:** bind the immutable model, checkpoints, score definition, score panel, training boundary, and data-role ledger. Account results cannot retrain or fine-tune them.
2. **A1 — result-free family freeze:** preregister TopN/selector, weighting and single-name caps, buy-unavailable behavior, concentration dimensions, variants/clocks, cost schedules, stress scenarios, primary objective, attempts, and promotion rules.
3. **A2 — causal input materialization:** use an allowlisted score schema with `score_available_at <= decision_time`; use raw/PIT fills and a separately declared economic accounting unit. Variants must remain separate accounts.
4. **A3 — validation and performance:** validate accounting identities, physical read bounds, source closure, formal/isolated parity, and the exact workload runtime before account results open.
5. **A4 — blind prior-policy run:** execute only the preceding frozen account policy. Its output may contain no challenger identities or family rankings.
6. **A5 — manual review then family run:** after main-controller review, separately execute the complete frozen Cartesian family. Produce distinct progression and promotion ledgers.
7. **A6 — annual seal:** bind blind, analysis, family, prior-receipt, and prior-policy digests before the next year opens.
8. **A7 — outcome-neutral final audit:** validate winner, no-winner, no-opportunity, candidate-family-insufficient, and infrastructure-gap outcomes without hardcoding one result.

## Reusable account-research boundary

New work uses `docs/ops/post_training_account_audit@1.1.json` and the workflow at `docs/user/post_training_account_research_bundle_workflow.md`.

- Materialize each registered account once as a content-addressed complete `AccountSnapshot` containing daily account state, holdings, additive trade/cost legs, and execution events.
- The selection/opportunity ledger answers whether the frozen score selected the best subsequently realised tradable opportunities. Its hindsight labels have no runtime authority.
- The realised P&L ledger decomposes each account day, stock, trade episode, and strategy-defined component. Both simple-return and linked-log contributions must reconcile to the account.
- Fit policy-independent factor returns once per variant and return segment, then reuse that surface across years and account policies.
- Annual, quarterly, monthly, benchmark-relative, Sharpe, drawdown, turnover, and cost reports read the snapshot. Adding a report may not trigger model loading, score generation, market replay, or account replay.
- `account_daily_only` snapshots are allowed for aggregate reporting or performance measurement but cannot close A7 or claim complete trade attribution.

## Non-compensable invariants

- no future/PIT leak or next-open substitution;
- no model/checkpoint/score mutation;
- full-account costs, tradability, forced holdings, cash, and corporate actions reconcile;
- formal/isolated scientific bytes match;
- all attempts enter the denominator;
- sealed source bytes resolve from the current tree or exact Git history;
- retrospective results keep `fresh_oos=false` and `production_authority=false`.

## Progression versus promotion

Any hard-valid primary-objective improvement above replay tolerance is retained. Promotion gates may label it weak, concentrated, risky, or cross-variant inconsistent and may block replacement of the current snapshot. They do not delete the observation. When return, drawdown, capacity, or variant preferences conflict without a frozen utility rule, retain the material and wait for the financial owner.

Strategy-specific adapters own model loading, data products, clocks, costs, policy identities, and diagnostic columns. The generic audit owns schemas, stage separation, chain validation, retention/promotion separation, authority, and replay/source-closure rules.
