# R1 原始输入与模型绑定补件

外部返工停在 R1：原 `execution_receipt.json` 引用的 14:30/14:45 输入、冻结分数和市场面板未随第一包交付。

本补件恢复：

1. 六个点名文件的**原字节**（两个 149MB 市场面板因 GitHub 100MB 限制拆成 `.parts`，用 `python scripts/restore_github_split_artifacts.py` 拼回原路径并校验 sha256）。
2. 14:30/14:45 `reaka_intraday_K1_input_v1_2009_2020` 完整 npy 输入仓（manifest 实际引用）。
3. `docs/ops/reaka_current_k1_account_ledgers@1.5.json`（canonical digest `sha256:b2a7b150...`）及其 source closure。
4. 现任身份 `d8-h8-K1-r0_fit_prefix_successor` 的 formal 拟合回执与 review scores。

`r0` 只表示未启用潜空间残差修正网络，不等于未使用金融收益残差，也不自动要求重训 K1。

`src/factor_lab/factor_rotation/reaka_current_k1_account_ledgers_v1.py` 当前工作区字节与旧回执记录的 source-closure digest 不一致，按现字节交付，不覆盖旧摘要。
