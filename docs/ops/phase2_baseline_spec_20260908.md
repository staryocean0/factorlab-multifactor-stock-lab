# Phase II 等价基线规范（语义冻结，旧策略字节身份待回收）

日期：2026-09-08  
任务 ID：`P2-BASELINE-SPEC-20260908-01`  
状态：`frozen_semantic_baseline_waiting_old_policy_identity`

## 1. 权威与研究顺序

本规范服从：

- `docs/ops/reaka_research_mission.md`：两阶段总研究任务；
- `docs/ops/phase1_lab_validation_20260908.md`：Phase I 已正式判定 `mathematical_integrity = PASS`、`financial_implementation_capability = PASS`；
- `docs/ops/phase2_old_strategy_redevelopment_20260908.md`：Phase II 已启动。

Phase II 的目标不是复制旧模型内部字节，而是：**把旧实验室已经开发过的主动多头 A 股策略的金融任务，在新实验室中用正确、可审计的数学和时间语义重新开发出来。**

本文件先冻结“等价基线的金融语义与比较合同”。旧策略最终 canonical policy 的确切源码/配置/账户身份尚未唯一回收，因此本规范不得被误读为已完成旧策略字节级复现。

## 2. 已冻结的等价基线金融语义

### 2.1 产品与排序目标

主产品目标保持：`fully_invested_active_long_A_share_cross_sectional_selection`。

等价基线的 primary prediction/ranking object 必须是与股票持仓决策一致的**股票级未来总收益/可交易总收益横截面排序对象**，当前重开发主 horizon 为 H20。

金融残差 `epsilon` 可以作为模型中的合法子通道，但不得把

`rank(epsilon_hat)`

自动等同于

`rank(total_return_hat)`。

这是 Phase I 已确认的必要金融约束，因为策略允许主动 market/size/industry 等共同成分暴露。

### 2.2 新实验室 paper core

当前 paper core 固定为 `CORE_SPATIAL_H20` 的 48 个冻结 identities。其身份由现行冻结注册/产物确定，不在本规范中重新选择、增删或用历史赢家结果反向改写。

辅助稳定性、有效性、availability/context 等通道与这 48 个 paper-core identities 分开管理。

### 2.3 市场/指数、size、industry 与 context

这些输入可以作为金融共同成分、暴露、context 或条件变量进入新实验室，但必须满足两条：

1. 数学上通过股票异质响应进入横截面，例如 `beta_i * factor_state`，而不是给所有股票加同一个常数；
2. 实际使用前必须闭合来源、时钟和 `available_at`/PIT 证据，不能用“历史曾实现过 pairing”代替当前准入。

因此：

- market/index：数学角色可直接映射，具体来源仍按当前数据合同；
- size：若进入基线，需要实际来源/可得性证据；
- industry：若进入基线，需要实际来源/可得性证据；
- CloudRidge 上一自然月 1σ `S_obs`：只有精确公式、窗口、符号/编码和缺失规则从旧权威源码恢复后才可进入。未恢复前一律不猜。

### 2.4 R3 结果的地位

R3 state/reliability/mask/transfer 结果只作为新实验室机制研究的从属证据保存，**不继承为 Phase II 等价基线答案**。在旧策略身份冻结以前，不允许用 R3 已知结果挑选基线参数或架构。

## 3. 等价性的四个层级

Phase II 必须区分以下四层，不能互相替代。

### A. 金融语义等价（第一门）

必须确认旧策略与新基线比较的是同一个经济对象：

- universe/eligibility；
- decision instant；
- horizon；
- score 的经济含义；
- long-only / fully-invested 责任；
- benchmark、成本和可交易性语义。

旧实验室若有已知乐观或错误的 clock/fill 语义，新实验室不得为了“复现”而恢复错误；应记录为 `requires_semantic_redefinition`，并在当前合法执行语义下建立可比基线。

### B. Score / ranking 等价

旧 canonical policy 身份回收后，在同一合法可比样本上比较：

- score 定义与 normalization；
- 排序方向；
- rank/order；
- TopN membership；
- tie/missing/eligibility 处理。

本规范**不预先发明任何数值容差**。若旧合同有冻结 tolerance，则继承其精确身份；若没有，则在看到结果前另行预注册。

### C. Portfolio / account 等价

在相同合法 execution/accounting basis 下比较：

- TopN/权重；
- 买入受阻、卖出、持有、替补逻辑；
- rebalance cadence；
- 成本；
- fill；
- trade path；
- account metrics。

同样不得以某几个聚合收益相近替代路径等价。

### D. 模型内部字节等价

**不是 Phase II 的必要目标。**新实验室的任务是重新开发同一金融任务，而不是复制旧网络 checkpoint、旧 latent representation 或旧实现 bug。只有旧源码身份作为历史基准需要被绑定和保留。

## 4. 旧策略历史材料如何使用

仓库已知历史结论：V5、V6、旧 V7 与 V4 是并行分支；V6 重复聚合账户与 V2 等价且落后 V5；旧 V7 存在直接重选 V5 行为的污染。该历史可以用于理解研究谱系，但**不能据此把 V5 自动宣布为用户最终 canonical policy**，也不能利用其已消费结果偷选 Phase II 参数。

2021–2026 已被旧研究消费，不能重新包装成 fresh evidence。Phase II 的历史重开发和重复比较均保持 `fresh_oos=false`，直到未来真正未见期间的一次性冻结挑战。

## 5. Phase II 等价基线第一版冻结项

在旧策略精确身份回收前，第一版只冻结下列内容：

- primary objective：股票级 H20 总收益/可交易排序；
- paper core：`CORE_SPATIAL_H20` 48 identities；
- financial residual：仅子通道，非默认最终 score；
- market/index/size/industry/context：可选金融通道，按实际 old-policy role 与 PIT 来源决定是否纳入；
- CloudRidge `S_obs`：未闭合公式前禁用；
- R3 state/reliability：不作为旧策略等价基线的先验答案；
- execution：以现行合法时钟/fill/accounting 合同为准，旧乐观语义只作为历史差异记录；
- comparison：先金融语义，再 score/rank，再 portfolio/account；
- no training / no tuning / no candidate selection before old-policy identity review。

## 6. 当前唯一必须补的身份依赖

云端仓库当前不能唯一确定“用户实际认可/使用的旧策略 canonical executable identity”。必须回收：

1. canonical old policy id/version；
2. V4 common root 的确切实现身份（若该策略谱系依赖它）；
3. score 公式、normalization、方向；
4. universe/filter；
5. TopN、weights、rebalance、blocked-buy/sell/hold；
6. cost、benchmark、decision clock、label horizon、fill；
7. market/index/size/industry 是否真正属于 canonical policy；
8. CloudRidge `S_obs` 是否属于 canonical policy，以及若属于则其精确公式；
9. 对应源码/配置/manifest 的真实字节 SHA256 与工作区状态。

该依赖由：

`LCL-P2-OLDSTRAT-ID-20260908-01`

执行，说明见：

`docs/ops/cloud_local_communication_P2_old_strategy_identity_20260908.md`

身份回传并经云端审阅前，Phase II 不启动新模型训练、策略选优或账户晋升。

## 7. 当前证据边界

本规范不声称：

- 已复现旧策略账户；
- 已证明新实验室产生正 alpha；
- 已获得 fresh OOS；
- 已闭合所有历史 PIT/available_at；
- 已获得 production authority。

`fresh_oos=false`，`production_authority=false`。
