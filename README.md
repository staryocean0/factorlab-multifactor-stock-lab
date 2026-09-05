# FactorLab REAKA Multifactor Stock Lab

Private, bounded cloud workspace for FactorLab **multi-factor A-share stock selection**
(REAKA / residual-enhanced adaptive Koopman autoencoder) and the surrounding
factor-research infrastructure.

This repository is **not** the Layer 3 two-wave timing theme and **not** the
overnight-open lab. Do not merge it into `factorlab-two-wave-strategy-lab` or
`factorlab-overnight-open-lab`.

It is a research minimum set: current multifactor contracts, the licensed REAKA
paper, paper-faithful Python, 2007-2025 A-share research surfaces, and historical
results. It does not contain the 2 TiB DataHub, FactorLab git history,
credentials, or 2026 market rows.

## 2026-09-05 foundation audit

Start with the [takeover audit and repair workflow](docs/user/reaka_foundation_audit_workflow.md).
The paper is conditionally compatible with the financial objective. The audit
found residual-evidence and Stage4 observation defects; the foundation is not
yet certified ready. New code tests do not constitute financial acceptance.
The frozen Stage4 reports and current@1.2 remain historical evidence and
research-state records; this audit adds explicit corrections without rewriting them.

## Start here

```bash
python -m pip install -e .
python scripts/validate_theme_package.py
pytest -q
```

Then follow [`docs/user/cloud_execution_prompt.md`](docs/user/cloud_execution_prompt.md).

## Scientific status

`stage4_machine_evidence_waiting_user_financial_review`

Stage5, model training, K-capacity selection, accounts, pointer changes and
production remain closed. This repository may produce research notes and a pull
request. It cannot install a successor into the authoritative local FactorLab
registry or claim that a strategy works.

The bundled IEEE paper is internal-research only. See [`NOTICE.md`](NOTICE.md).

