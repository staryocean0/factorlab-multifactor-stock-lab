# R3：直接 X 分解与月度 CloudRidge 独立增量设计

日期：2026-09-07  
设计 ID：`R3-X-DECOMP-MONTHLY-DESIGN-20260907-01`

## 1. 已有证据与本轮问题

已完成的 TIMEISO F/H 实验表明：在已消费的 2018–2020 支持上，工具选择冻结在 2016 年末、F/H 统一 CPU、同 seed 共用 pre-DMD 初始状态且各自训练/重载时，完整直接 X 信息包相对 history-only H 的等日期等时钟平均 RankIC 增量为 `+0.020536824420887195`。本轮不再重复验证“X 整体有没有用”，而回答两类更窄问题：

1. 当前 71 通道 X 中，**state 包**与**exposure/reliability/mask 包**分别是否提供有序条件增量？
2. 尚未进入当前 X 的“前一完整自然月 CloudRidge 1σ / S_obs 条件”，在精确定义绑定后，是否能在完整现有 X 之外提供独立增量？

所有结论仍限于已消费历史材料的算法比较，不是 fresh OOS、完整 PIT、经济因果或账户 alpha。

## 2. 当前 71 通道

- `0:14` state values
- `14:28` state availability
- `28:42` stock factor exposures
- `42:56` exposure reliability
- `56:70` exposure availability
- `70` incumbent zero placeholder

历史 epsilon 在所有 arm 中保留，因此 H 不是“factor-free”。

## 3. Stage A：粗粒度 H → E → F 分解（下一步唯一真实训练授权）

冻结三个信息层：

- `H`: 71 个直接 X 通道全部置零；已存在 TIMEISO 分数，不重训。
- `E`: 仅保留 `28:70`，即 exposure + reliability + exposure mask；本轮新增训练。
- `F`: 保留 incumbent `0:70`；已存在 TIMEISO 分数，不重训。

主对比：

- `E − H`: exposure / reliability / exposure-mask 包在 history-only 之上的**有序条件增量**。
- `F − E`: state values + state availability 包在 exposure 包之上的**有序条件增量**。
- `F − H`: 整包直接 X 的既有 TIMEISO 参考，不重新估计。

这些差值不是唯一可加的因果归因；存在交互，禁止转换成“state 占 X 增量百分之多少”等机制份额。

### Stage A 预算

只新增 E：

- clocks: `1430`, `1445`
- seeds: `11, 29, 47`
- backend: 与已验收 TIMEISO 一致的 CPU 稳定环境
- candidate: 原 `d8-h8-K1-r0`, Adam LR `.03`
- max cycles: 3
- new fits: **6**
- max new cycles: **18**
- F/H new fits: **0**
- E 自己估计 DMD、自己优化；同 seed/clock 的 pre-DMD state digest 必须等于已验收 F/H。
- 每 arm/seed 仍按最小 canonical fit-prefix loss 选 cycle；不能读取 2018–2020 决定 cycle。
- E checkpoint 必须持久化，再由 fresh Python process reload 后评分。
- 评价 support、2018–2020 labelled rows、seed rank-z ensemble、paired daily RankIC、block 4/8/12 全部沿用 TIMEISO。
- 不得因 E−H 或 F−E 为负而重跑、增 seed、增 cycle、换参数。

### Stage A 运行器的硬绑定

新增 runner 必须先验证：

- 原 TIMEISO runner SHA256 = `sha256:ee7036f1925ab61ed88cc96e79a0ee06af9bb2a75812a1a58f4aa2d4a61c3708`
- 原 condition-view SHA256 = `sha256:7d76a03785e2d03623342c63c360ddf7680835433294f5f511163d09fba2f921`
- FactorLab commit = `b39bb12f43a46b165d18db93191a669234077444`
- 稳定环境字段（Python/platform/numpy/pandas/torch/device/cuda availability）与已验收 TIMEISO 一致；PID 不属于数值环境身份。
- 当前 F/H scores、fit receipts、normalizer、candidate、prediction rows 直接复用，且重新聚合的 F−H 必须逐日与已验收 `paired_daily.csv` 一致；否则 E 实验停止。

## 4. Stage B：细粒度分解（仅预注册，不自动执行）

为避免看完 Stage A 再发明有利 arm，以下顺序现在冻结，但**本轮不授权拟合**。

如果未来明确授权，可使用：

1. `STATE_VALUE_PLUS_E`: 保留 `0:14` 与 `28:70`，去掉 state mask。
   - `STATE_VALUE_PLUS_E − E`: state values 条件增量。
   - `F − STATE_VALUE_PLUS_E`: state availability 条件增量。
2. `BETA_ONLY`: 仅 `28:42`。
3. `BETA_RELIABILITY`: `28:56`。
4. `E`: `28:70`。
   - `BETA_ONLY − H`: exposure values 条件增量。
   - `BETA_RELIABILITY − BETA_ONLY`: reliability 条件增量。
   - `E − BETA_RELIABILITY`: exposure availability 条件增量。

不得依据 Stage A 正负来改变这些 arm、年份、seed 或顺序；是否执行 Stage B 是后续单独决策，不是 Stage A runner 的自动分支。

## 5. 新月度 CloudRidge 条件：容量匹配接口已实现，公式身份未绑定

当前仓库及可恢复历史上下文中没有找到该条件的精确公式。已知研究意图是“前一完整自然月 CloudRidge 1σ / S_obs 条件”，但以下细节目前**没有权威绑定**：

- S_obs 的精确定义；
- 1σ 是针对什么序列/估计量；
- 趋势正负号与阈值；
- 连续值还是离散值；
- 缺月如何编码。

因此不得凭印象实现公式或开展真实 F+M 训练。

### 已实现的因果时间接口

为避免公式一旦确定后再改实验结构，当前先固定**时间与容量合同**：

- 使用 incumbent 71 维中的 channel `70` 作为**实验性月度 slot**，不改变 feature_dim、网络拓扑和参数量；incumbent F 的 channel70 仍为 0。
- F+M 的每个 K1 序列 endpoint，使用**该 endpoint 自己所属月份的前一个完整自然月**的已编码月度值，而不是把当前决策日的一个值平铺到全部 10 个 endpoint。
- 月度记录必须带 `source_month`, `available_at`, `value`；若 `available_at` 晚于 endpoint，则拒绝。
- 缺失月份直接报错；在精确公式未绑定前，不发明 `0=missing` 或其他中性编码。
- 注入只允许修改 channel70，`0:70` 必须保持 byte-for-value 不变。

精确公式绑定后，预注册主对比为：

`F+M − F`

若 F 可复用，则只新增 F+M 的 6 次 fit；同样要求共同 pre-DMD 初始状态、各自 DMD、checkpoint 保存及 fresh-process reload。该实验不会把整包 F−H 的增量归给月度条件。

## 6. 云端实现与验证

新增：

- `src/factor_lab/factor_rotation/reaka_r3_x_decomposition.py`
- `src/factor_lab/factor_rotation/reaka_r3_x_coarse_runner.py`
- `scripts/reaka_r3_x_coarse_compare.py`
- `tests/unit/test_reaka_r3_x_decomposition.py`
- `tests/unit/test_reaka_r3_x_coarse_runner.py`

云端实际执行 27 项合成/接口测试，0 失败，并运行 `py_compile`。范围覆盖：

- F/H/E/fine pre-registered views 的通道投影；
- F/H/E 相同参数量的合成 carrier；
- E 模型入口只保留 `28:70`；
- mask/age incumbent 约束；
- E-only 6 fit budget 与 F/H 禁止重训；
- accepted F/H identity/reconstruction 守卫；
- stable runtime identity（排除 PID）；
- 月度跨年边界、逐 endpoint 前月映射、future availability、missing month、channel70-only 注入；
- 月度 store view 不读取 target。

这些是云端合成/接线证据，不是 E 的真实市场结果，也不是月度公式的证明。

## 7. 下一本地任务

真实 Stage A 因 accepted TIMEISO 大 scores/store/checkpoint 与 FactorLab 数值栈在本地，交给 `LCL-R3-XCOARSE-20260907-01`。任务书见 `docs/ops/cloud_local_communication_R3_xdecomp_20260907.md`。

月度 F+M **不在该任务授权范围内**。本地可顺手搜索是否存在精确 S_obs/1σ 定义的权威本地源码/文档；若找到，只回传小型定义/路径/源码身份，不执行月度训练。找不到则明确 `formula_identity_not_found`。
