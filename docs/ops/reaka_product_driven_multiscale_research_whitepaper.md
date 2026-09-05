# REAKA 产品驱动多尺度研究与装配白皮书

> 版本：V2.0
> 生效日期：2026-08-16
> 责任项：`bd://fl-yj4b5`
> 当前机器合同：[`reaka_product_driven_multiscale_research@2.0.json`](reaka_product_driven_multiscale_research@2.0.json)
> 历史 V1：[`reaka_product_driven_multiscale_research@1.0.json`](reaka_product_driven_multiscale_research@1.0.json)，仅保留采访前基础设施血缘
> 用户入口：[`../user/reaka_product_driven_multiscale_research_workflow.md`](../user/reaka_product_driven_multiscale_research_workflow.md)
> 首份冻结包：[`evidence/reaka_product_driven_multiscale_research_v2_20260816/README.md`](evidence/reaka_product_driven_multiscale_research_v2_20260816/README.md)
> 当前权限：研究基础设施，`fresh_oos=false`，`production_authority=false`

## 0. 修复了什么

旧流程从“已有因子池”直接跳到“5/20/60 日效力”，再把这些结果送入三出口和 REAKA。它缺了一个上游问题：用户究竟要的是怎样的产品。

新流程的起点是：

`User product intent -> frozen product contract -> one multiscale factor matrix -> three-pathway qualification -> REAKA compatibility certificate -> model training -> whole-policy challenge`

首份用户产品已把最小交易许可冻结为日频、周频和双周频。月线、双月线不作为新的交易许可档，但20/40日慢目标仍在同一矩阵中研究；慢机会可以跨过许多合法交易日继续持有。

## 1. 换仓频率的真实含义

“周频换仓”表示两次实际交易之间至少间隔一周，不表示每周必须换。到了新的合法决策点，策略可以：

1. 换到新股票；
2. 调整权重；
3. 保持原仓不动。

本产品是始终满仓的主动多头，因此没有“降低到现金”的第四种动作。满仓是组合约束，不等于强制换股。

因此必须分开三个时钟：

| 时钟 | 白话含义 | 可否不同 |
|---|---|---|
| 信号重算间隔 | 多久重新读一次因子和状态 | 可以日频重算 |
| 最小交易间隔 | 最早什么时候允许再下一次单 | 是产品硬约束 |
| 预测目标期 | 因子在回答多久以后的收益 | 可长于换仓间隔，本产品含20/40日 |
| 实际持有期 | 已买入仓位实际持续多久 | 不设机械上限，慢机会可继续持有 |

信号可以比交易权更快地更新，但不得借更快信号绕过产品的最小交易间隔。

## 2. 主控 AI 必须先采访用户

采访只问需要金融和产品权衡的内容，不要求用户决定潜维、算子数或统计阈值。必问项是：

1. 做多、多空研究，还是两者都要；
2. 交易的股票范围、流动性和容量下限；
3. 是否允许主动行业、市值和风格暴露；
4. 希望同时研究哪些最小换仓间隔；
5. 快慢两本账能否共存，还是最后只能选一个速度；
6. 换手政策、资金容量和真实买卖成本；
7. 是否允许现金、持股数如何产生，以及回撤在因子层还是组合层处理。

本次采访已冻结：主动多头；全 A 进入候选计算，具体因子可只在 PIT 自动发现的部分股票有效；资金规模100万—1000万元；快慢账可并行；行业、市值、风格允许主动获利；允许高换手但必须按真实成本扣费；单因子回撤只报告不否决；始终满仓；持股数量由容量、信号广度和分散化研究产生，并在整案评价前冻结。

采访未冻结时，系统只生成 `product_interview_template.json`，不允许生成外部 AI 执行提示词。

## 3. 一次研究的多尺度资格矩阵

冻结产品后，系统展开：

`factor x PIT spatial subset x minimum trade interval x target horizon x pathway`

三条 pathway 是长期主效应、条件效应/状态反馈、严格滞后可跟随。同一原始因子只有一个身份，但可以拿到多张使用资格票：

- `factor_A x weekly x H=5 x long_term`；
- `factor_A x weekly x H=20 x follow`；
- `factor_A x biweekly x H=40 x conditional x discovered_subset`。

它们是同一因子的不同用法，不是三列因子，也不能重复投票。

### 3.1 交易许可与慢目标必须解耦

V1 用 `D x multiplier` 生成期限，容易让人误以为“没有月频调仓，就不能研究月线机会”。V2 改为分别冻结：

- 最小交易许可：`1/5/10`日；
- 目标期限：日频格 `1/5/10/20/40`，周频格 `5/10/20/40`，双周格 `10/20/40`；
- 最大持有期：开放，不因到达下一个许可点或目标日机械卖出。

这些格子都在读结果前冻结并进入多重检验分母。20/40日是慢目标，不是月频、双月频的独立科学样本。

旧 `5/20/60 + weekly/monthly` 是 V2.2 已执行研究的历史坐标，不是今后产品的永久规定，也不得回改其封存证据。

## 4. 外部 AI 只负责前两段

产品合同冻结后，主控程序自动生成外部 AI 提示词。提示词带有产品 digest、矩阵 digest、必读文档、输入边界、交付物和停止条件。

外部 AI 可以做：

1. 机械性输入验收；
2. CPU/GPU 向量化的全矩阵原始效力计算；
3. 为 2009—2020 每个自然年分别准备同 schema 材料；
4. 生成 coverage gap、反例、事件和性能台账。

外部 AI 不能做：

1. 局部 BH 晋级或选最佳周期；
2. 批量代写十二年的因果归因和封条；
3. 把同一年的日/周/月结果算成多份独立证据；
4. 代替用户判断金融机制；
5. 装配 REAKA、训练模型或发布策略。

## 5. 主控收回材料后做什么

顺序年度审阅的当前实现为[`REAKA Stage 3 顺序年度裁决基础设施`](reaka_stage3_annual_adjudication_whitepaper.md)。它一次只打开一年，把单年数百MB原始材料压缩为约4.5MB主控包，仅对有界诊断队列回取具体正反例。该队列不改变全量多重检验分母，也不自动晋级。

主控必须依次执行，不得跳步：

1. 验收数据时钟、矩阵全量覆盖、CPU/GPU 对齐和计算分母；
2. 按 2009→2020 顺序审阅年度材料，书写归因并链式封存；
3. 对整个矩阵做中央多重校正，不在外部 AI 分片内晋级；
4. 合并长期、条件和跟随资格，执行同族去重和空间子池对照；
5. 将翻向队列按证据处境、翻向形态和金融机制分桶，禁止只交付一个黑箱总数；
6. 通过顾问介入路由完成机器保留、未获票坐标关闭、本轮否决与同机制压缩；
7. 条件效力找不到已知状态时，只把最小金融机制考卷交给用户；
8. 形成“因子×空间×时间尺度×使用路线”资格台账；
9. 为获准输入生成 REAKA `input_compatibility_certificate`。

Stage 4 的当前实现为[`REAKA Stage 4 多尺度中央收敛`](reaka_stage4_multiscale_convergence_whitepaper.md)。其使用票身份包含交易许可与目标期，禁止跨期限、跨交易许可去重。收敛后的队列解释固定先进入[`Stage 4未解释因子分类`](reaka_stage4_advisor_queue_taxonomy_whitepaper.md)，再进入[`Stage 4金融顾问介入路由`](reaka_stage4_advisor_involvement_router_whitepaper.md)。

只有第 9 步通过，才能进入模型。

## 6. 从资格矩阵到 REAKA

| 项目 | 谁提供/冻结 | 输入规则 |
|---|---|---|
| 历史收益序列 | DataHub/FactorLab | PIT、时钟和目标严格对齐 |
| 因子和可观测状态 | 资格矩阵 + 用户/主控 | 保留原生更新频率，不插值伪造新信息 |
| 空间掩码 | 主控从 PIT 可观测描述量生成 | 不记股票代码或历史胜者 |
| 跟随权重 | 主控从已实现历史效力生成 | 严格滞后，回看与效力半衰期匹配 |
| 目标、频率、窗口 | 产品合同 + 数学兼容证书 | 检查 `H/Delta_x`、`W/H`、重叠和有效样本 |
| 潜维/算子数候选族 | 主控 AI | 用 `r_eff`、`n_k_eff/d^2`和扰动稳定性约束 |
| 残差/损失合同 | 主控 AI | 真实/生成残差同尺度，损失梯度可识别 |
| 组合、成本、换手 | 用户金融政策 + 主控实现 | 必须与因子考题同口径 |

### 6.1 成本不是一个对称常数

V1 的 `cost_bps_per_leg` 无法表达 A 股印花税只在卖出侧发生，也无法覆盖100万—1000万元资金对不同股票的冲击差异。V2 接入 `factor_rotation_ashare_execution_v1`：当前基线为买入4.6bps、卖出9.6bps，拆分手续费、过户费、卖出印花税和基础滑点；另以1/2/3倍滑点及委托规模—流动性压力检验容量。任何持仓延续都不得虚构一次卖出再买入的成本。

### 6.2 回撤和持股数处于不同层

- 因子层：必须报告最大回撤、左尾和持续性，但单因子回撤不作硬淘汰门；
- 组合层：研究因子互补、集中度和尾部，再决定持股数量；
- 持股数不得由最终回测收益事后挑选，必须作为有界组合候选进入搜索分母，并在整案评价前冻结；
- 产品层：始终满仓，若某条快路没有新信号，可以维持已有慢仓，但不能退到现金。

REAKA 自己学习 gate、潜状态、operator assignment、Koopman 矩阵、潜残差分布和预测分数。这些不得作为人工已知答案填进输入表。

## 7. 统计与证据边界

1. 同一年在多个频率中只是多个相关测量，不增加独立年份数；
2. 持有期大于决策间隔时，标签和仓位可重叠，必须报告 `n_eff` 和 block/HAC 处理；
3. 全部矩阵单元进入搜索分母，coverage gap 不等于失败，也不能从分母中消失；
4. 一个因子在周频通过、日频失败，只说明周频用法获准，不代表因子身份被删除；
5. 2009—2020 是已消费的研究材料，2021—2025 不得倒回来教新矩阵，2026 以后保持封闭。

## 8. 五位一体落点

- 白皮书：本文；
- 用户工作流：[`../user/reaka_product_driven_multiscale_research_workflow.md`](../user/reaka_product_driven_multiscale_research_workflow.md)；
- 当前机器合同：[`reaka_product_driven_multiscale_research@2.0.json`](reaka_product_driven_multiscale_research@2.0.json)；V1 只作历史血缘；
- 代码：`src/factor_lab/factor_rotation/reaka_product_driven_research.py`；
- 构建/验收：`scripts/factor_rotation/build_reaka_product_driven_research_workflow.py`、`scripts/factor_rotation/validate_reaka_product_driven_research_workflow.py`；
- 回归测试：`tests/unit/test_reaka_product_driven_research.py`。
- 首份产品包与外部 AI 提示词：[`evidence/reaka_product_driven_multiscale_research_v2_20260816/README.md`](evidence/reaka_product_driven_multiscale_research_v2_20260816/README.md)。
- Stage 3 单年裁决：[`reaka_stage3_annual_adjudication_whitepaper.md`](reaka_stage3_annual_adjudication_whitepaper.md)、[`reaka_stage3_annual_adjudication@1.0.json`](reaka_stage3_annual_adjudication@1.0.json)。
- Stage 4 中央收敛：[`reaka_stage4_multiscale_convergence_whitepaper.md`](reaka_stage4_multiscale_convergence_whitepaper.md)、[`reaka_stage4_multiscale_convergence@1.0.json`](reaka_stage4_multiscale_convergence@1.0.json)。
- Stage 4 队列分类：[`reaka_stage4_advisor_queue_taxonomy_whitepaper.md`](reaka_stage4_advisor_queue_taxonomy_whitepaper.md)、[`reaka_stage4_advisor_queue_taxonomy@1.0.json`](reaka_stage4_advisor_queue_taxonomy@1.0.json)。
- Stage 4 顾问介入路由：[`reaka_stage4_advisor_involvement_router_whitepaper.md`](reaka_stage4_advisor_involvement_router_whitepaper.md)、[`reaka_stage4_advisor_involvement_router@1.0.json`](reaka_stage4_advisor_involvement_router@1.0.json)。
- Stage 5 数学兼容证书：[`reaka_stage5_input_compatibility_whitepaper.md`](reaka_stage5_input_compatibility_whitepaper.md)、[`reaka_stage5_input_compatibility@1.0.json`](reaka_stage5_input_compatibility@1.0.json)。
- Stage 6 论文忠实日频训练：[`reaka_stage6_paper_faithful_training_whitepaper.md`](reaka_stage6_paper_faithful_training_whitepaper.md)、[`reaka_stage6_paper_faithful_training@1.0.json`](reaka_stage6_paper_faithful_training@1.0.json)。
- Stage 1—5 性能治理：[`reaka_factor_pipeline_performance_whitepaper.md`](reaka_factor_pipeline_performance_whitepaper.md)、[`reaka_factor_pipeline_performance@1.0.json`](reaka_factor_pipeline_performance@1.0.json)。

## 9. 与已有文档的关系

- 输入数学兼容性：[`reaka_input_mathematical_compatibility_whitepaper.md`](reaka_input_mathematical_compatibility_whitepaper.md)；
- 状态与因子同步研究：[`reaka_state_factor_joint_research_whitepaper.md`](reaka_state_factor_joint_research_whitepaper.md)；
- 三出口因子资格：[`reaka_factor_discovery_three_pathway_whitepaper.md`](reaka_factor_discovery_three_pathway_whitepaper.md)；
- 旧 V1 前置冻结：[`reaka_factor_development_prerequisites_whitepaper.md`](reaka_factor_development_prerequisites_whitepaper.md)，仅作历史已执行实例；
- REAKA 模型输入责任：[`reaka_human_model_authority_whitepaper.md`](reaka_human_model_authority_whitepaper.md)。
