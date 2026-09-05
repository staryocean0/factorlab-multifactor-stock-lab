# REAKA Multifactor Stock Lab Control Plane

This private repository is a bounded FactorLab research theme package. Its
purpose is to let an external research-grade agent continue multifactor stock
selection research with the data, infrastructure, paper, and historical results
that the local controller frozen for this lab. It is not an authority to trade,
mutate the local FactorLab current pointer, choose K, or promote a strategy.

## Takeover audit supplement (2026-09-05)

Read `docs/user/reaka_foundation_audit_workflow.md` and its report before using
the frozen handoff. The user authorized foundation audit and reversible repairs.
Keep the original current@1.2 and source receipts immutable; use the new read-only
audit for current-version checks. A successful report command is not a passed
foundation gate. Do not silently relabel teacher-forced residuals, deduplicate
Stage4 months, or call financial residual/account other latent residual.

## Read order

1. `README.md`
2. `NOTICE.md`
3. `docs/INDEX.md`
4. `docs/user/cloud_execution_prompt.md`
5. `docs/governance/data_usage_declaration.json`
6. `docs/user/reaka_multifactor_current_workflow_v1_2.md`
7. `docs/ops/reaka_multifactor_current_manifest@1.2.json`
8. The REAKA paper PDF and its FactorLab summary under `research_materials/`
9. `.codex/skills/strategy-slice-rebuild/SKILL.md` before any strategy change

## Semantic checksum

```text
observable_state_equals_latent_operator_state = false
user_supplies_operator_count = false
model_learns_operator_matrices = true
model_learns_operator_assignments = true
stage3_may_select_operator_count = false
effective_operator_count_is_post_training_evidence = true
portfolio_top_k_is_operator_count = false
```

Stop if these cannot be confirmed. Do not invent K2 from a failed identification
attempt. Do not treat S_obs as operator supervision.

## Frozen boundaries

- Current unique local action is user financial review of Stage4 evidence.
- Stage5, training, residual/DRC training, account execution, pointer change and
  production are closed in this repository.
- Files outside the current manifest have no current normative authority.
- Consumed formula identities in
  `docs/ops/reaka_factor_parallel_consumed_formula_registry@2.0.json` must not be
  rerun as if they were new.
- Never use result-driven calendar rules. Dates, clusters and casebook names are
  materials, not runtime state.
- The paper is a licensed IEEE full text. Internal research only; no public
  redistribution.

## Data contract

- A-share QFQ daily bars: 2007-2008 warmup, 2009-2025 research surface.
- 165 non-financial factors, PIT market cap, industry indexes, macro input and
  CloudRidge/000985 references are shipped as research surfaces through 2025-12-31.
- 2026+ rows are physically absent and must not be downloaded, inferred,
  requested over the network, or fabricated.
- `fresh_oos=false`. 2018-2025 is already consumed comparison for the current
  Stage4 line and cannot be advertised as unseen OOS.
- Data is a research surface, not a live broker fill surface.

## Deliverables

- New reusable code under `src/factor_lab/`.
- Tests under `tests/`.
- Executable workflows under `scripts/`.
- Specifications and notes under `docs/` or `cloud_results/`.
- Do not modify `data/development/` or the frozen paper PDF.

No production, paper-trading, registered-use, K-selection, or fresh-OOS
authority is available in this repository.

