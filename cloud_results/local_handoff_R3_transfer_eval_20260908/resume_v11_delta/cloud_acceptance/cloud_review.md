# R3 2021–2025 frozen transfer evaluation 云端验收

日期：2026-09-08。任务：`LCL-R3-TRANSFER-EVAL-20260908-01`。
本地结果提交：`a1ee98a986b372c7181d5f0013ed9b4a139d4ede`。
本地执行基点：`ec714cfda9ced07ca36582e7138b5ed4c1a851c4`。
FactorLab：`b39bb12f43a46b165d18db93191a669234077444`。

## 裁决

**通过，状态 `completed_with_limits`。**

修复后的 archived-score batch-context preflight 24/24 通过，且24组旧score比较的 `max_abs_error=0.0`；随后正式运行恰好24个 fresh-process、无标签 score jobs，并完成两项预登记 contrast 的2021–2025 consumed historical transfer评价。没有新训练、checkpoint selection、normalizer refit、DMD reinit或2026 target读取。

本次结果可以作为“冻结模型在已消费2021–2025历史材料上的跨期算法比较”。不得称 fresh OOS、PIT认证、账户alpha、生产可交易性或唯一因果特征证明。

## 1. 执行门与身份

本地 targeted tests：26 passed / 0 failed / 0 errors / 0 skipped。

preflight：

- schema `factorlab.r3_transfer_score_preflight@1.1`；
- 2 clocks × 3 seeds × 4 arms = 24组；
- 每组固定64个comparison rows；
- 以历史 `BATCH_SIZE=4096` 的原连续batch geometry重放；
- 每组64个历史batch，context rows=260,990；
- 24/24 checkpoint state digest匹配；
- 24/24 comparison row identity匹配；
- 24/24 `max_abs_error=0.0`，ATOL仍为 `1e-7`；
- outcome/sidecar/new-period score在preflight中均未读取/执行。

此前稀疏64行重组成新batch造成的ULP级差异因此被证明是preflight执行路径问题，而不是需要放宽容差；阈值没有修改。

正式run从16:34:02到16:47:32 Asia/Shanghai，exit 0，状态 `completed_consumed_historical_transfer`。提交diff中存在恰好24个 `score_receipt.json`。每个worker没有label/target路径；抽查及本地总回执均报告：`score_rows=931677`、`target_values_read=0`、`label_path_received=false`、`new_model_fits=0`、`fresh_process=true`。

label sidecars沿前轮已验收v1.1产物直接复用，没有重建target/label/sidecar。每时钟 finite evaluation rows=914,934，评价日=238，年份仅2021–2025。

## 2. Primary 结果

聚合口径保持预登记：每日每seed截面rank-z后三seed等权；同日两时钟contrast等权；再跨238个日期统计H20 financial residual RankIC差。

### A. `F − STATE_VALUE_PLUS_E`

combined：

- mean = **0.005307745671817133**
- median = 0.00697726150060805
- win/loss days = 149 / 89
- block4 = **[-0.0033328471883997653, 0.013810389776097208]**
- block8 = **[-0.0039554627402847405, 0.015222010038309216]**
- block12 = **[-0.004920318959656801, 0.015309921071389768]**

逐年：2021 -0.00680868；2022 +0.00511997；2023 +0.01618510；2024 +0.00713398；2025 +0.00488590。phase0 = -0.00295995。seed47在两时钟均为负（1430 -0.00369992；1445 -0.00647756）。

**科学解释：点估计仍为正，但4/8/12 moving-block区间均跨0，且存在负年份、负phase和稳定负seed切片，因此不能称为稳定跨期增益。** 与2018–2020 XFINE中 `F−STATE_VALUE_PLUS_E ≈ +0.0103955` 且block区间全正相比，本期均值约为其51%。

更重要的是，INFOCLOCK已经证明2018–2020评价支持上的14个state-mask通道恒为1。故该contrast继续只能解释为 **state-mask相关训练/模型算法路径的冻结迁移差异**，不能解释为动态state availability信号贡献。

### B. `BETA_RELIABILITY − BETA_ONLY`

combined：

- mean = **0.0064301572928477015**
- median = 0.005815130231243775
- win/loss days = 153 / 85
- block4 = **[0.0032613852170230427, 0.009573838710406095]**
- block8 = **[0.0031994016133545613, 0.010220078930576313]**
- block12 = **[0.003296001762473256, 0.010692347191676463]**

逐年combined全部为正：2021 +0.00273125；2022 +0.00854858；2023 +0.00455903；2024 +0.00343480；2025 +0.01325985。四个phase combined也全部为正。

存在负seed切片：1430 seed47 = -0.00938853；1445 seed11 = -0.00260923。因此不能写成“所有seed/clock都一致”。但在冻结的主聚合口径上，238日mean为正，且4/8/12 moving-block区间都高于0。

**科学解释：这是本期更强的迁移证据。** 它与2018–2020 XFINE `BETA_RELIABILITY−BETA_ONLY ≈ +0.0056343`、block区间为正的方向一致；本期均值约高14%。可称为“reliability ordered increment在已消费历史跨期中的稳定正向算法差异”，但仍不是可靠性变量的唯一因果归因、PIT证明或未来收益承诺。

## 3. Secondary

combined decile：

- F−STATE = +0.00100238
- reliability−beta-only = +0.00129665

combined Top30-minus-universe：

- F−STATE = +0.00687276
- reliability−beta-only = +0.00459286

均保留为secondary，不能用于挽救primary或改变预登记裁决。

## 4. 两时钟与seed异质性

1430：F−STATE mean +0.00601397，reliability contrast +0.00831531；后者block4/8/12均为正。

1445：F−STATE mean +0.00460152，reliability contrast +0.00454501；后者block4/8/12亦均为正。

六个clock×seed切片并非独立市场重复，不能把6个切片当作6份独立样本做显著性放大。它们用于异质性诊断：F−STATE在seed47两时钟均负；reliability contrast也有两个负切片。

## 5. 云端复核范围

云端实际读取并交叉核对：

- 本地结果提交与基点compare：只新增本次结果、24个score receipts及沟通记录，没有修改评分模型源码；
- targeted test摘要；
- batch-context preflight完整receipt；
- formal run日志；
- 顶层result、两时钟结果、combined结果；
- score receipt样本，并按提交diff确认24份receipt文件存在；
- 提交对应Actions runs为空。

云端未读取本地大`scores.npz`逐格重算931,677×24分数，也未重新运行24个模型forward。因此这是“本地真实模型执行 + 云端源码/小产物/统计回执复核”，不是云端独立全量重算。

## 6. 研究结论与下一步边界

本任务到此收口，不因结果强弱追加seed、年份、arm或重跑。

当前最稳健的算法层结论是：

1. `F−STATE_VALUE_PLUS_E`：正点估计但跨期稳定性不足；保留为算法路径差异，不作为动态mask价值证据。
2. `BETA_RELIABILITY−BETA_ONLY`：在冻结主聚合上跨2021–2025保持正向，五年combined均正且moving-block 4/8/12均高于0；这是当前更可信的跨期算法增量候选。

这些结果仍使用原3982固定股票队列和此前已披露的成员来源限制。`fresh_oos=false`、`PIT_certified=false`、`production_authority=false`继续不变。禁止把本验收升级为账户收益、总收益、容量、冲击成本或生产上线结论。

如启动下一研究任务，应优先围绕已冻结的reliability机制做不增加训练自由度的诊断/经济解释，或等待真正未消费数据；不要用当前已消费2021–2025继续调参。
