---
name: strategy-slice-rebuild
description: Develop, optimize, combine, route, or validate FactorLab trading strategies through sequential annual research sessions, progressive evidence retention, whole-policy rebuilding, post-training account audits, and genuinely unseen-period challenges. Use for every strategy change, especially robustness, drift, non-overfitting, walk-forward, dynamic-parameter, routing, account mapping, or cross-period work.
---

# Strategy Slice Rebuild

Use twelve sequential natural-year research sessions to expose observations and counterexamples. In every session, first blind-test the previously frozen whole policy, then use the newly opened year as material and rebuild a complete policy from the declared common root plus this branch's cumulative materials. Never turn a calendar slice into a runtime rule, auto-promote a negative return to a hard veto, inherit a sibling experiment, or patch the previous winner one failure at a time.

Read [the project contract](references/project-contract.md) before running this workflow.

## 0. Data and backtest contract (fail closed)

Offset / noon-close is **not a second market**. It is a backtest bucket of
the same DataHub 1-minute history. Terminal replay still consumes DataHub
`1m raw`. FactorLab research must:

1. Fetch through `factor_lab.data.session_offset_defaults.apply_fetch_defaults`
   or `factor-lab datahub-fetch-bars`. DataHub constructs wall-clock bars;
   FactorLab only chooses the menu. No local resample and no
   `derive-shifted-bars` wall-clock factory.
2. Daily research menu is optional: `1d@11:30` + `same_day_afternoon`,
   and/or official `60m+0` selected at 14:00, and/or `30m+30` selected at
   14:30. `60m+30` closes at 11:00/14:30, not 14:00.
3. Hourly menu: `30m+15` / `60m+30` / `60m+45`. No 60m+5.
   15m menu is only `15m+5` and `15m+10`. No 15m+15 research default.
   Intraday fill is `next_tradable_after_bar_close`.
4. Allow qfq only as the **signal** view. Fills are raw / pit.
5. Treat
   `bars_cn_a_1d_qfq_canonical_xdxr_v9_factorlab_2009_2025_20260814`
   and `backtest_signal()` close-to-close as legacy / optimistic only.
6. Refuse noon-close + `next_session`, 15:00 + `same_day_afternoon`, and
   qfq fills.

Details: `docs/ops/timing_layer1_datahub_clock_split_whitepaper.md` and `docs/ops/unified_offset_data_and_backtest_whitepaper.md`.
7. Old timing-infrastructure numbers stay legacy. Remakes use the same
   optional menus and must not overwrite old artifacts.

### GPU-first heavy recomputation

For foreseeable repeated heavy recomputation in multifactor stock-selection or
timing, design an equivalent GPU-friendly algorithm before admitting a
CPU-oriented recurring implementation. Materialize causal CPU/I/O inputs once,
batch rolling linear algebra and neural inference with device-resident tensors,
and keep only stable ranking and small sequential accounts on CPU. ROCm becomes
the default only when the exact target workload preserves numerical tolerance,
cross-sectional ordering, TopN membership, trade paths, and account metrics.
Ordinary throughput mode requires at least 1.20x end-to-end speedup. When the
user explicitly reserves CPU for CPU-only jobs, resource-priority mode may
select an equivalent low-feeder ROCm path at speedup at least 0.80x. A slow
mechanical port disproves only that port, not a GPU-first redesign.

Cross-device floating-point parity uses a scale-aware mixed tolerance per
reported quantity: `abs(gpu-cpu) <= atol + rtol*abs(cpu)`. Do not require
independent global absolute and relative maxima to both pass, because that
makes the relative tolerance ineffective and creates scale-dependent vetoes.
Bitwise identity is a separate gate and may be required only when the frozen
contract explicitly needs exact bytes. Numerical parity never substitutes for
ordering, TopN, trade-path, or account equivalence.


## 1. Declare the evidence boundary

Before reading returns, charts, trades, or event details, write a machine-readable data-usage declaration that assigns every interval exactly one role:

- `development_material`: may generate materials and influence candidate construction;
- `repeat_audit`: may reproduce an already-consumed conclusion but cannot become fresh evidence;
- `fresh_challenge`: may test exactly one frozen policy once, without candidate ranking or retuning;
- `aggregate_lockbox`: may expose only preregistered aggregate fields and may not expose years, months, events, trades, charts, or parameters.

Once an interval has influenced candidate choice or been opened in detail, never call it fresh again. Once an aggregate lockbox is consumed, do not reuse it to develop the next version.

## 2. Freeze the common root and branch isolation

Declare whether versions are descendants or parallel experiments. For a parallel experiment, freeze before computation:

- the execution model, T+1 semantics, price convention, costs, and boundary isolation;
- one common-root policy formula and digest;
- an allowlist containing only the common-root implementation, raw carrier data, generic infrastructure, and the current experiment branch;
- a denylist containing every sibling policy, ledger, candidate family, parameter, result, conclusion, and lockbox artifact;
- the chronological slice atlas;
- the reported metrics and failure gates.

Sibling experiments may share the common root and raw data. They may not teach, seed, constrain, rank, or validate one another. If contamination occurs, invalidate the branch and restart from the common root. Memory of a sibling result is not authority: machine-verifiable source lineage must still prove that no sibling artifact entered design or selection.

## 3. Build the annual session atlas

Use one non-overlapping natural year per research session. For the current bounded history, execute exactly twelve sessions: 2009 through 2020.

- Do not create half-year-offset or other rolling material windows.
- Do not run all years as one scientific batch.
- Do not use a shell loop or batch driver to complete the twelve evidence/review sessions.
- Automation may prepare a frozen, same-schema evidence pack for exactly one requested year.
- The main agent must review that pack, attribute problems, write the year-specific analysis ledger, and seal a receipt before opening the next year.
- Every receipt must bind both the prior receipt digest and the exact prior-policy digest. The first year binds to the common-root digest; later years bind to the preceding session's frozen rebuilt policy.
- Chain every receipt to the prior receipt digest. Missing, duplicated, out-of-order, or batch-generated receipts fail closed.

Subagents may help inspect evidence, but the main agent owns each year's conclusion and ledger. A script or subagent may not bulk-author causal interpretations, hard obligations, or year verdicts.

Never use the slice id, calendar year, or lane id as a runtime feature.

## 4. Blind-test the prior snapshot, then discover openly

At the start of each year, run exactly one frozen prior policy. This blind phase may report only that policy's evidence; it may not rank candidates or change the formula. Then inspect concrete trades, opportunity events, charts, missed moves, wrong-way exposures, and whipsaws. Do not limit discovery to the old policy's owners, parameters, or candidate axes.

Review concrete observations covering at least:

- opportunity supply or absence;
- full-account net result relative to the frozen baseline;
- Sharpe and drawdown diagnostics;
- responsibility-owner marginal contribution;
- error morphology, missed opportunity, false claim, or execution pathology.

Every observation must record its symptom, evidence references, opportunity sufficiency, responsibility owner, and whether the cause is resolved. Mark no-opportunity cases `inconclusive`; they are neither pass nor fail.

Graphical/event attribution is mandatory for every annual session, not optional when aggregate metrics look good. Do not invent a threshold when the root cause remains unresolved. A raw observation or an `unresolved` root is always diagnostic and has no hard-veto authority.

## 5. Distill roots before constraints

Group same-root observations into falsifiable mechanism hypotheses while preserving every source case. Promote a root to `resolved` only when it is economically material and is supported by either two independent annual sessions or one frozen causal challenge.

Each resolved root may promote at most one hard obligation. The number of hard obligations may not exceed the bounded candidate family's effective degrees of freedom. If the observed roots exceed what the family can express, report `candidate_family_insufficient`; do not add dozens of vetoes or silently delete mechanisms.

## 6. Rebuild the whole policy in every annual session

After the current year's attribution, but before evaluating alternatives, preregister a bounded complete candidate family and search budget derived only from the common root plus the current branch's cumulative materials. Then:

- evaluate every registered candidate as a full-account policy;
- reprice the complete path with T+1 and costs;
- evaluate over all branch materials revealed through the current year;
- inherit zero block-specific runtime conditions;
- add zero calendar-specific rules;
- evaluate every promoted hard obligation and explain every diagnostic observation;
- count all candidate attempts in the multiplicity denominator.

Reconstruct the candidate from the common root; the previous winner is only the blind-test subject, never the code parent or default candidate. A rebuilt formula may coincidentally be behaviorally identical, but its receipt must prove a fresh whole-family decision rather than incremental inheritance. Do not require every annual return delta to be nonnegative: years are research cases, not absolute vetoes. Measure stability over independent sessions with preregistered economic materiality, downside concentration, opportunity supply, and complete-account results.

Separate **hard validity**, **progression retention**, and **candidate promotion**. Financial meaning, mathematical identity, causal timing, complete-account accounting, reproducibility/source closure, multiplicity, and authority boundaries are non-compensable hard checks. If any fails, invalidate the economics and retain only an incident or counterexample. After all hard checks pass, any improvement on the preregistered primary objective that uses the same comparator/account/cost basis and exceeds the frozen numerical replay tolerance must be retained as progression material. Do not impose a minimum economic effect size for retention. Record its tradeoffs, contribution concentration, attempt id, and failed promotion gates.

Distribution, robustness, cost, risk, and cross-variant gates may block promotion to a retrospective candidate; they may not delete hard-valid measured progress. If financial utility is ambiguous and no result-free utility rule resolves it, retain the material as `progress_tradeoff_waiting_financial_owner` and do not let the AI invent a preference after seeing results.

Do not confuse this anti-patching rule with a ban on low-capacity routing. An entry-only veto, a two-way parameter route, or one additional causal layer may be a legitimate complete candidate when it expresses one resolved mechanism and is repriced in the full account. A candidate discovered from the already-consumed 2009--2020 material may be frozen as a **retrospective research candidate** when its gain is distributed across affected annual sessions rather than supplied by one isolated year. At minimum report affected-year count, positive/negative affected-year counts, positive-year share, affected-year median, total increment, and concentration. Use a preregistered majority rule (the current promotion default is at least three affected years, at least 60% positive, nonnegative median, and positive total). Failure blocks candidate promotion but does not erase valid progression material; passing still grants neither fresh validation nor production authority.

Freeze the selected research snapshot and its formula digest before opening the next year. Keep the common root as a comparator, not an eligible successor. If only the common root or an account-identical candidate survives, report `no_incremental_successor`; never publish it as a new strategy version.

## 7. Challenge causally

The next natural-year session is the causal challenge for the prior snapshot. During its blind phase:

- do not rank candidates;
- do not inspect detailed subperiods unless the lockbox contract explicitly permits it;
- do not change the formula;
- do not treat insufficient opportunity as success;
- do not let the failed interval validate the rebuild it later helps construct.

On failure, convert the new year into materials, reject the whole policy as the continuing snapshot, and rebuild a new whole policy from the common root plus cumulative branch materials. On an infrastructure gap, repair the infrastructure before continuing. On unresolved mechanism evidence, change measurement or factor family rather than adding a threshold.

The policy rebuilt after the final 2020 session has no later fresh challenge inside this workflow. Label it `frozen research candidate waiting for a new unseen challenge`; never infer validation from the years that constructed it.

## 7b. Admit Koopman operator count and residual before freezing a trading score

K count and residual inclusion are research outcomes. Use `docs/ops/koopman_residual_admission@1.0.json`. First evaluate K1. If it passes, do not give residual yet; ask the next K. If it fails, do not force a whole-stack residual; ask whether leftover can split into two tables. If it cannot, abandon this Koopman stack and return to factor or state work. If it can, evaluate K2. Keep asking the next K until it fails or the frozen `maximum_operator_count` is reached, then ask residual of the last qualified K. Residual may enter the trading score only after that stop. Do not close K3 a priori. Do not send a residual-contaminated score to SSA or A0--A7.

## 8. Run strategy science acceptance, then the post-training account audit

After a model, factor score, or strategy score snapshot is frozen, and before strategy closeout, first run the generic strategy science acceptance. Read [the post-training account audit reference](references/post-training-account-audit.md). SSA uses `docs/ops/post_training_strategy_science_acceptance@1.0.json`. It binds the frozen identity, materializes one diagnostic selection/opportunity ledger and one score-path diagnostic ledger, attributes factor representation / K-state / residual, and fail-closes on `no_signal` or `infrastructure_gap`. Do not freeze an account-policy family, search TopN/cost, or execute A0--A7 until SSA status is `diagnostic_signal_present_account_contract_may_open`. Passing SSA is not validation, fresh OOS, or production authority.

Only after SSA passes, run the generic post-training account audit. Bind the immutable model/checkpoint/score identity, freeze the account-policy family before results, materialize causal formal/isolated inputs, validate the exact workload, then execute annual account sessions.

Use `docs/ops/post_training_account_audit@1.1.json` for new account work; do not rewrite `@1.1` to absorb SSA. Materialize each registered account once as a content-addressed complete `AccountSnapshot`; derive later performance reports from that snapshot with zero model, score-generation, market-replay, or account-replay calls. Keep the hindsight selection/opportunity ledger separate from the realised per-stock/per-trade P&L ledger, and fit any policy-independent factor-return surface only once per variant and return segment.

The blind prior-policy account test and the complete-family repricing must be separate commands. The family command may start only after the main controller reviews the blind evidence. Account results may never retrain or jointly fine-tune the frozen model. The final validator must be outcome-neutral: both a real winner and an honest no-winner result are valid scientific outcomes when the evidence chain passes.

## 9. Report the scientific status

End with exactly one honest status:

- frozen research candidate waiting for a new unseen challenge;
- no incremental successor beyond the baseline;
- no bounded whole policy covers the materials;
- infrastructure or measurement gap;
- opportunity absent, so evidence is inconclusive.

Never grant parameter, routing, architecture-lock, or production authority from retrospective slice fitting alone. A valid weak improvement may be retained even when no candidate is promoted; report both statuses rather than collapsing them into `no_increment`.

## 10. Persist five-in-one evidence

Keep documentation, whitepaper, code, tests, and executable workflow synchronized. Persist at minimum:

- data-usage ledger;
- annual session atlas;
- twelve separate evidence packs, analysis ledgers, and digest-chained completion receipts;
- source-material ledger and same-root consolidations;
- observation/root/obligation promotion ledger and obligation-by-policy matrix;
- twelve separate whole-policy rebuild preregistrations, build receipts, and frozen policy snapshots;
- candidate-attempt/multiplicity receipt;
- progression ledger separated from the promotion ledger;
- Koopman/residual admission state, selected K, residual-in-score flag, and trading-identity freeze;
- post-training strategy science acceptance contract, two diagnostic ledgers, factor/K/residual attribution, and outcome-neutral SSA verdict;
- post-training account audit plan, blind receipts, account-family receipts, and outcome-neutral final audit;
- frozen challenge or explicit “waiting for fresh data” status;
- replay validator and source digests.

Source digests in a sealed historical bundle are immutable freeze-time evidence.
After a legitimate workflow or Skill upgrade, validate each old digest against
either the current bytes or the exact blob retained in repository history. Never
rewrite an old manifest merely to match today's source, and fail closed when the
recorded bytes cannot be recovered.

Stop only after the validator proves the boundaries, inventory, formula identity, and authority flags.
