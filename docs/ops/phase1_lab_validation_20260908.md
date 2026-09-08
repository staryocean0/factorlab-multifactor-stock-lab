# Phase I 正式判定：REAKA 新实验室的数学成立性与金融实现能力

日期：2026-09-08

## 1. 判定问题

本报告执行 `docs/ops/reaka_research_mission.md` 的 Phase I，只回答两个有顺序的问题：

1. 论文/研究路线与用户给定的市场/指数、大小盘、行业及股票横截面因子，按当前基础设施、白皮书和工作流组合后，数学上是否成立；
2. 若成立，该数学结构是否具备实现“全投资、主动多头、A 股横截面选股”这一金融需求的能力。

本报告不是“某个 R3 子实验是否有增量”的裁决，也不把历史回测收益代替数学证明。

## 2. 论文对象到实验室对象

现行语义把对象严格分层：股票/历史特征进入 encoder；`H_x/H_y` 是学习得到的表示；`Z/S_latent` 是 encoder+gate 得到的潜表示；selector 学习 operator assignment；`K_i` 是模型学习的潜转移矩阵；score 是冻结模型输出，只能成为 ranking candidate；账户结果还必须经过 portfolio/cost/execution。`S_obs` 不等于潜 operator state，用户也不提供 operator 数量。

论文主干的可核数学链是：

`features/history -> encoder -> gate/latent representation -> selector -> K_s -> next latent representation -> score`

其中 selector/Koopman 关系在现行 ontology 中冻结为 `a=SelectorNet(Z,H_y)`、训练时 `K_s=sum(alpha_i*K_i)`、推理时选择 selector operator、`Z_hat_next=K_s*Z`。该链的对象类型和职责没有把可观测市场状态误当 operator 标签，数学语义成立。

## 3. 48 个 paper core 与用户给定因子的关系

这里纠正此前口头表述：**现行权威证据支持的是 `CORE_SPATIAL_H20` 的 48 个 paper-core factor identities，不是已证明的“48+2 全部正式输入”。**

V3 factor-authority 白皮书明确：论文主干需要历史收益、股票特征、双路 LSTM/gate、潜状态、Koopman selector/residual；transparent Context、行业、市值/size、style 和其他交互属于**可选因子**，不是为了满足论文而必须强塞进 48 个 core 的对象。Step5 V3 实际冻结 `CORE_SPATIAL_H20` 48 因子和 `baseline_score`；Step6 对该 paper core 的神经载体保真已经通过。

因此 Phase I 的正确检查不是“48 个 core 必须包含市场、size、industry 每一种外部因子”，而是：paper core 必须数学自洽；用户因子必须有合法、不会破坏 paper core 的接入位置；接入后必须能通过股票异质响应影响总收益排序。

## 4. 市场/size/industry 的金融数学接口

`src/factor_lab/factor_rotation/reaka_financial_residual.py` 明确冻结三类金融因子 `market/size/industry`，并实现共同区间、共同收益单位、显式 factor identity、冻结 beta、时间可得性约束下的

`epsilon_i = r_i - intercept_i - beta_i,market F_market - beta_i,size F_size - beta_i,industry F_industry`。

这是金融收益残差，不等于 latent Koopman residual，也不等于账户中的 other contribution。

股票横截面选择的决定性条件是异质响应。若状态只给所有股票增加同一常数 `c_t`，则

`rank(rhat_i + c_t) = rank(rhat_i)`，

因此不能实现选股。合法机制必须类似

`Delta rhat_i = beta_i^T Delta Fhat`

或更一般的股票特异映射 `f(x_i, z_t, s_t, beta_i, industry_i, ...)`。当前实验室同时具有股票级输入/score 与 beta/exposure 型接口，因而存在可验证的“共同状态 -> 异质股票响应 -> 横截面排序变化”路径。

## 5. 当前真实因子接线边界

当前 factor registry 进一步说明了“数学接口存在”和“该因子已被 PIT 认证并激活”不能混为一谈：

- price/volume 类基础股票因子存在 active/default-enabled 项；
- `market_cap_size_lag1` 与 `market_cap_from_pit_shares_lag1` 已注册为 structural size exposure，但状态为 `inactive_requires_availability_gate`，需要 `available_at`/PIT 来源证据；
- `industry_membership_lag1` 已注册为 structural industry exposure，同样为 `inactive_requires_availability_gate`；
- 历史 Stage4 曾实际装配 index/industry component contribution 与 observable condition 的配对，因此不是只有抽象接口；但该旧 Stage4 因重复月份与来源闭合问题仍是未接受历史证据，不能拿来证明预测增量或 PIT 成功。

故本报告**不声称所有用户可选因子当前都已获得经验准入**。这不阻止 Phase I 的“金融实现能力”判定，因为实验室能合法承载这些对象；但 Phase II 若迁移旧策略中的 size/industry 组件，必须满足各自 availability gate，不得把注册等同于 PIT 通过。

## 6. 预测目标与排序闭环

K1 的 `epsilon` 预测是一个合法子问题，但不是整个产品目标。用户允许主动行业和大小盘暴露时，一般有

`rank(epsilon_hat_i) != rank(total_return_hat_i)`。

因此 residual-only 不能被升格为整个策略的金融目标。

当前主 H20 paper-core 路径的职责是股票级 H20 score/ranking candidate；现行 ontology 又把 score 与最终 account 明确分开。实验室因而具备从股票特异预测到横截面排序，再到 portfolio/cost/execution 的金融闭环接口。是否最终赚钱、净值是否优于基准，是后续经验与账户问题，不是本阶段用数学结构伪造的结论。

## 7. 决定性反例

Phase I 用以下反例限定“成立”的含义：

1. **常数状态反例**：共同状态只产生全股票相同平移 -> 排名不变 -> 不能完成选股；因此必须保留异质股票响应。
2. **residual-only 反例**：若产品允许主动共同因子暴露，却只按 `epsilon_hat` 排序 -> 不等价于总收益排序；因此 residual 只能是子通道或需与共同因子预期贡献重新组合。
3. **注册即有效反例**：size/industry 只在 registry 出现但没有 PIT availability -> 不能声称实际因子已准入。
4. **latent 自洽反例**：重建误差低、operator 可分或 latent residual 非零 -> 均不能单独证明金融排序有用。
5. **R3 mask 反例**：INFOCLOCK 已发现 consumed 2018-2020 的 14 个 native state-mask 全为 1；因此对应 arm gap 不能解释成“评估期动态 mask 信息”。子机制解释失败不等于实验室整体失败。

## 8. 正式判定

### 数学成立性：PASS

论文主干到现行 encoder/gate/selector/Koopman/score 的对象与映射成立；金融 residual 与 latent residual 已分离；market/size/industry 有显式收益分解与异质 exposure 接口；没有发现必须靠维度广播、未来标签或把 observable state 当 operator label 才能成立的数学依赖。

### 金融实现能力：PASS

目标是股票级 H20 ranking candidate，且实验室具有股票特异输入、异质 beta/exposure 响应和 score -> portfolio/account 的接口。它**具备**把市场/行业/大小盘共同信息转化为不同股票的预期收益差异并进行主动多头横截面排序的能力。

### 不随 PASS 一并授予的主张

- 不证明所有 optional size/industry/index 因子当前已 PIT 认证、已激活或有增量；
- 不证明完整 upstream PIT；
- 不把 2018-2025 已消费历史称为 fresh OOS；
- 不证明历史 Stage4 因果有效；
- 不证明 net-account alpha、交易可实现性或生产适用性；
- 不授予 production authority。

这些是后续具体策略/因子实例的证据门，不是实验室数学能力本身的失败。

## 9. Phase II 门

根据研究总纲，Phase I 的两个必要判定均为 PASS，故 **Phase II 正式开放**。

下一任务不是继续扩展 R3 消融，而是恢复旧实验室策略的金融目标、输入、决策时钟、排名/持仓/成本语义和历史共同根，映射到刚通过验收的新实验室；先建立等价基线，再研究新实验室增量。对应任务书：`docs/ops/phase2_old_strategy_redevelopment_20260908.md`。

## 10. 证据基线

本判定在分支提交 `458b27f5af84f798f58f39c1aedfc8e2b3d587ea` 上审阅以下现行/历史材料：

- `docs/ops/reaka_research_mission.md`
- `docs/ops/reaka_multifactor_semantic_ontology@1.0.json`
- `docs/ops/reaka_factor_authority@3.0.json`
- `docs/ops/reaka_factor_authority_v3_whitepaper.md`
- `src/factor_lab/factor_rotation/factor_specs.py`
- `src/factor_lab/factor_rotation/reaka_financial_residual.py`
- `docs/ops/reaka_v2_stage4_observable_factor_pairing@1.0.json`
- `docs/ops/research_state.json`
- R2/R3 已接受的 scoped receipts（仅按其原范围使用）。

本轮没有运行新训练、模型推理、账户回放或 GitHub Actions。