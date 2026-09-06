# R1 原始输入与模型绑定补件

外部返工停在 R1：原 `execution_receipt.json` 引用的 14:30/14:45 输入、冻结分数和市场面板未随第一包交付。第一轮点名的 6 个输入、账本合同 @1.5、K1 npy 仓和 formal checkpoint 已在 `main` 上。本轮再补的是**沿这些清单继续走下去仍缺的源码/合同/证据闭包**。

## 已恢复

1. 六个点名文件的**原字节**（两个 149MB 市场面板因 GitHub 100MB 限制拆成 `.parts`，用 `python scripts/restore_github_split_artifacts.py` 拼回原路径并校验 sha256）。
2. 14:30/14:45 `reaka_intraday_K1_input_v1_2009_2020` 完整 npy 输入仓（manifest 实际引用）。
3. `docs/ops/reaka_current_k1_account_ledgers@1.5.json`（canonical digest `sha256:b2a7b150...`）及其 source closure。
4. 现任身份 `d8-h8-K1-r0_fit_prefix_successor` 的 formal 拟合回执、review scores 与 seed 11/29/47 checkpoint；checkpoint manifest digest 与 mapping `input_manifest_*` 一致。
5. mapping `source_digests` / `market_rebuild_source_digests` 中的 FactorLab 相对路径文件，按**旧回执摘要**交付。其中 3 个当前 FactorLab 工作区已漂移，从 Git 历史取出原 blob：
   - `src/factor_lab/factor_rotation/reaka_intraday_portfolio_mapping_v1.py` @ `03e761e28`
   - `scripts/factor_rotation/prepare_reaka_intraday_portfolio_mapping_session_v1.py` @ `02b60c51e`
   - `tests/unit/test_reaka_intraday_portfolio_mapping_v1.py` @ `f2babbd3a`
6. 拟合合同 `docs/ops/reaka_intraday_K1_fit_prefix_successor@1.0.json`、K1 输入合同 `docs/ops/reaka_intraday_K1_preflight@1.0.json`、mapping/market-rebuild 合同，以及对应 evidence 目录。
7. mapping 回执引用的两份 DataHub **repair validation report** 副本，放在 `docs/ops/evidence/r1_datahub_history_copies/`。这不是 DataHub 湖，原绝对路径见该目录 `path_map.json`。

## 使用方法

```bash
git pull origin main
python scripts/restore_github_split_artifacts.py
```

然后从 PR #1 的 `cloud_results/first_round_rework_20260905/rework.md` 继续 **R1**。不要用旧 GitHub tree 快照 `20d3f18e` 判断当前上传状态。不要因 `r0` 这个名字重训 K1。

`r0` 只表示未启用潜空间残差修正网络，不等于未使用金融收益残差，也不自动要求重训 K1。K1 构造器读取 `epsilon_history` / `epsilon_future`。

## 故意不覆盖的漂移

当前包里的现行源码与旧回执摘要不一致时，保留现行字节，另存原 blob，不伪造旧 digest：

- `src/factor_lab/factor_rotation/reaka_paper_v1.py`：现行 V1.3 基础字节保留；mapping 回执所需旧 blob 在 `docs/ops/evidence/r1_original_source_snapshots/reaka_paper_v1.py`。
- `src/factor_lab/factor_rotation/reaka_current_k1_account_ledgers_v1.py`：FactorLab git 中找不到旧 blob `sha256:bf97a470...`，按现字节交付。
- `src/factor_lab/portfolio/account_research_bundle.py`：旧 blob `sha256:7480480a...` 同样无法从 git 取出，按现字节交付。

未包含：DataHub 湖、isolated 重复树、K2/残差后继训练产物、生产指针。`fresh_oos=false`。
