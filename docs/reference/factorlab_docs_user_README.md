# 用户文档索引

- [REAKA多因子选股当前唯一工作流 V1.2](reaka_multifactor_current_workflow_v1_2.md)：Stage4机器证据已完成，当前只等待用户审核五个冻结的指数/行业金融机制；机器没有代签回执。
- 本索引其余 REAKA 条目只有在 [`current manifest @1.2`](../ops/reaka_multifactor_current_manifest@1.2.json) 显式列出并限定 scope 时才有局部 current 权限；否则一律是历史或专题导航。

- [LAT效率记忆V10工作流](market_state_lat_1m_policy_migration_workflow.md)：使用频段匹配、不重叠的P窗测试效率自持续、EWMA、AR和转移模型；结果否决简单效率硬门。

- [多频因子研究操作系统](multifrequency_factor_research_os_workflow.md)：共享假说主干、日/周/月/季四频分叉、四本编号账本、策略专属准入与反馈回路；[四lane并行交接](multifrequency_parallel_lane_handoff_workflow.md)冻结结果禁运和主控验收边界。

- [REAKA FINAL_V1实体因子外部执行工作流](reaka_final_entity_factor_external_workflow.md)：历史已关闭；三个lane均为`no_evidence`，九个公式全部消费，只有审计权。
- 历史三个独立提示词均已消费并从当前工作树删除；原始字节只在Git历史中保留，不得恢复分发。
- [REAKA残差生命周期跟随工作流](reaka_residual_lifecycle_following_workflow.md)：三个旧lane已经全部`no_evidence`并关闭；当前主控结果支持连续跟随行业残差水平与大小盘相对状态，不支持加速度择时或硬退出，等待真正未见共同挑战。
- [因子凝结指数工作流](factor_condensation_index_workflow.md)：当前“指数→动态个股因子载体”入口；19个L1和大小盘双核周频持续凝结，14个研究代理通过、7个语义漂移拒绝。等权只定义指数身份，不是持仓权。
- [动态市值标签工作流](dynamic_size_taxonomy_workflow.md)：小/大凝结核已经吃下；K=3/4/5均不能诚实发布为物理市值标签，中盘不是独立因子，物理市值与连续大小盘行为轴分离。
- [REAKA凝结载体再开发分支](reaka_condensation_redevelopment_branch_workflow.md)：B6完成根因重建；[B7全局准入](reaka_condensation_B7_admission_workflow.md)完成，两个候选均未准入，B8和训练关闭。
- [择时基础设施四层拆分工作流](timing_infrastructure_four_layer_split_workflow.md)：数据时钟 → K线测量 → 策略基础/时效原型 → 执行标的。步 A 清单 [`timing_infrastructure_four_layer_inventory@1.0.json`](../ops/timing_infrastructure_four_layer_inventory@1.0.json) 已冻。第 1 层造 bar 分工：[DataHub 造 / FactorLab 消费](timing_layer1_datahub_clock_split_workflow.md)。
- [Layer 2 下一窗路径效率因果预估](timing_layer2_next_path_efficiency_forecast_workflow.md)：预估接下来 H 根 K 线的 Kaufman ER，而不是跟随/反转回看平均效率。第一跑 `no_evidence`。
- [Layer 2 隐含日内反转 K 线属性](timing_layer2_implied_intraday_reversal_workflow.md)：消费第1层时段时钟，V1.2 按涨跌幅1%与振幅2%做主桶，再按周线情境拆三桶。
- [Layer 2 隔夜高低开账本](timing_layer2_overnight_gap_ledger_workflow.md)：@1.2 补充。中证1000 隔夜 ±30bp 为普通开盘，高开/低开尾部账本；消息只记第一天。
- [第4层 V2.0 MO 账户回测工作流](timing_layer4_account_backtest_v2_workflow.md)：当前第4层入口。真实 PIT 价格路径接入后，使用每次装配固定的最近一年流动性/容量/冲击 snapshot 执行账户风险、成交代价、持仓、结算和 NAV 对账。
- [Layer 4 ETF 期权相对 MO 对等闭合工作流](timing_layer4_etf_option_mo_parity_workflow.md)：五位一体校验与构造入口。无经济路由权。
- [Layer 4 期权工具身份画像工作流](timing_layer4_option_instrument_profile_workflow.md)：当前路由前置。先侧写不同期权工具，再重审 D1–D5。无成交改写权。
- [Layer 4 分层期权路由工作流](timing_layer4_hierarchical_option_router_workflow.md)：D1–D5 决策身份暂留，待画像完成后重审。无经济路由权。
- [Layer 4 提问状态机 × HF12 稀疏交易 V1](timing_layer4_question_machine_hf12_sparse_state_workflow.md)：修复退出 BBO 管道并固化首个正收益低自由度状态门；只是 retrospective progression，无选参/生产权。
- [Layer 4 提问状态机 × HF12 做多分布风险 V2](timing_layer4_question_machine_hf12_long_distributional_v2_workflow.md)：分开盈利/失败风险、典型/存活持有期并用 Black-76 翻译；未超过 V1，状态为 no increment。
- [Layer 4 HF12 最小最坏 Delta 复制误差 V3](timing_layer4_question_machine_hf12_delta_replication_v3_workflow.md)：不预测期权收益，只最小化未预测Greeks对Layer3方向暴露的污染；优于V2但未超过V1。
- [跨频收益机会与稳定性潜力 V2 工作流](cross_frequency_opportunity_stability_infrastructure_workflow.md)：25频段、段间状态重置、端到端L1漏斗、高斯/Rademacher敏感性、四offset边界图和双Pareto入口；[@2.0当前注册表](../ops/cross_frequency_opportunity_stability_registry@2.0.json) 与 [V1撤权/V2当前性](../ops/cross_frequency_opportunity_stability_version_registry@1.0.json)机器可查。
- [CSI1000中频资产成本纠正V2工作流](csi1000_medium_frequency_asset_cost_corrected_workflow.md)：当前唯一入口。股票1+6bp不得进入指数/MO；指数信号零显式成本，MO长期权Ask买/Bid卖且只扣14+14元。纠正后开发与重复信号均由LAT P34/510分钟领先；[版本链](../ops/csi1000_medium_frequency_limited_history_version_registry@1.0.json)已撤销V1。
- [中证1000ETF 15m LAT 万二/T+1重算](csi1000_etf_t1_2bp_frequency_reprice_workflow.md)：512100长仓/现金，买卖各1bp、严格T+1；佣金-only历史最优保留P49，完整成本和生产权关闭。
- [择时资产类别成本边界](timing_asset_cost_boundary_workflow.md)：当前 `@2.0`。股票、股票ETF、指数信号、MO长期权和MO短期权合同硬隔离；Bid/Ask是成交价格，显式期权成本只有固定手续费。V1 只保留历史复现。

- [REAKA并行因子提案沙盒](reaka_factor_proposal_parallel_sandbox_workflow.md)：支持定向或开放lane，每lane先多假说、最多3个结果前公式，再做2009--2018三段自验证和机器交接；主控beta加速度试跑为负但工作流通过，当前尚未授权实际并行分发。
- [REAKA因子提案沙盒收官验收](../ops/evidence/reaka_factor_proposal_sandbox_closeout_v1_20260827/controller_acceptance.md)：0.1基础设施与负终态试跑均通过；建议并行拓扑已冻结为评审稿，等待用户决定是否升1.0。

- [REAKA开荒后的因子再开发](reaka_post_pioneer_redevelopment_workflow.md)：区分工程更新与策略后继开发；新增因子不重跑Stage0和旧因子材料，先做delta Stage2→十二年delta审阅→Stage4全局合并，只有准入后才重建Stage5→Step8。
- [REAKA开荒收官验收](../ops/evidence/reaka_post_pioneer_closeout_v1_20260827/controller_acceptance.md)：当前版本开发完成。下一主问题是补高β成长行情参与；只开放有界候选公式预注册，当前策略、训练与生产均不变。

- [REAKA Step7 Koopman 容量 V2](reaka_step7_capacity_v2_workflow.md)：已由主控完成零标签预检、CPU/ROCm选路、三候选三种子训练、双运行和验收，选中 `d8-K2`。开荒后基础设施审计也已纳入同一工作流；当前只进入 Step8 合同冻结。
- [REAKA Step8 残差研究合同](reaka_step8_residual_contract_workflow.md)：已进入步骤8第一小步。先冻结零残差、条件线性/最小MLP、论文DRC的层级门；当前不得训练残差。
- [REAKA Step8 简单残差关闭](../ops/evidence/reaka_step8_simple_v1_20260827/controller_acceptance.md)：已双运行完成零/线性/MLP对照，保留零残差并关闭DRC。下一步是主控冻结组合装配与 incumbent battle 合同。
- [REAKA Step8 固定完整模型直接回测](reaka_step8_fixed_model_backtest_workflow.md)：当前权威纠偏入口。年度只报告不重建，固定模型、组合和 incumbent。数据/incumbent replay 预检已通过，下一步建设确定性 runtime 后直接回测。
- [REAKA Step8 固定回测审计后继](../ops/reaka_step8_fixed_model_backtest_contract@1.1.json)：当前组合分数是三种子逐日rank-z后等权ensemble；320,490行全冻结分数宇宙交易资格已物化。只开放runtime/validator/admission建设，尚未计算NAV。
- [REAKA Step8 评分身份修复工作流](reaka_step8_score_identity_repair_workflow.md)：V1 经济关闭因 shifted/full-window 评分身份错位撤销。V2 逐值绑定 Step7 三种子权威分数，先过五维基础设施审计，再原样重放固定组合；不调参、不读2021+。
- [REAKA Step8 V2 主控验收](../ops/evidence/reaka_step8_fixed_internal_v2_20260827/controller_acceptance.md)：正确评分下年化/Sharpe相对透明基线`+4.26pp/+0.162`，2019/2020均为正；当前冻结研究候选，外部incumbent battle因无完整原生共同期关闭。
- [REAKA V3 Context 层级纠偏与 Step5--7 恢复](reaka_factor_authority_v3_workflow.md)：当前主控恢复入口。Context 已降回可选因子；baseline-only Step6 和 Step7 容量研究已通过，当前身份 `latent=8,K=2`。[机器合同](../ops/reaka_factor_authority@3.0.json)。
- [REAKA 产品驱动多尺度因子研究工作流](reaka_product_driven_multiscale_research_workflow.md)：当前操作首入口。首份产品已冻结主动多头、全A候选+自动子集、1/5/10日交易许可、20/40日慢目标、始终满仓和真实不对称成本。主控生成矩阵及外部 AI 前两段提示词；年度封存、全局校正、三出口、兼容证书和 REAKA 训练仍归主控。
- [REAKA Stage 4 未解释因子分类](reaka_stage4_advisor_queue_taxonomy_workflow.md)：将每次的“95个/60个”黑箱队列自动拆成证据处境、翻向形态、金融机制和用法持续性四类桶；保留因子身份与期限/交易许可用法两层，不做事后挑选或状态发现。
- [REAKA Stage 4 金融顾问介入路由](reaka_stage4_advisor_involvement_router_workflow.md)：分类后由机器先落实保留、关闭和本轮否决，只把同机制共同翻向簇压缩成最小用户考卷。当前95个因子中89个已由机器处理，其余6个压缩为1道金融机制问题。
- [REAKA 基本面—流动性双驱动Case](reaka_fundamental_liquidity_driver_case_workflow.md)：用户对ADV-001的金融回执已完成实证。2020年后超额流动性和驱动概率差的极端波动确实收窄；但24个宏观轴×领先期检验0个过BH。ADV-001已关闭：状态保留为历史有效、当前低活跃的背景监控；六因子本轮关闭为模型输入，仅留事后诊断价值。
- [REAKA Stage 6论文忠实日频训练与单次外包](reaka_stage6_paper_faithful_training_workflow.md)：历史冻结工作流，当前外包权已被 V3 关闭；不得转发旧 `external_ai_stage6_single_execution_prompt.md`。
- [REAKA换主控述职交接 2026-08-26](reaka_controller_succession_handoff_20260826.md)：上一任主控述职。给下一任控制器，不是执行提示词。记录接手以来的验收、外部成果、基础设施修改依据，以及已撤回的9格筛选。
- [REAKA透明联合核心顾问门 C 审查请求](reaka_joint_core_freeze_review_request_20260826.md)：历史顾问材料。它不再拥有把 Context 升格为论文主干或系统阻断门的权限。
- [REAKA透明核心主动暴露归因外部交接](reaka_joint_core_active_exposure_attribution_external_ai_handoff.md)：历史已消费计算任务，当前不得转发。其暴露账本只保留候选因子诊断权，不是论文主干门。
- [REAKA 2009–2020单股PIT行业归属消费能力外部交接](reaka_pit_industry_membership_consumer_external_ai_handoff.md)：历史交接，不得原样重跑。首次 attempt `33051032` 读取 post-2020 详细行且 digest 漂移；v1.1 clean successor `f548a675` 已修复边界和digest，主控收下出口B测量，但仍要求修复builder字节重放。
- [REAKA论文参数治理工作流](reaka_paper_parameter_governance_workflow.md)：金融意图必须先编译成22项数学合同。当前 Step7 已选中 `d8-K2`，下一步是冻结 Step8 残差合同，不是恢复旧9格选参。
- [REAKA步骤6神经保真历史外部交接](reaka_step6_neural_fidelity_external_ai_handoff.md)：已撤权，只读。
- [REAKA步骤6神经保真后继外交接](reaka_step6_neural_fidelity_successor_external_ai_handoff.md)：已消费并被主控拒收，不得原样重跑。它只证明 Context 候选失败，不再拥有 REAKA 主干阻断权。
- [REAKA Stage5论文latent K1残差编译](../ops/reaka_stage5_parameter_compilation@1.1.json)：历史只读的顺序倒置编译，无当前路由或训练权。
- [REAKA Stage6论文latent K1残差主控验收](../ops/evidence/reaka_stage6_paper_latent_k1_residual_controller_acceptance_v1_20260826/controller_acceptance.md)：身份探针通过，不是容量或因子结论。
- [REAKA Stage6论文latent K1残差校准筛选外部交接](reaka_stage6_paper_latent_k1_residual_screening_external_ai_handoff.md)：已撤回，只读。9格选参不是当前下一步。
- [REAKA Stage6论文latent K1残差外部交接](reaka_stage6_paper_latent_k1_residual_external_ai_handoff.md)：历史交接，只读。身份探针已验收，不得再跑同一预检。
- [REAKA Stage5残差身份](../ops/reaka_stage5_residual_identity@1.0.json)：历史只读。不得把gamma=0身份冒充论文DRC。
- [REAKA Stage5残差身份工作流](reaka_stage5_residual_identity_workflow.md)：冻结残差身份；下一动作是Stage5参数闭包。
- [REAKA Stage5参数身份门与因子效力门](../ops/reaka_stage5_identity_factor_gates@1.0.json)：历史只读。不得再派同一家族探针，也不得把GateB失败写成因子无效。
- [REAKA Stage5参数身份门与因子效力门工作流](reaka_stage5_identity_factor_gates_workflow.md)：冻结两扇门；同类探针未授权。
- [REAKA Stage5无增量继任](../ops/reaka_stage5_no_incremental_successor@1.0.json)：历史只读。不得把K1发布为新策略版本，不得再跑受限confirmation。
- [REAKA Stage5无增量继任工作流](reaka_stage5_no_incremental_successor_workflow.md)：冻结当前科学状态；无外部执行提示词。
- [REAKA Stage5透明主干身份封存](../ops/reaka_stage5_baseline_identity_closeout@1.0.json)：历史只读。不得宣布容量赢家，不得再跑受限confirmation。
- [REAKA Stage5透明主干身份封存工作流](reaka_stage5_baseline_identity_closeout_workflow.md)：冻结当前合同；不得再跑受限confirmation或启动formal fit。
- [REAKA Stage5容量/学习率联合合同](../ops/reaka_stage5_capacity_lr_joint@1.0.json)：历史只读。受限confirmation家族只有h32@0.1；不得从原三hidden选出容量赢家。
- [REAKA Stage6受限confirmation主控验收](../ops/evidence/reaka_stage6_restricted_confirmation_h32_lr0p1_controller_acceptance_v1_20260825/controller_acceptance.md)：测量通过，selected coverage=4是透明主干`gamma=0`身份，hidden未选中。
- [REAKA Stage6受限confirmation外部交接](reaka_stage6_restricted_confirmation_h32_lr0p1_external_ai_handoff.md)：历史交接，只读。不得再跑h32@0.1受限confirmation，也不得创建controller_acceptance。
- [REAKA Stage6 V2.3学习率边界外部交接](reaka_stage6_v2_3_lr_boundary_external_ai_handoff.md)：历史交接，只读。V2.3测量已验收，整案边界未闭合，不得再派0.3/1.0。
- [REAKA Stage6 V2.2学习率边界外部交接](reaka_stage6_v2_2_lr_boundary_external_ai_handoff.md)：历史交接，只读。当前合同已转到v1.2，不得再派`0.3→1.0`。
- [REAKA 输入数学兼容性工作流](reaka_input_mathematical_compatibility_workflow.md)：当前执行入口为[Stage 5证书](reaka_stage5_input_compatibility_workflow.md)，证书已获 `compatible_with_claim_limitations`。外部AI/主控提速路径见[REAKA全流程性能工作流](reaka_factor_pipeline_performance_workflow.md)。
- [REAKA V2.4 深度 2 回顾性装配工作流](reaka_v2_4_depth2_retrospective_workflow.md)：工程验收保留，但现定位为 FactorLab 月频适配诊断。共同 40 个月上透明 Rank `+11.44%`、完整扩散 `-4.76%`；扩散残差尺度未校准，不授权否定论文日频框架。2021—2026 未打开，生产权关闭。
- [REAKA V2.3 候选收敛与 V2.4 事前方案](../ops/evidence/reaka_factor_development_v2_3_20260816/controller_final_acceptance_and_v2_4_plan.md)：106 因子三通道输入的上游冻结血缘；恢复当前研究必须先读 V2.4 工作流和白皮书。
- [REAKA V2.1 因子开发纠偏与验收工作流](reaka_factor_development_v2_1_acceptance_workflow.md)：历史纠偏流程；当前实施与恢复从 V2.2 最终验收和 V2.3 收敛方案进入。
- [外部 AI：REAKA V2 因子开发原执行提示词](external_ai_reaka_factor_development_v2_execution_prompt_20260815.md)：保留为历史执行合同；新运行必须先经 V2.1 验收工作流。
- [REAKA 因子专属股票池自动发现 V2](reaka_factor_carrier_subset_discovery_workflow.md)：当前载体轴入口。输入因子、候选股票和 PIT 描述量，由系统自动发现可复现的因子专属股票池；发现候选必须在不重叠材料上确认。预设市值桶只作保底，不是主方法；下游进入[`REAKA 状态—因子联合研究手册`](../ops/reaka_state_factor_joint_research_whitepaper.md)和[`reaka_state_factor_pair_workflow@2.0.json`](../ops/reaka_state_factor_pair_workflow@2.0.json)。
- [REAKA 因子开发前置冻结工作流](reaka_factor_development_prerequisites_workflow.md)：三出口运行前的两个前置步骤。冻结第一轮候选因子池（197 个 canonical 个股 alpha）与统一研究口径，交付后等待主控 AI 验收；不得自行启动效力画像或三路并行研究。构建/验证命令与失败关闭条件见工作流，白皮书见 [`../ops/reaka_factor_development_prerequisites_whitepaper.md`](../ops/reaka_factor_development_prerequisites_whitepaper.md)。
- [市场状态发现：已完成上游](authoritative_market_state_discovery_workflow.md)：当前 8 条用户重述后命题均获支持，并已完成 XDXR V9 数据复验/迁移审计。权威结论见[白皮书](../ops/authoritative_market_state_catalog_whitepaper.md)，机器真相见[`authoritative_market_state_catalog@2.0.json`](../ops/authoritative_market_state_catalog@2.0.json)。状态准备门已完成，但最新 2009—2020 状态×因子族扫描没有产生严格晋级单元；透明候选重建和策略总收益回测未开始。
- [AMS-008 火电轮动末端领先状态手册](ams008_firepower_late_rotation_state_workflow.md)：当前入口；火电 5 日残差领先 RV5 扩波/换阶段的状态层已通过。直接扩波测量显示历史上约六成向下，但“必跌”和独立做空权限未冻结。
- [AMS-008 旧 20 日口径手册](ams008_industry_relative_strength_cloudridge_volatility_workflow.md)：历史失败血缘，不再代表当前 AMS-008 语义。
- [REAKA 因子挖掘三出口与输入装配工作流](reaka_factor_discovery_three_pathway_workflow.md)：当前唯一入口。同一严格滞后画像并行判断长期有效、条件有效和可跟随；可跟随必须预测未来扣费因子收益。三出口不复制因子身份，按原始因子一次＋连续状态/滞后效力交互交给 REAKA。旧[双通道工作流](reaka_factor_discovery_dual_channel_workflow.md)仅作历史重放。
- [REAKA 因子载体轴与预设子集 V1](reaka_factor_carrier_axis_workflow.md)：自动发现缺少合格 PIT 描述量或覆盖不足时的保底入口；不得冒充 V2 自动股票池发现。
- [状态—策略 / 状态—因子假设池使用说明](state_factor_strategy_hypothesis_pool_workflow.md)：完整历史台账入口，保存成功、失败、修订和退役血缘；不再承担“当前市场状态真相”的职责。当前结论必须回到权威市场状态目录。
- [分布—波动率状态操作手册](state_distribution_volatility_regime_workflow.md)：重述口径的专项证据入口；U-SH-006/007/008 的证据只用于支撑对应 `AMS-*` 最终命题，不得恢复被替代的原始措辞。
- [状态—因子活跃输入历史手册](state_factor_active_inputs_v2_workflow.md)：V2/V3 保留历史合同；V3 绑定已退役 XDXR V8，不能作为当前配对输入。当前后继从[多因子 V9 数据准备手册](multifactor_research_data_readiness_workflow.md)进入。
- [REAKA 人机职责与 V2 工作流](reaka_paper_v1_workflow.md)：先从 TOP 级[职责白皮书](../ops/reaka_human_model_authority_whitepaper.md)理解可研发输入与模型学习边界，再区分旧代理、公式忠实 V1 和一次冻结训练 V2。V2 六项训练健康门全过，但扣费年化多空 `-2.54%`，经济表现未通过；[三层归因](../ops/reaka_best_practice_v2_layer_attribution_whitepaper.md)显示因子底座 `-3.53%`、状态 `+0.69pp`、残差 `+0.30pp`，且主要改善来自状态×残差协同。
- [REAKA V3 严格因子总表与输入增量](../ops/evidence/macro_regime_v1_vs_reaka_v1/reaka_factor_uplift_v3_20260811/README.md)：310 项身份已逐项归档，186 个严格原子因子完成统一表，结果前筛出 6 非财务 + 8 财务。原始最好臂为 `-3.17%`，但三个财务臂均未通过训练健康门；健康合格最好仍为 `-4.64%` 非财务基线。恢复研究必须先读 [`health_adjudication.json`](../ops/evidence/macro_regime_v1_vs_reaka_v1/reaka_factor_uplift_v3_20260811/health_adjudication.json)与[`deterministic_replay.json`](../ops/evidence/macro_regime_v1_vs_reaka_v1/reaka_factor_uplift_v3_20260811/deterministic_replay.json)，不得把原始排名写成财务因子准入。基线复跑逐对象一致，机器台账序号 28、科学票 4。
- [REAKA 论文公式版 V1 工作流](reaka_paper_v1_workflow.md)：新挑战者的唯一操作入口；区分旧代理与公式版，说明冻结 spec、确定性重放、训练健康门、已消费考卷禁止事项和日频 Alpha158 恢复点。当前是“架构完成、训练健康阻断”，不是策略替换。
- [REAKA 非财务论文输入面](../ops/evidence/macro_regime_v1_vs_reaka_v1/reaka_nonfinancial_input_closure_20260811/README.md)：已真实物化全可见股票日频 Alpha158、同坐标历史日收益与六档因子家族温度；这是可重放输入基础设施，不是新训练结果或论文数值复刻。
- [宏观多因子双策略并行开发工作流](macro_regime_dual_strategy_workflow.md)：多因子总入口；原策略、旧 REAKA 代理和新论文公式版身份隔离。正式 Round 3 已接入 DataHub 21 个严格年报财务因子：旧 REAKA / incumbent 为 `+0.12% / -5.55%`，但区间跨 0、挑战者回撤更大，所以无正式胜者。论文日频 Alpha158、同步历史收益与家族温度已完成全市场 10 交易日输入验收；尚未用它做长历史训练或新收益实证。已消费的 2021—2025 不得因换 mechanism 而重开科学票。证据从[实证索引](../ops/evidence/macro_regime_v1_vs_reaka_v1/README.md)进入。
- [宏观状态条件化多因子策略工作流](macro_regime_conditioned_multifactor_workflow.md)：双策略体系中的 incumbent 路线入口；先读永久台账、架构 readiness 和具体 dataset consumer contract，再逐层开发。已授权 CSRC 行业指数 Phase 1 的 harness 与重放通过，但共享四因子组合未通过历史支持门；该 Phase 1 的宏观数值仍未补入旧基线；严格财务已在双策略 Round 3 接通，但个股评分和生产权仍关闭。
- [行业因子一 / 因子二 V3 诊断入口](../ops/evidence/macro_regime_v1_vs_reaka_v1/industry_factor_one_two_diagnostic_20260811/README.md)：旧 V7 不可消费，V2 因未来时间戳无效；行业因子一的 13 个历史 prior 尚无严格行业 PIT，行业因子二仅成交额活跃度异常在两段已消费历史重复为正，方向臂近重复，结构与筛选非正。该诊断 `fresh_oos=false`、科学票增量 0，不进入训练、评分或生产。
- [CloudRidge IIR 逐棒否决研究工作流](cloudridge_iir_per_bar_veto_workflow.md)：否决不得锁存整笔事件；两个入场质量候选已通过前训练、后验证，D信号的毛方向价值无法支付逐棒退出—恢复成本。
- [CloudRidge IIR 单笔大亏损逐棒否决工作流](cloudridge_iir_tail_loss_per_bar_veto_workflow.md)：专门处理已有IIR持仓中的持续下行尾部风险；历史冻结验证通过，fresh OOS与生产权仍为否。

- [CloudRidge IIR 市场层面否决专家研究工作流](cloudridge_iir_market_veto_experts_workflow.md)：先在市场全样本证明风险状态的独立负向长仓价值并冻结，再与裸 IIR 取交集计动作价值；F/D/G 本轮被拒绝、J 为 diagnostic_only，不授予生产权。
- [CloudRidge IIR D-v2 持仓结构破坏/下跌延续专家研究工作流](cloudridge_d_v2_structure_break_expert_workflow.md)：v1 失败根因纠错（close-only→OHLC 硬破位族、本频走弱确认、动作分级）；三确认 H+C+P 在训练折未过门槛，裁决 `rejected_candidate_set`；裸 IIR 不变，`production_authority=false`。
- [CloudRidge IIR D-v3 持续性门槛专家研究工作流](cloudridge_d_v3_persistence_gate_expert_workflow.md)：用因果 `causal_failed_reclaim` 门槛替代 H+C+P 三确认；L1/L2 独立解耦（门槛已隐含 persist2，叠加 P 会削减 85% 样本）；8 状态全过 Stage 1（训练 timing=1.0），OOS timing=0.4595 反向预测，错杀赢家 -0.241 >> 正确避开 +0.033；裁决 `rejected_candidate_set`；裸 IIR 不变，`production_authority=false`。
- [CloudRidge IIR D-v4 选择规则重做研究工作流](cloudridge_d_v4_selection_rule_redo_workflow.md)：用 PTSS（n_events desc / cross-subfold CV asc / simplicity asc）替换 D-v3 Stage 1 按 `effect_mean_diff` 升序排序的过拟合规则；PTSS 完全不读取效应值（monkey-patch 反过拟合保证）；冻结 D-v3 8 状态族原样复用；选中 `D_v3_w5_gate4_body0`，OOS timing 0.4595→0.982、net_delta 7bps -0.207→+0.032、错杀 -0.241→-0.031；裁决 `accepted_iir_veto`（D 系列首个被接受专家），`production_authority=false`。
- [CloudRidge IIR D-v5 大周期下推独立 L2 工作流](cloudridge_d_v5_large_cycle_down_thrust_l2_workflow.md)：将 `large_cycle_down_thrust` atlas 类别提取为独立 L2 触发器（`parent_down_60m AND low_slope_z<=threshold`）；8 个预注册状态全未通过 Stage 1 timing gate（最佳 0.5928 < 0.90）；触发器太宽泛（83% 基线事件被触发）；裁决 `frozen_shadow_candidate`（未进入 Stage 2 OOS）；atlas 事后分类不适合实时 L2 触发，`production_authority=false`。
- [CloudRidge IIR D-v6 波动率 regime 分级工作流](cloudridge_d_v6_volatility_regime_classification_workflow.md)：将 D-v3 冻结 8 状态族按 `volatility_z`（16 根滚动 std 的 z-score，严格 PIT）分成 3 桶（low_vol / normal_vol / high_vol）共 24 状态，按 regime 分别用 PTSS（n_events / CV / simplicity，不读取 effect_mean_diff）选状态；low_vol 与 normal_vol 因事件太少或 CV 过高未过 Stage 1 eligibility；high_vol 选中 `D_v6_high_vol_D_v3_w5_gate4_body0`（n=37、cv=0.590），Stage 2 OOS timing_pct=0.9475（略低于 0.95 门槛）、net_delta 7bps=+0.0156（正净_delta）、right_tail=1.0；物理假设被证实（高波动率 regime 中门槛更有效），但 stratification 不及 D-v4 unstratified（+0.0323），仅作为诊断确认；裁决 `rejected_candidate_set`，`production_authority=false`。
- [CloudRidge IIR D-v7 失败收回后验振幅阈值工作流](cloudridge_d_v7_failed_reclaim_amplitude_threshold_workflow.md)：在 D-v3 冻结 8 状态族上叠加振幅后验阈值（`hard_break_volscaled_{w} >= A`，A ∈ {0.0, 0.5, 1.0, 1.5, 2.0}，预注册固定，严格 PIT），共 40 状态；PTSS（A. n_events / B. CV / C. simplicity / D. state_id 字典序，不读取 effect_mean_diff）选中 `D_v7_amp0_D_v3_w5_gate4_body0`（amp=0.0、n=68、cv=1.119），Stage 2 OOS timing_pct=0.982、net_delta 7bps=+0.0323、right_tail=0.998；关键发现：所有 amp>=0.5 状态在训练折 n_events=0 或 1，故 PTSS 自然选 amp=0.0；D-v7 amp=0.0 等价于 D-v4，振幅过滤不增加正交信息；裁决 `accepted_iir_veto`（D 系列第二个被接受专家，技术满足接受门但科学上是 D-v4 的确认），`production_authority=false`。
- [CloudRidge IIR D-v8 外部风险确认因子集成工作流](cloudridge_d_v8_external_risk_confirmation_workflow.md)：在 D-v3 冻结 8 状态族上叠加 5 个外部风险确认因子层（breadth_thrust / order_flow_divergence / implied_volatility_regime / skew_steepening / put_call_ratio_spike），每因子单一预注册阈值（0.5/0.5/1.0/1.0/0.5），共 40 状态；PTSS（A→B→C→D，不读取 effect_mean_diff）选中 `D_v8_implied_volatility_regime_D_v3_w5_gate4_body0`（factor=implied_volatility_regime、threshold=1.0、n=49、cv=0.8275、simplicity=10002）；正交性审计证实全部 5 个代理因子均 NON-ORTHOGONAL（breadth_thrust 用 log_return、order_flow_divergence 用 price_path_efficiency16、implied_volatility_regime 用 vol_z640、skew_steepening 用 vol_of_vol、put_call_ratio_spike 用 slope_cancellation），均重用 CloudRidge 派生列；Stage 2 OOS timing_pct=0.9090、net_delta 7bps=-0.0161（透明度报告，不覆盖正交性边界）；裁决 `rejected_candidate_set`（正交性边界违反 per bd fl-jzl1）；本轮交付 (a) 5 因子摄取规格、(b) PIT 验证框架、(c) 正交性审计、(d) 被拒绝的 OOS 测试；CloudRidge panel 缺少所有 5 类外部数据，所有因子必须用价格派生代理；D 系列第 8 轮、用户授权的第 5 个也是最后一个有界研究方向；`production_authority=false`。
- [IIR专家分级证据门工作流](iir_specialist_evidence_gate_workflow.md)：分开机制识别、冻结动作价值、家族显著性与尾部集中；90%家族线只授权fresh OOS shadow，95%强历史线也不自动授予生产权。
- [IIR损失图形归因工作流](iir_loss_graph_attribution_workflow.md)：在开发任何否决、等待、减仓或退出专家前，先生成完整损失总账、互斥主因、频段反事实、近邻赢家和图形图册，再按候选可回收价值排序。
- [失败研究知识台账](negative_research_ledger_workflow.md)：失败也必须留下图形、已试机制、数据消费和有限否定边界；阻断同数据同机制只换阈值重试。
- [CloudRidge IIR 正交否决迭代](cloudridge_iir_orthogonal_veto_round_workflow.md)：完整执行图形归因、因子挖掘、冻结分块验证和失败留账。
- [CloudRidge IIR 入场支撑破位/扫损收复](cloudridge_iir_entry_support_reclaim_workflow.md)：真实15分钟OHLC证明市场级接受破位弱于扫损收复，但固定有效期不能直接映射为IIR否决；“更低高点＋更低收盘”仅为支持不足的诊断性正信号。
- [CloudRidge IIR 事件同步支撑风险](cloudridge_iir_event_synchronous_support_risk_workflow.md)：用收盘收复取代固定事件年龄；CloudRidge影子正信号未经跨ETF合计确认。
- [CloudRidge IIR 市场领导收窄新锁箱](cloudridge_iir_style_narrowing_fresh_lockbox_workflow.md)：真正新数据上否定冻结q67一次入场否决，禁止重调阈值救活。
- [副频段相位 × 原K线斜率 IIR 否决专家工作流](cloudridge_3_0_parent_phase_raw_slope_veto_workflow.md)：保留副频段早期下行与原K线中期弱势，用4根相对16根反弹加速度保护右尾；历史时间外6/6亏损，当前仅为待fresh OOS的shadow候选。
- [IIR 七频带可重构归因工作流](cloudridge_3_0_neighbor_reconstruction_attribution_workflow.md)：正式 Owen 分解门通过；v1 因未来持续时间筛样废止，纠错后的 v2 图形修正器仍未打赢裸 IIR，不启用动态邻频权重。
- [全局通道与 R3 独立策略复跑工作流](cloudridge_independent_long_experts_workflow.md)：完全移除IIR条件，分别复跑两个裸策略及训练期专属硬否决；当前只允许裸策略进入后续shadow。
- [Risk-Off 稀有事件、多层稀疏单调 GAM 工作流](risk_off_sparse_monotone_gam_workflow.md)：浅树规律发现、独立因子验证、三层 GAM、确定性状态机、220 个 9/3 挑战和完整策略质量总门。
- [Risk-Off 条件性因子严格验证工作流](risk_off_conditional_factor_validation_workflow.md)：预注册 PIT 条件、事件级条件账本、条件内效应/条件外无害、train-only 重选与因子×条件共同多重检验；不放宽普适因子门。

本目录保存面向使用者的任务指南。这里解释“怎么用”，不承载架构裁决、机器契约或内部运维 runbook。
本目录只记录后端化转换期内的后端/headless 使用任务；
但新增前端产品/交互指南应进入策略项目外壳 `../docs/`，不应扩大本目录的 UI 职责。

如果你只是接手项目，先回到 [`../00-index.md`](../00-index.md) 或 [`../../ai-readme.md`](../../ai-readme.md)。如果你已经知道要做什么，从下方任务路径进入。

使用本目录时按文件资产角色理解：文档、白皮书、Python 文件、测试、schema 和可复用配置/模板 JSON 属于**工具类文件**；由工具生产并冻结的 strategy result JSON、决策卡、发布 manifest 或账户机会表结果才属于**策略类文件**。文件类型本身不决定分类，JSON 不自动等于策略；`output/`、`artifacts/`、`.local/` 和 `.omx/research-notes/` 下的运行输出默认只是研究证据产物。

---

## 常用任务路径

| 任务 | 推荐链路 |
|---|---|
| 用切片素材开发、渐进优化并完成训练后账户审计 | **项目强制入口：**[`$strategy-slice-rebuild`](../../.codex/skills/strategy-slice-rebuild/SKILL.md) → [年度工作流](strategy_slice_rebuild_workflow.md) → [渐进开发工作流](strategy_progressive_development_workflow.md) → [K/残差纳入工作流](koopman_residual_admission_workflow.md) → [策略科学验收工作流](post_training_strategy_science_acceptance_workflow.md) → [账户快照/两账本工作流](post_training_account_research_bundle_workflow.md) → [SSA合同@1.0](../ops/post_training_strategy_science_acceptance@1.0.json) / [项目账户合同@1.1](../ops/post_training_account_audit@1.1.json)。隔离分支使用十二个自然年顺序会话；硬原理零妥协，弱但真实改善保留；模型/分数冻结后先做策略科学验收，通过才执行A0—A7，并以一次账户快照复用机会账本、逐笔收益账本和后续报表。 |
| 执行项目级 / 策略级基础设施治理 | [governance_execution_workflow.md](governance_execution_workflow.md) → [../ops/project_strategy_infrastructure_governance_whitepaper.md](../ops/project_strategy_infrastructure_governance_whitepaper.md)；先分类 project_level / strategy_level / historical_evidence，再决定归位、合并、拆分、迁移或归档。 |
| 验收项目级 K 线市场状态地基 | 先从[市场状态地基总入口](market_state_foundation_workflow.md)进入；V3 再进入[公式派生与联合状态机工作流](market_state_formula_derived_state_machine_workflow.md)，配套[外部 AI 五路提示词](market_state_formula_derivation_external_ai_prompts.md)、[数学白皮书](../ops/market_state_formula_derived_state_machine_whitepaper.md)、[ADR-029](../adr/ADR-029-market-state-formula-derived-joint-policy-v3.md)与[V3总验收](../ops/evidence/market_state_formula_derived_infrastructure_v3_acceptance_20260731.md)：第一段零数据派生/注册，第二段完整有界联合家族嵌套验证，第三段冻结机械验收。[三段式 AI 研究工作流](market_state_three_stage_ai_research_workflow.md)仅承载 V1/V2 包只读兼容；全链不生成生产策略路由。 |
| 构建全市场/制造业群体相关指标 | 进入[群体相关性市场状态工作流](group_correlation_market_state_workflow.md)；从DataHub最新READY日线每日增量计算20/60/120日三指标，两个股票池统一注册；成员质量仅作口径说明，不判断指标或策略有效性。 |
| 构建择时六轴公共环境 | 进入[择时策略六轴市场状态工作流](market_state_timing_six_axis_workflow.md) → [白皮书](../ops/market_state_timing_six_axis_whitepaper.md)；生成方向、方向记忆、波动水平、波动记忆、路径尾部和截面共振日序列，同时固化参数映射与禁止重复计票合同。 |
| 统一查询公共状态与工具专属因子 | 进入[六轴与工具专属因子统一基础设施工作流](market_state_unified_timing_factor_infrastructure_workflow.md) → [白皮书](../ops/market_state_unified_timing_factor_infrastructure_whitepaper.md)；一条 build、一条 validate、一个 query 入口按工具/因子/参数/缺口四视角回答"当前有哪些公共底层状态、某工具还需哪些专属因子、哪些只是定义、哪些已有证据、哪些仍是缺口"；复用不复制六轴与冻结 R2F 包，权限全部为 false。 |
| 登记并治理项目级市场情绪因子 | 进入[市场情绪四路因子库整合工作流](market_sentiment_factor_library_integration_workflow.md) → [白皮书](../ops/market_sentiment_factor_library_integration_whitepaper.md)；登记下跌广度、同步传染、恐慌流动性和风险偏好共82个FeatureSpec，物化、同根去重、策略证据和交易权限分别记账，不把四路信号做成综合分数。 |
| 用情绪因子补 FDA 第三维 | 进入[FDA 情绪第三维 V1 工作流](market_state_fda_sentiment_third_dimension_v1_workflow.md) → [白皮书](../ops/market_state_fda_sentiment_third_dimension_v1_whitepaper.md)；先有R11价格核心，再要求连续跟跌广度与下行同步同时成立。联合确认27例中23真/3弱/1假，旧确认外新增15例；只冻结研究公式等待真正未见期，不改默认策略。 |
| 把情绪第三维接入 FDA 高置信入场 | 进入[FDA 情绪增信入场整合 V2 工作流](market_state_fda_sentiment_entry_integration_v2_workflow.md) → [白皮书](../ops/market_state_fda_sentiment_entry_integration_v2_whitepaper.md)；旧确认OR新联合确认使高置信子路由32次扩至47次。未确认事件退回母路由，不能全局硬否决；R8盈利出场已冻结，但入场后不及预期快速处置仍未过门。 |
| 用统一尺子评价择时策略 | [项目级择时策略统一评价工作流](market_state_timing_evaluation_platform_workflow.md) → [白皮书](../ops/market_state_timing_evaluation_platform_whitepaper.md)；**唯一 current 评价入口。** V4 从原始事件重算行情供给、抓取、漏抓和假认领，再用同执行、签名成本的 M/F/B/R 精确区分市场供给、工具架构、族内路由和当前参数失配。 |
| 验证暴跌账本能否被因果切成形态纯桶 | [暴跌形态因果路由擂台 R1 工作流](market_state_downside_morphology_router_tournament_r1_workflow.md) → [白皮书](../ops/market_state_downside_morphology_router_tournament_r1_whitepaper.md)；五路分类只按 K 线全路径和几何描述量过门，当前全部拒绝整段路由权，仅保留生命周期阶段线索。 |
| 用交易后果分出 FDA 暴跌低假信号入场 | [R11 工作流](market_state_fda_high_purity_entry_router_r11_workflow.md) → [白皮书](../ops/market_state_fda_high_purity_entry_router_r11_whitepaper.md)；在冻结 R8 入场时只用残差能量扩张、最近12根方向和同棒全A传播分桶。价核 61 次的真/弱/假为 41/16/4；高置信确认层 32 次回溯零假但未过样本门，易假信号桶不得硬否决。 |
| 用 DataHub V5 重放 FDA × 火电残差增信 | [R13 工作流](market_state_fda_firepower_confirmation_r13_v5_rebase_workflow.md) → [白皮书](../ops/market_state_fda_firepower_confirmation_r13_v5_rebase_whitepaper.md)；V3/V5 事件身份 Jaccard 全部为 1.0，price-core 6/6 仍为真但支持度不足。AMS 扩波山脊保留，下跌方向增量被否决；只有研究用二级标签权。 |
| 检验多层行业指数能否补 FDA/R8 观测缺口 | [R14 工作流](market_state_fda_multilevel_industry_lead_r14_workflow.md) → [白皮书](../ops/market_state_fda_multilevel_industry_lead_r14_whitepaper.md)；行业五日下跌扩散度能稳定刻画入场后机会深度，但不能删掉仍盈利的低扩散入场；日度行业信息无法稳定负责15分钟R8出场，下一基础设施缺口是同频行业扩散与修复面板。 |
| 复现 FDA 同频行业修复测量及全域反例 | [R15/R16 工作流](market_state_fda_intraday_industry_repair_r15_r16_workflow.md) → [白皮书](../ops/market_state_fda_intraday_industry_repair_r15_r16_whitepaper.md)；R15 的 30 分钟行业修复广度是有效测量，R16 证明它不能无条件覆盖 R8。 |
| 复现 FDA 行业—价格路径桥接 | [R17 工作流](market_state_fda_industry_path_bridge_r17_workflow.md) → [白皮书](../ops/market_state_fda_industry_path_bridge_r17_whitepaper.md)；历史研究可复现，但 2021—2026 聚合黑箱已裁决 `failed`并封存。只允许校验封存包，不得重跑、拆明细或用结果调参。 |
| 用六轴属性验证工具切换 | [六轴属性与工具切换闭环工作流](market_state_timing_six_axis_tool_feedback_loop_workflow.md) → [白皮书](../ops/market_state_timing_six_axis_tool_feedback_loop_whitepaper.md)；用开发期六轴生成工具胜负假设，再用后续工具擂台和 M/F/R 收益守恒账本决生死。 |
| 复现旧W250-LAG1专项诊断 | 进入[趋势连续性市场状态工作流](market_state_trend_continuity_regime_workflow.md)；该线现只是六轴中方向记忆的一个分量，具体策略仍须机会账本联立诊断。 |
| 验证群体相关性对暴跌反弹命中的增量 | 进入[暴跌反弹群体相关性增量验证工作流](market_state_fda_rebound_group_corr_increment_workflow.md)；只检验全市场20/120日离散度期限结构，当前开发OOF否决且未打开2021—2026黑箱。 |
| 进入第3层策略身份架构 | [三类身份工作流](timing_layer3_strategy_architecture_workflow.md) → [白皮书](../ops/timing_layer3_strategy_architecture_whitepaper.md) → [当前@2.2](../ops/timing_layer3_strategy_architecture@2.2.json) → [权威身份注册表](../ops/timing_strategy_identity_registry@2.2.json) → [Layer2/3边界修复计划](timing_layer2_layer3_boundary_repair_plan.md)；具体策略的属性条件效果统一进Layer 3。 |
| 组装四层并在Layer 4后调参 | [端口与调参顺序计划](timing_four_layer_ports_and_l4_parameter_optimization_plan.md) → [白皮书](../ops/timing_four_layer_integration_whitepaper.md) → [已接受当前Port合同@1.1](../ops/timing_four_layer_port_contracts@1.1.json) → [候选Port@1.2](../ops/timing_four_layer_port_contracts@1.2.json) → [卖方/保证金候选工作流](timing_layer4_option_seller_margin_workflow.md)；Layer1/2对Layer3/4同等开放，Layer4不得私有重复测量器，且账户后才允许选参。 |
| 固定 Layer 4 最近一年盘口参考面 | [工作流](timing_layer4_recent_one_year_liquidity_impact_workflow.md) → [权威合同](../ops/timing_layer4_recent_one_year_liquidity_impact_policy@1.0.json) → [白皮书](../ops/timing_layer4_recent_one_year_liquidity_impact_whitepaper.md)；股票、基金、转债、期货、期权的容量/冲击统一使用最近一年 snapshot，历史价格保留真实 PIT 路径。 |
| 构造 Layer 4 统一期权推荐候选 | [统一推荐工作流](timing_layer4_unified_option_recommendation_workflow.md) → [历史保证金绑定](../ops/cffex_mo_seller_margin_datahub_binding_whitepaper.md) → [MO 固定流动性 snapshot](../ops/timing_layer4_mo_recent_one_year_liquidity_snapshot_whitepaper.md)；MO 输入数据 blocker 已闭合，当前等待完整账户经济评估。 |
| 运行 Layer 4 期权工具身份画像 | [画像工作流](timing_layer4_option_instrument_profile_workflow.md) → [计划](../ops/timing_layer4_option_instrument_profile_rebuild_plan.md) → [白皮书](../ops/timing_layer4_option_instrument_profile_whitepaper.md)；先侧写工具，再进 D1–D5。无成交改写权。 |
| 运行 Layer 4 分层期权路由 | [分层路由工作流](timing_layer4_hierarchical_option_router_workflow.md) → [白皮书](../ops/timing_layer4_hierarchical_option_router_whitepaper.md) → [机器合同@1.0](../ops/timing_layer4_hierarchical_option_router@1.0.json)；先买方/卖方，再认购/认沽，再虚实值，再近远月，最后才选档位。无生产权。 |
| 建立十五择时工具的组合优先级 | [择时策略组合优先级工作流](market_state_timing_priority_composition_workflow.md) → [白皮书](../ops/market_state_timing_priority_composition_whitepaper.md)；当前现役表 `tool_registry_v1_5`，论文核为第十四工具、LAT 通道为第十五工具；冻结上涨捕获/下跌防护两条“优先认领、剩余下传”空瀑布，不选择具体顺序。 |
| 搭建三级双向择时策略路由 | [三层双向择时策略路由工作流](market_state_timing_strategy_routing_workflow.md) → [第一层V3](market_state_timing_explosive_layer_v3_workflow.md) → [第一道暴跌反弹上下文门证据](../ops/evidence/market_state_fda_rebound_context_gate_20260804.md) → [第二道残差正交因子](market_state_fda_rebound_residual_orthogonal_workflow.md) → [白皮书](../ops/market_state_timing_strategy_routing_whitepaper.md)；当前全市场15分钟强涨宽度通过三阶段研究门，但未写入V3/V62生产公式，生产权仍为false。 |
| 复现三桶加动态 IIR 组合样板 | [V1 工作流](market_state_timing_three_bucket_iir_reference_v1_workflow.md) → [白皮书](../ops/market_state_timing_three_bucket_iir_reference_v1_whitepaper.md) → [冻结回执](../ops/evidence/market_state_timing_three_bucket_iir_reference_v1_20260812.md)；严格余集、单一真实T+1与同账户对照均已固化，供后续策略拆装参考，不替换V4路由且无生产权。 |
| 读取多尺度市场场谱 | [场谱工作流](market_state_timing_multiscale_market_field_workflow.md) → [白皮书](../ops/market_state_timing_multiscale_market_field_whitepaper.md)；分别查询清洁频带绝对能量、原始行情同尺度趋势和截止以下累积高通波动，禁止把测量状态直接升级为参数所有权。 |
| 用场谱与三桶 IIR 样板做第一次双向迭代 | [V2 工作流](market_state_timing_three_bucket_iir_reference_v2_workflow.md) → [白皮书](../ops/market_state_timing_three_bucket_iir_reference_v2_whitepaper.md) → [冻结证据](../ops/evidence/market_state_timing_three_bucket_iir_reference_v2_20260812.md)；场谱补充P36所有权，样板反向固化完整连续路径重定价门；跨聚合黑箱收益/夏普为正但回撤门失败，无生产权。 |
| 用两年块生成素材并整案淘汰重建 | [权威工作流](market_state_timing_block_material_rebuild_workflow.md) → [白皮书](../ops/market_state_timing_block_material_rebuild_whitepaper.md)；切块只生成问题素材和验收案例，冻结整案失败后整案作废，禁止父策略逐块补条件。[旧 V4](market_state_timing_three_specialist_progressive_v4_workflow.md)仅保留负例与账户证据。 |
| 复现年度/半年错位整案重建 V6 | [V6 工作流](market_state_timing_three_specialist_rolling_rebuild_v6_workflow.md) → [白皮书](../ops/market_state_timing_three_specialist_rolling_rebuild_v6_whitepaper.md)；23个边界视图每片6条素材，每轮完整重评8套结构，重叠不算独立OOS。V6构建对2021—2026零读取；冻结后的候选专属重复聚合复核显示V6与V2完全相同且低于V5，V6后继资格被拒绝，黑箱不得再用于选模。 |
| 重放前三专用桶整案淘汰重建 | [V5 工作流](market_state_timing_three_specialist_whole_rebuild_v5_workflow.md) → [白皮书](../ops/market_state_timing_three_specialist_whole_rebuild_v5_whitepaper.md)；旧全三项 V4 被 2019—20 否决后整体作废，24 条素材重建为“V4暴跌反弹 + V4论文核上涨 + V2 OLS”，六个两年块相对 V2 全正；因无新鲜留出块，仅为待验证研究候选。 |
| 复核高斜率上涨桶的 S2/S3 条件参数 | [R1 工作流](market_state_three_specialist_paper_up_nested_scale_r1_workflow.md) → [白皮书](../ops/market_state_three_specialist_paper_up_nested_scale_r1_whitepaper.md)；D2 能量传播决定新生命周期使用 S3 或 S2，生命周期内冻结。结果仅有已消费历史研究权。 |
| 挑战高斜率下跌桶是否应替换 OLS | [R1 工作流](market_state_three_specialist_down_tool_battle_r1_workflow.md) → [白皮书](../ops/market_state_three_specialist_down_tool_battle_r1_whitepaper.md)；FDA 在传播型下跌有增量，但固定替换显著增加回撤与换手，当前保留 OLS，并把下一研究收敛到传播/反向修复的条件路由。 |
| 挑战 OLS/FDA 因果条件路由 | [R1 工作流](market_state_ols_fda_causal_router_r1_workflow.md) → [白皮书](../ops/market_state_ols_fda_causal_router_r1_whitepaper.md)；先证明“中慢尺度方向一致向下”与“快频段能量衰减”的入场前因果测量，再测完整生命周期路由。接管轴 +0.536（8/12 正年份）但保留轴 -1.299，语义门双轴未同时成立，路由被拒绝，OLS 仍为唯一幸存者。 |
| 挑战 OLS/FDA 慢尺度组织化路由 | [R2 工作流](market_state_ols_fda_slow_org_router_r2_workflow.md) → [白皮书](../ops/market_state_ols_fda_slow_org_router_r2_whitepaper.md)；从 R1 残差找到方差比跨尺度结构（VR_d128>VR_d4，安慰剂 100 分位）。语义双轴通过（接管 11/11 正年 +1.893、保留 +0.058），完整账户 +1.326、夏普 2.308 高于 OLS，但回撤恶化 7.34pp 与换手 +24.1% 未过稳定门，OLS 仍为唯一幸存者。 |
| 挑战 OLS/FDA 出场感知路由 | [R4 工作流](market_state_ols_fda_exit_router_r4_workflow.md) → [白皮书](../ops/market_state_ols_fda_exit_router_r4_whitepaper.md)；R2 遗留的回撤与换手病由 middle_slowdown 出场 + 收紧交接条件（slow_org AND 传播）同时治愈：+0.266、夏普 2.159 高于 OLS 2.147、回撤变化 0、换手 +3.8%、语义双轴通过。本系列第一个通过本分支全部预注册门的非 OLS 回溯候选；但 2018—2020 合计 -0.107，尚未证明跨时期稳定，只能等待未来新增数据或未消费独立载体挑战。 |
| 验证 OLS 倾斜通道去趋势残差出场 | [R1 工作流](market_state_ols_residual_break_exit_r1_workflow.md) → [白皮书](../ops/market_state_ols_residual_break_exit_r1_whitepaper.md)；先拉平下跌通道再算残差宽度的测量成立，但W24越轨/CUSUM单独早退在2015/2020误伤多段暴跌和隔夜续跌；所有者总增量 -0.187、回撤恶化3.46pp，故只保留几何测量权，不授予独立出场或生产权。 |
| 收口暴跌反弹旧过滤与 paper-up 路由 | [R1 工作流](market_state_three_specialist_closeout_r1_workflow.md) → [白皮书](../ops/market_state_three_specialist_closeout_r1_whitepaper.md)；旧暴跌反弹第二门对 V4 冗余，第一门未过逐年稳定性门，保留 V4；`paper_s3_require_d2_energy` 冻结为等待新鲜期的研究候选。 |
| 第一桶暴跌反弹残差继任研究 | [R1 工作流](market_state_crash_rebound_residual_successor_r1_workflow.md) → [白皮书](../ops/market_state_crash_rebound_residual_successor_r1_whitepaper.md) → [主会话验收回报](market_state_crash_rebound_residual_successor_r1_main_session_report.md)；工具中立机会账本量准 V4 召回（大 39.0%/中 27.3%/小 9.7%）与 78/127 假启动，36 个漏掉大反弹中 30 个为上游供给缺席；宽度持续性明确过安慰剂门但其否决表达被 2010 整案重建证伪，d2 能量只是缺少邻尺度平台的压线点，十二年度 36 次候选尝试无一通过分散性门，裁决 `no_incremental_successor_beyond_baseline`，保留 V4。 |
| 验证 OLS 暴跌桶出场参数迁移与因子入参 | [R5 工作流](market_state_ols_residual_confirmed_turn_exit_r5_workflow.md) → [白皮书](../ops/market_state_ols_residual_confirmed_turn_exit_r5_whitepaper.md)；静态参数迁移已确认，但W24确认转向的回看正信号在逐年盲测中失败，最终状态为无增量继任者。 |
| 归因高斜率上涨冻结候选的残差错路由 | [R1 工作流](market_state_three_specialist_paper_up_residual_successor_r1_workflow.md) → [白皮书](../ops/market_state_three_specialist_paper_up_residual_successor_r1_whitepaper.md)；24 个差异区块全部归因为 S2 计时误差；V1 机制候选无一过帕累托，V2 阶梯研究证明 S1 臂条件不稳定、S4 臂全面落后、三路路由改善单事件支撑，科学状态 `no_incremental_successor_beyond_incumbent`，保留冻结候选。 |
| 验收三项外部 AI 专用桶任务 | [主会话收口报告](market_state_three_external_ai_tasks_main_session_closeout_20260813.md)；第一、第二桶均无稳定增量后继，第三桶仅形成待未来新增数据挑战的 OLS/FDA 回溯候选；同步修正 d2 压线点、贡献集中度和全局未见期口径。 |
| 评价择时策略研发成熟度 | 从[统一评价工作流](market_state_timing_evaluation_platform_workflow.md)进入；单策略可直接提交事件机会/抓取/责任仓账本，尚未形成完整出场时再用其[三层研发评价组件](market_state_timing_strategy_stage_evaluation_workflow.md)，依次评价独立机会、命中入场和完整交易。 |
| 用新基础设施重审滤波旧结论 | [v1 局部规则重审](market_state_causal_filter_new_workflow_revalidation_v1.md) → [v2 完整策略修复与重跑](market_state_causal_filter_complete_policy_revalidation_v2.md) → [v2 白皮书](../ops/market_state_causal_filter_complete_policy_revalidation_v2_whitepaper.md)；同时检验绝对亏损、跑输买入持有、跑输冻结静态，并拒绝将未安排触发机会的局部消融写成完整策略。 |
| IIR 单工具波动率参数路由 | [工作流 v1](market_state_causal_filter_iir_volatility_parameter_router_v1.md) → [白皮书](../ops/market_state_causal_filter_iir_volatility_parameter_router_v1_whitepaper.md)；只在同一个 Laplace IIR 带通工具内部，以25日/150日已实现波动率比的0.90/1.00滞回状态切换 P40/P32，禁止买入持有、现金门或其他工具接管。 |
| 验证 IIR 宽周期级别切换 | [宽周期验证 v2](market_state_causal_filter_iir_wide_period_router_v2.md) → [白皮书](../ops/market_state_causal_filter_iir_wide_period_router_v2_whitepaper.md)；联立验证 P20/P80 等2—6倍周期距离、状态窗口缩放和阈值山脊，开发期信号在2018—2020反转，因此否决宽周期波动率直路由并保留V1。 |
| IIR 波动率连续参数律门禁 | [逐层工作流 v3](market_state_causal_filter_iir_volatility_continuous_parameter_law_v3.md) → [白皮书](../ops/market_state_causal_filter_iir_volatility_continuous_parameter_law_v3_whitepaper.md)；先重建P28稳健静态中线，再挑战波动率参数所有权；完整两档路径虽盈利，但高波动P28优势集中于2015—2016，G3失败，故三/四档、连续公式与2018—2020复核均未运行。 |
| IIR 周期所有权残差归因 | [V11—V15 工作流](market_state_causal_filter_iir_period_ownership_residual_attribution_v11_v13_workflow.md) → [白皮书](../ops/market_state_causal_filter_iir_period_ownership_residual_attribution_v11_v13_whitepaper.md)；从闭合 P16/P40 分歧账本定位相位缺口，再用2018—2020新鲜样本否决“恰好3/4同向”的生命周期规则；当前只剩局部机制线索，不授权第三轴或动态参数。 |
| IIR 周期距离与缺失尺度 | [V16 工作流](market_state_causal_filter_iir_pair_distance_attribution_v16_workflow.md) → [白皮书](../ops/market_state_causal_filter_iir_pair_distance_attribution_v16_whitepaper.md)；用同一V7公式横向比较P16/P28/P40/P60/P80的10组周期对，并通过静态周期谱、分歧事件、中间尺度和方向上下文图形归因定位外层基准尺度缺口；不授权动态参数。 |
| IIR 第一层外层默认周期归属 | [V17 工作流](market_state_causal_filter_iir_outer_baseline_owner_v17_workflow.md) → [白皮书](../ops/market_state_causal_filter_iir_outer_baseline_owner_v17_whitepaper.md)；只开发绝对默认周期层，频谱重心和一致传递能量均未通过2009—2017决生死门，因此不打开正式重复审计、不启动内层挑战并保留静态P28。 |
| IIR 机会尺度—执行尺度交接 | [V19 工作流](market_state_causal_filter_iir_opportunity_execution_handoff_v19_workflow.md) → [白皮书](../ops/market_state_causal_filter_iir_opportunity_execution_handoff_v19_whitepaper.md)；P60/P80只定位大级别机会背景，冻结V7 P16/P28决定是否加快执行，外内同时成立才用P16，否则闭合回P28。原型通过开发与已消耗重复审计，但不是fresh OOS且生产权为false。 |
| IIR P13失效事件与P36慢接管双门 | [V2 工作流](market_state_causal_filter_iir_p13_failure_slow_handoff_v2_workflow.md) → [白皮书](../ops/market_state_causal_filter_iir_p13_failure_slow_handoff_v2_whitepaper.md)；开发期双门、曲面、错位与账本均通过，但2018—2020两分支同时转负，而静态P36胜过P13，定位为“慢周期所有权上游状态缺失”；保留研究账本，所有正式权限为false。 |
| IIR P13/P36阶段级慢周期所有权 | [V3 工作流](market_state_causal_filter_iir_p13_slow_ownership_regime_v3_workflow.md) → [白皮书](../ops/market_state_causal_filter_iir_p13_slow_ownership_regime_v3_whitepaper.md)；以“额外频带能量高、额外独立周期少”的二维条件做月度阶段路由，开发期四折/成本/延迟通过，冻结后2018—2020已消费聚合复核为正，2021首次新鲜验证也通过；具有单年fresh OOS支持，但生产权仍为false。 |
| IIR 双单因子时间曲面 | [V25 工作流](market_state_causal_filter_iir_single_factor_temporal_surfaces_v25_workflow.md) → [白皮书](../ops/market_state_causal_filter_iir_single_factor_temporal_surfaces_v25_whitepaper.md)；分开验证波动率与IIR分量BDCI的高/低状态记忆。两族均有可预测规律，但无可跟随规律，不允许跳到周期收益所有权或动态参数。 |
| IIR 单因子条件收益所有权 | [V26 工作流](market_state_causal_filter_iir_conditional_return_ownership_v26_workflow.md) → [白皮书](../ops/market_state_causal_filter_iir_conditional_return_ownership_v26_whitepaper.md)；把V25六条规律逐条映射到真实T+1含成本P14相对收益。三组关系有跨折正条件增量，但0/54候选取得三折原始所有权，故停止在开发门、未打开18—20且不授权动态参数。 |
| IIR短中长尺度档可利用性 | [决生死V1工作流](market_state_causal_filter_iir_scale_family_state_viability_v1_workflow.md) → [白皮书](../ops/market_state_causal_filter_iir_scale_family_state_viability_v1_whitepaper.md)；三档事后机会供给成立，但20—240日七种历史记忆均不可跟随，两个冻结因果传感器也不可预判；因此只能事后分档，不授权动态参数。 |
| 迁移旧因子否决四小时下跌假命中 | [正交否决迁移工作流](market_state_downside_entry_orthogonal_veto_workflow.md) → [三段证据](../ops/evidence/market_state_downside_entry_orthogonal_veto_20260805.md)；106项6家族重算后，12根跳变集中度在09—20通过，但21—26黑箱同时伤到1个真命中，最终不迁移，父入场不变。 |
| 研究四小时入场后出场现象 | [路径与转折—中继图谱](market_state_four_hour_downside_exit_path_atlas_workflow.md) → [证据回执](../ops/evidence/market_state_four_hour_downside_exit_path_atlas_v01_20260805.md)；固定`240×425×90`入场后统计四类下探、中继幅度和终局转折速度，未选参、未回测出场。 |
| 研究四小时四态因果出场 | [四态出场工作流](market_state_four_hour_downside_four_state_exit_workflow.md) → [证据回执](../ops/evidence/market_state_four_hour_downside_four_state_exit_v01_20260805.md)；修复跨态串线并加入深中继硬门后，入场失败态仍缺快速止损工具，转折工具只剩审计严重退化的孤立点，完整架构不锁定。 |
| 筛选第二层温和趋势工具 | [温和趋势工具筛选V0](market_state_ordinary_trend_tool_battle_v0_workflow.md) → [证据回执](../ops/evidence/market_state_ordinary_trend_tool_battle_v0_20260804.md)；上涨选中15分钟频率选择布林并通过三段审计，下跌选中60分钟因果Haar但存在单位能力漂移；当前通道无条件抢桶会抹掉上涨增量，工具选择权仍为false。 |
| 验证暴跌反弹动态宽度参数 | [动态参数工作流](market_state_fda_rebound_dynamic_breadth_workflow.md) → [第一轮证据](../ops/evidence/market_state_fda_rebound_dynamic_breadth_20260804.md) → [匹配状态归因工作流](market_state_fda_rebound_matched_state_workflow.md) → [最终证据](../ops/evidence/market_state_fda_rebound_matched_state_20260804.md)；24棒下跌方差耗竭能解释2020年前一部分真假事件，但冻结规则未通过21–26汇总黑箱，最终仍否决动态化并保留固定宽度边界。 |
| 复现已被替代的高斜率双桶 V1 | [历史双桶工作流](market_state_context_free_explosive_two_bucket_workflow.md) → [V1冻结证据](../ops/evidence/market_state_context_free_explosive_two_bucket_v1_20260803.md)；W12/W24通用通道路由已撤销，只保留历史复现和暴跌反弹内生第一腿，不代表最新基础设施。 |
| 复核W12/W24下跌通道选择性入场 | [GPU Transformer工作流](market_state_w12_w24_transformer_entry_gate_workflow.md) → [三阶段黑箱证据](../ops/evidence/market_state_w12_w24_sparse_transformer_v3_drift_blackbox_aggregate.md) → [2021—2026授权打开归因](../ops/evidence/market_state_w12_w24_post2020_authorized_attribution_20260803.md)；2022、2023并非没有大跌，而是W12/W24只覆盖长下跌中的短脉冲；主缺口是父级下跌生命周期，Transformer误筛居次，不授予生产权。 |
| 验证FDA触发与真通道生命周期 | [FDA触发真通道原型工作流](market_state_fda_explosive_channel_prototype_workflow.md) → [白皮书](../ops/market_state_fda_explosive_channel_prototype_whitepaper.md) → [三阶段证据](../ops/evidence/market_state_fda_explosive_channel_prototype_v0_20260803.md)；固定8候选训练一次、验证两次，区分机会减少和方向能力漂移。 |
| 验证多尺度通道的最高层数 | [FDA多尺度权威通道V1工作流](market_state_fda_multiscale_channel_v1_workflow.md) → [白皮书](../ops/market_state_fda_multiscale_channel_v1_whitepaper.md) → [三阶段证据](../ops/evidence/market_state_fda_multiscale_channel_v1_20260803.md)；不预设四层，直接Battle两/三/四层和三种退出，拆解最大下跌边际价值。 |
| 验证纯OLS高斜率暴涨暴跌生命周期 | [OLS高斜率通道V1工作流](market_state_ols_explosive_channel_v1_workflow.md) → [白皮书](../ops/market_state_ols_explosive_channel_v1_whitepaper.md) → [证据](../ops/evidence/market_state_ols_explosive_channel_v1_20260804.md)；W12/W24同时负责命中、入场与退出，P48/P96不参与第一层交易；冻结候选三段均为正，但2021—2026仍有单位能力衰减，只授予研究权。 |
| Battle OLS与论文核S2/S4的高斜率分桶权 | [V1工作流](market_state_ols_paper_explosive_bucket_battle_v1_workflow.md) → [白皮书](../ops/market_state_ols_paper_explosive_bucket_battle_v1_whitepaper.md) → `artifacts/market_state/ols_paper_explosive_bucket_battle_v1/`；15分钟真实T+1含成本下，上涨由S2 q925独立入场/零轴退出，下跌由OLS W12/W24独立入场/原生退出；交叉接管全部否决，并联增强只保留为无新鲜验证权的下一版假设。 |
| 评价单4小时下跌专家的命中入场 | [四尺度入场工作流](market_state_multiscale_downside_entry_workflow.md) → [尺度原生命中评价](market_state_multiscale_downside_outcome_workflow.md) → [斜率稳定化 Walk-Forward](market_state_multiscale_downside_walk_forward_workflow.md) → [8h/16h必要性消融](market_state_multiscale_downside_large_scale_necessity_workflow.md) → [完整波段账本与入口重审](market_state_four_hour_downside_entry_rechallenge_workflow.md)；当前研究入口为240分钟×425bps/日×90分钟，旧出场证据已失效，须重新研究。 |
| 挑战OLS长入短出包络通道 | [V2研究工作流](market_state_ols_asymmetric_channel_v2_workflow.md) → [否决证据](../ops/evidence/market_state_ols_asymmetric_channel_v2_20260804.md)；较长入场窗在开发期不稳定，短OLS残差极值包络虽减少退出回吐，但冻结2018—2020下跌侧转负；不替换V1。 |
| 压缩OLS旧跌势末端入场 | [V2工作流的入场补充](market_state_ols_asymmetric_channel_v2_workflow.md#入场新鲜度补充验证) → [新鲜度门证据](../ops/evidence/market_state_ols_entry_freshness_gate_20260804.md)；W24只作慢背景，W12斜率不弱于W24时才允许W12触发。两段都提高夏普并压低占用，但未修复下跌单笔能力衰减，只作研究压缩候选。 |
| 复算第一责任位 | [无上下文暴涨暴跌通道 V0](market_state_context_free_explosive_channel_workflow.md) → [白皮书](../ops/market_state_context_free_explosive_channel_whitepaper.md)；下跌沿用V62内核，上涨用严格价格镜像，双向独立计价和图形归因。 |
| 复算第二责任位 | [有上下文暴涨暴跌通道 V0](market_state_context_conditioned_explosive_channel_workflow.md) → [白皮书](../ops/market_state_context_conditioned_explosive_channel_whitepaper.md)；先按价格方向还原选背景，再消融正向/反向/裸局部通道。 |
| 区分尖顶尖底与混淆项 | [尖顶尖底四类形态识别工作流](market_state_sharp_turn_morphology_classifier_workflow.md) → [白皮书](../ops/market_state_sharp_turn_morphology_classifier_whitepaper.md)；持续通道、真反转、假突破、单棒跳变互斥识别，后两类只排除不交易。 |
| 复算尖顶/尖底反转策略擂台 | [反转固定桶策略擂台工作流](market_state_sharp_reversal_strategy_battle_workflow.md) → [白皮书](../ops/market_state_sharp_reversal_strategy_battle_whitepaper.md)；固定两个反转桶，统一14工具、成本、命中和入出场图形归因；向上研究候选通过重复审计，向下主人仍未冻结。 |
| 使用S20共享父级分桶 | [第14工具S20共享父级工作流](market_state_paper_s20_shared_parent_workflow.md) → [白皮书](../ops/market_state_paper_s20_shared_parent_whitepaper.md)；同一S20既作第二责任位背景，又作普通up/down/flat父桶，flat再下钻S5/IIR。 |
| 复算S20普通上涨桶工具擂台 | [上涨桶执行工具擂台工作流](market_state_s20_up_bucket_execution_battle_workflow.md) → [白皮书](../ops/market_state_s20_up_bucket_execution_battle_whitepaper.md)；固定父桶后比较12条单尺度、快组、双层V1与W72，审计期只否决不反选。 |
| 诊断S20上涨剩余桶工具与周期正交性 | [工具—周期正交性工作流](market_state_s20_up_bucket_tool_orthogonality_workflow.md) → [白皮书](../ops/market_state_s20_up_bucket_tool_orthogonality_whitepaper.md)；固定剩余桶重放14工具、12条论文核单尺度和W72，比较通道Phi、周期、成本与年度稳定性。 |
| 查询或登记择时经验公式 | [经验公式唯一入口](market_state_empirical_formula_workflow.md) → [白皮书](../ops/market_state_empirical_formula_whitepaper.md)；当前登记短周期跨尺度相对换手凹坑及其候选职责分配，同时保存147对普遍性反证。不是因子，也不是生产路由。 |
| 论文EWMA核多尺度长期时序 | [唯一渐进式入口](cloudridge_paper_kernel_multiscale_timeseries_workflow.md)。原论文是入口Layer 0最高理论源头；入口继续索引白皮书、12尺度数据、Schema、代码与测试。不设第二估计窗，不减局部均值乘积，不输出趋势/反转标签。 |
| 执行策略族基础设施归位 | [strategy_family_governance_workflow.md](strategy_family_governance_workflow.md) → [../ops/strategy_family_infrastructure_governance_whitepaper.md](../ops/strategy_family_infrastructure_governance_whitepaper.md)；先声明项目级依赖，再标注策略级保留机制、research-only 资产、历史证据和生产门禁。 |
| 先研究因子、再选择股票/基金载体 | [factor_first_research_workflow.md](factor_first_research_workflow.md) → [../ops/factor_first_infrastructure_whitepaper.md](../ops/factor_first_infrastructure_whitepaper.md) → [../adr/ADR-026-factor-first-research-and-carrier-separation.md](../adr/ADR-026-factor-first-research-and-carrier-separation.md)；统一研究股票、基金、宏观和跨资产信息，P1 不做策略评分或生产切换。 |
| 用统一多因子内核给股票/基金/混合载体评分 | [factor_first_multifactor_strategy_workflow.md](factor_first_multifactor_strategy_workflow.md) → [../ops/factor_first_multifactor_strategy_whitepaper.md](../ops/factor_first_multifactor_strategy_whitepaper.md) → [../ops/factor_first_infrastructure_compatibility_audit_report.md](../ops/factor_first_infrastructure_compatibility_audit_report.md)；P2 实现可审计评分/载体，`fl-hd06` 已修复后 P3 为 `passed`，仍不授予生产权。 |
| 审计并扩展为股票/基金/可转债广义轮动 | [broad_factor_rotation_strategy_workflow.md](broad_factor_rotation_strategy_workflow.md) → [broad_factor_rotation_layer1_recovery_workflow.md](broad_factor_rotation_layer1_recovery_workflow.md) → [broad_factor_rotation_layer1_factor_validity_workflow.md](broad_factor_rotation_layer1_factor_validity_workflow.md)；权威日线入口已拒绝退役 snapshot 并保留 `market:instrument_type:symbol`。第一层允许实体作实验样本但不选标的；310 候选/26 机制已恢复，经验数据门当前 blocked，裁决数和生产权均为 0。 |
| 运行载体中立 L0 年度扩展折 | [carrier_neutral_l0_yearly_expanding_workflow.md](carrier_neutral_l0_yearly_expanding_workflow.md) → [../ops/carrier_neutral_l0_yearly_expanding_readiness_result.md](../ops/carrier_neutral_l0_yearly_expanding_readiness_result.md) → [../ops/carrier_neutral_l0_datahub_history_gap_prompt.md](../ops/carrier_neutral_l0_datahub_history_gap_prompt.md)；2017 首折已冻结，当前因宏观/行业长历史与旧家族产物不足在拟合前阻断。 |
| 验收因子优先基础设施能否进入策略研究 | [factor_first_infrastructure_gate_workflow.md](factor_first_infrastructure_gate_workflow.md) → [../ops/factor_first_infrastructure_gate_report.md](../ops/factor_first_infrastructure_gate_report.md) → [../ops/factor_first_infrastructure_gate@1.0.json](../ops/factor_first_infrastructure_gate@1.0.json)；`fl-hd06` 修复后 G1 复验为 `go`，只开放后续策略研究；V9 未变、V10 未生成、生产权仍为 false。 |
| 发现因子在策略中的用途 | [factor_usage_discovery_workflow.md](factor_usage_discovery_workflow.md) → [../ops/factor_usage_discovery_infrastructure_whitepaper.md](../ops/factor_usage_discovery_infrastructure_whitepaper.md) → [../schemas/README.md](../schemas/README.md)；项目级记录 information evidence、0/1/N trial、campaign、frozen binding、integration claim 和逐策略 CAS cutover，不替策略规定动作空间；五策略交接从工作流“策略交接”入口进入。 |
| 用 AI / CLI 驱动完整研究 | [ai_research_cli_control_surface.md](ai_research_cli_control_surface.md) → [../api/headless_cli_reference.md](../api/headless_cli_reference.md) |
| 运行长耗时研究/训练/参数面脚本 | [research_resource_runner_workflow.md](research_resource_runner_workflow.md) → [../ops/research_resource_runner_execution_plan.md](../ops/research_resource_runner_execution_plan.md)；默认先用零侵入 runner，热点脚本再逐个深接入。 |
| 使用本机 AMD ROCm GPU | [factorlab_gpu_acceleration_workflow.md](factorlab_gpu_acceleration_workflow.md) → [../ops/factorlab_gpu_runtime_whitepaper.md](../ops/factorlab_gpu_runtime_whitepaper.md) → [工作区GPU契约](../../../../docs/workspace-gpu-runtime-contract.md) → [REAKA Stage6性能工作流](reaka_stage6_performance_governance_workflow.md) → [REAKA Stage6性能治理](../ops/reaka_stage6_performance_governance_whitepaper.md) → `scripts/check_factor_lab_accelerator_runtime.py`；先跑 `scripts/run_factor_lab_rocm_gpu.sh --check`，再按当前 workload fingerprint 比较 CPU/ROCm 端到端数值与速度。PyTorch 用默认模式，CuPy 用 `--cupy`，两者共用宿主 ROCm 与独占租约。 |
| 审计未来数据、伪 OOS 和过拟合 | [temporal_integrity_governance_workflow.md](temporal_integrity_governance_workflow.md) → [model_temporal_stability_audit_workflow.md](model_temporal_stability_audit_workflow.md) → [../ops/temporal_integrity_governance_whitepaper.md](../ops/temporal_integrity_governance_whitepaper.md)；LOYO/full-sample 只能诊断，同一拟合模型上的参数面不足以晋级，生产仍必须是冻结后 validation + 一次性 lockbox。 |
| 执行 L7 因子中台硬门 | [execution_surface_enforcement_workflow.md](execution_surface_enforcement_workflow.md) → [../ops/execution_surface_enforcement_whitepaper.md](../ops/execution_surface_enforcement_whitepaper.md)；策略、脚本、CLI 或自动化代理消费因子中台前必须提交 Feature Library、CandidateReviewPackage、CandidateAsset、挖因子 readiness、技术选型或 production gate 证据。 |
| 登记或复核脚本身份 | [script_identity_governance_workflow.md](script_identity_governance_workflow.md) → [../ops/script_identity_governance_whitepaper.md](../ops/script_identity_governance_whitepaper.md) → [../ops/script_identity_ledger.json](../ops/script_identity_ledger.json)；先登记身份、权威、引用和安全运行状态，再决定后续迁移、归档或删除。 |
| 治理归档、去重、迁移或删除 | [archive_dedup_migration_workflow.md](archive_dedup_migration_workflow.md) → [../ops/archive_dedup_deletion_governance_whitepaper.md](../ops/archive_dedup_deletion_governance_whitepaper.md) → [../ops/archive_migration_ledger.json](../ops/archive_migration_ledger.json)；当前脚本层迁移和删除候选已闭合，物理删除只保留 proof 完整的 `deleted_after_proof` tombstone。 |
| 运行当前代码静态质量门 | [static_quality_gate_workflow.md](static_quality_gate_workflow.md) → [../ops/static_quality_scope_whitepaper.md](../ops/static_quality_scope_whitepaper.md)；Ruff 覆盖 current 代码和测试，Basedpyright 覆盖 current 运行面，归档脚本不冒充生产代码。 |
| 执行 Baylum 每日数据更新 | [baylum_daily_data_update_workflow.md](baylum_daily_data_update_workflow.md) → [../ops/baylum_daily_data_update_whitepaper.md](../ops/baylum_daily_data_update_whitepaper.md)；默认更新 DataHub→FactorLab→Cloud Relay→ECS 数据包，不做策略优化；策略外部优化期间用 `--factorlab-pull-only` 只拉齐 DataHub→FactorLab。 |
| 拉取 DataHub 期货主力连续日线 | [datahub_futures_main_continuous_daily_workflow.md](datahub_futures_main_continuous_daily_workflow.md)；只消费 DataHub 从 no-gap 1m 派生的 `*_MAIN` 大品种成交量主力连续日线，不在策略脚本里临时拼接。 |
| 查云脊指数底层属性与多周期均线数据 | [cloudridge_attribute_infrastructure.md](cloudridge_attribute_infrastructure.md) → [../ops/cloudridge_attribute_infrastructure_whitepaper.md](../ops/cloudridge_attribute_infrastructure_whitepaper.md)；论文EWMA核必须转入其[唯一渐进式入口](cloudridge_paper_kernel_multiscale_timeseries_workflow.md)；当前普通属性产物目录 `../../output/cloudridge-attributes/current/`。 |
| 生成 CloudRidge 频段父级参数因子 | [cloudridge_scale_parent_factor_workflow.md](cloudridge_scale_parent_factor_workflow.md) → [../ops/cloudridge_scale_parent_factor_whitepaper.md](../ops/cloudridge_scale_parent_factor_whitepaper.md)；当前 `55D-90D` 子频段按公式映射到 `650D-1100D` 核心父级，产物目录 `../../output/cloudridge-scale-parent-factor/current/`。 |
| 跑滤波择时闭环 | **先读 [滤波择时基础技术资产总白皮书](../ops/filter_timing_technical_assets_whitepaper.md)** → [time_series_characteristics_workflow.md](time_series_characteristics_workflow.md) → [filter_directional_information_workflow.md](filter_directional_information_workflow.md) / `frequency_workflow.py` → [filter_tool_selection_workflow.md](filter_tool_selection_workflow.md) → [filter_timing_strategy_workflow.md](filter_timing_strategy_workflow.md) → [filter_workflow_chain.md](filter_workflow_chain.md) → `factor-lab filtering multi-scale-frequency-plan` → [filter_opportunity_queue.md](filter_opportunity_queue.md)；短周期反向入场走 [filter_protected_reversal_workflow.md](filter_protected_reversal_workflow.md)。p13 五桶逐桶优化走 [filter_timing_strategy_2_0_bucket_optimization_workflow.md](filter_timing_strategy_2_0_bucket_optimization_workflow.md)。 |
| 复跑脱离 IIR 的独立做多策略 | [cloudridge_independent_long_experts_workflow.md](cloudridge_independent_long_experts_workflow.md) → [../ops/cloudridge_independent_long_experts_whitepaper.md](../ops/cloudridge_independent_long_experts_whitepaper.md)；分别验收全局通道、全局R3裸版和专属否决版，失败的否决必须fail-open。 |
| 图形归因1000D背景与200D开门 | [filter_1000d_context_200d_open_gate_graph_attribution_workflow.md](filter_1000d_context_200d_open_gate_graph_attribution_workflow.md) → [../ops/filter_1000d_context_200d_open_gate_graph_attribution_whitepaper.md](../ops/filter_1000d_context_200d_open_gate_graph_attribution_whitepaper.md)；必须先看价格事件图谱，再读命中/假命中/延迟表，收益不替代开门质量。 |
| 归因并联滤波专家的大跌与逐笔亏损 | [filter_parallel_authority_veto_workflow.md](filter_parallel_authority_veto_workflow.md) → [../ops/filter_parallel_authority_veto_whitepaper.md](../ops/filter_parallel_authority_veto_whitepaper.md)；同时区分“事后最保护专家”与“事前可执行权威”，当前仅 1/10 笔完整 OR 亏损事前有合格权威，候选门未通过。 |
| 只看滤波择时基础规律和最终结论 | **[滤波择时基础技术资产总白皮书](../ops/filter_timing_technical_assets_whitepaper.md)** → [filter_workflow_chain.md](filter_workflow_chain.md) → [../ops/filter_research_decision_whitepaper.md](../ops/filter_research_decision_whitepaper.md) |
| 构建云脊可交易小篮子 | [cloudridge_tracking_basket.md](cloudridge_tracking_basket.md) → [../ops/cloudridge_tracking_basket_whitepaper.md](../ops/cloudridge_tracking_basket_whitepaper.md)；先用几十只等权股票高相关、高波动追踪云脊，再承接云脊滤波择时信号。 |
| 复核筛选/治理/优化是否真的改善买卖点 | [filter_post_walk_forward_tuning.md](filter_post_walk_forward_tuning.md) → [../ops/filter_post_walk_forward_tuning_whitepaper.md](../ops/filter_post_walk_forward_tuning_whitepaper.md)；要求前后图形渲染和 AI 买卖点检查。 |
| 使用因子中台 | [factor_middle_platform_workflow.md](factor_middle_platform_workflow.md) → [../ops/factor_middle_platform_lifecycle_whitepaper.md](../ops/factor_middle_platform_lifecycle_whitepaper.md)；先区分 FeatureSpec、FactorSpec、Public/Macro/Internal/Mined factor，再进入 CandidateAsset 生命周期。 |
| 使用因子轮动消费套件 | [factor_mining_to_consumption_workflow.md](factor_mining_to_consumption_workflow.md) → [../ops/factor_consumption_infrastructure_whitepaper.md](../ops/factor_consumption_infrastructure_whitepaper.md)；P3 fallback 与五消费者仅适用于 A 股日线多因子轮动。 |
| 使用特征-因子生产工具 | [feature_factor_library_workflow.md](feature_factor_library_workflow.md) → [public_factor_library.md](public_factor_library.md) → [standard_factor_library.md](standard_factor_library.md) → [formulaic_alpha_dsl.md](formulaic_alpha_dsl.md) → [mining_template_search.md](mining_template_search.md) → [genetic_factor_mining_workflow.md](genetic_factor_mining_workflow.md) → [symbolic_factor_search.md](symbolic_factor_search.md)；新字段先进入 Feature Library，公开因子库再按策略瓶颈检索外部声明来源/模板，V3 可用 shared asset ref 把内部研究 FactorSpec 接入同一 P2 context/memory/handoff 层，其余工具再负责本地公式、挖掘和验证；遗传/符号搜索是项目级挖因子基础设施，不是策略组。 |
| 执行宏观—微观历史重放 | [macro_micro_historical_replay_workflow.md](macro_micro_historical_replay_workflow.md) → [../ops/macro_micro_historical_replay_whitepaper.md](../ops/macro_micro_historical_replay_whitepaper.md)；按固定版本和 PIT 时间轴解释宏观周期、利率、流动性、制度事件与 A 股市场属性，未解释点显式进入下一轮研究队列，禁止把 index-only 数据用于个股信号。 |
| 训练深度因子模型工具 | [deep_factor_models.md](deep_factor_models.md) → [../ops/deep_factor_model_whitepaper.md](../ops/deep_factor_model_whitepaper.md)；模型可服务策略生产，但不单独列为策略组。 |
| 开发 T+0 可日内交易资产策略组 | [t0_fund_strategy_workflow.md](t0_fund_strategy_workflow.md) → [../ops/t0_fund_strategy_workflow_whitepaper.md](../ops/t0_fund_strategy_workflow_whitepaper.md) → [t0_convertible_bond_strategy_workflow.md](t0_convertible_bond_strategy_workflow.md) → [../ops/t0_convertible_bond_strategy_workflow_whitepaper.md](../ops/t0_convertible_bond_strategy_workflow_whitepaper.md) |
| 跑 ETF/LOF 动态标签 Top-1 轮动研究 | [etf_lof_dynamic_label_rotation_workflow.md](etf_lof_dynamic_label_rotation_workflow.md) → [../ops/etf_lof_dynamic_label_rotation_whitepaper.md](../ops/etf_lof_dynamic_label_rotation_whitepaper.md) → [../ops/etf_lof_dynamic_label_rotation_execution_plan.md](../ops/etf_lof_dynamic_label_rotation_execution_plan.md) |
| 使用 Residual Risk-Off 风险防护 | [risk_off_strategy_versions.md](risk_off_strategy_versions.md) → [risk_off_residual_protection_strategy.md](risk_off_residual_protection_strategy.md) → [../ops/risk_off_strategy_versions_whitepaper.md](../ops/risk_off_strategy_versions_whitepaper.md)；当前唯一权威交接版是 v2.0 preview：`publish_risk_off_current_result_package.py --v2-preview` / `--risk-v2-preview`，Gate1 为 `55D-90D` family、`60D-85D` order 3、108 observation 过滤到 34 accepted hit，Gate2 为未生产闭环的风险解除/出场生命周期回放。v1.0 `75D-130D` / 38 命中 / `--butterworth-preview` 只保留为历史基线。 |
| 比较 Risk-Off 候选与 V48 baseline | [risk_off_scorecard_workflow.md](risk_off_scorecard_workflow.md) → [../ops/risk_off_scorecard_whitepaper.md](../ops/risk_off_scorecard_whitepaper.md)；任何 Risk-Off 新候选优化后都要输出 T0 覆盖/误报、T1 入出场及时性、T2 交易质量，并生成 baseline comparison。分层动态出场主线必须额外运行 `audit_risk_off_dynamic_statistical_exit_v1.py`，比较 `fallback_only` / `drawdown_primary` / `bar_count_primary`；bar-count 参数优化运行 `optimize_risk_off_dynamic_statistical_exit_bar_count_v1.py`。 |
| 推进 Risk-Off 树模型/随机森林优化轮次 | [risk_off_model_discovered_state_machine_workflow.md](risk_off_model_discovered_state_machine_workflow.md) → [../ops/risk_off_model_discovered_state_machine_whitepaper.md](../ops/risk_off_model_discovered_state_machine_whitepaper.md)；先让模型发现足够强的一档候选，若多轮上不去则进入瓶颈诊断，拆错误样本和失败类型，再把失败类型映射到特征缺口并执行有界补因子/重训/challenge 循环。 |
| 复跑 Risk-Off V49 嵌套因子挑战 | [risk_off_v49_nested_walk_forward_workflow.md](risk_off_v49_nested_walk_forward_workflow.md) → [../ops/risk_off_v49_nested_walk_forward_whitepaper.md](../ops/risk_off_v49_nested_walk_forward_whitepaper.md)；首次外层硬锚定为 2017-01-13，当前 campaign 可证明搜索下界为 764。G1 硬过滤和不压低 V48 的严重度路由都未通过历史外层门，所以保留 V48、不发布 V49。前瞻数据冻结见 [risk_off_v49_vintage_store_workflow.md](risk_off_v49_vintage_store_workflow.md)。 |
| 运行 Risk-Off V49 图结构因子用途挑战 | [risk_off_v49_graph_usage_challenge_workflow.md](risk_off_v49_graph_usage_challenge_workflow.md) → [risk_off_v49_graph_prospective_validation_workflow.md](risk_off_v49_graph_prospective_validation_workflow.md) → [../ops/risk_off_v49_graph_prospective_validation_whitepaper.md](../ops/risk_off_v49_graph_prospective_validation_whitepaper.md)；固定 `V48 + hard_body_break_box_5` 已在 2017–2026 历史年度 Walk-Forward 中判为相对 V48 有效的 V49 研究版本；冻结后独立 OOS 和生产权限仍未获得。 |
| 从完整 V49 挖掘 Risk-Off V50 | [risk_off_v50_factor_challenge_workflow.md](risk_off_v50_factor_challenge_workflow.md) → [../ops/risk_off_v50_factor_challenge_whitepaper.md](../ops/risk_off_v50_factor_challenge_whitepaper.md)；盘点 72 个图结构因子，V49 已用 1 个，其余 71 个形成 95 个用途配置；只用 2009–2016 选择 `hard_close_box_pos_5 <= 0.10`，固定后在 2017–2026 十个外层折相对完整 V49 通过，形成 V50 历史研究版本，production=false。 |
| 从完整 V50 挑战 Risk-Off V51 | [risk_off_v51_pit_factor_challenge_workflow.md](risk_off_v51_pit_factor_challenge_workflow.md) → [incremental_walk_forward_stability_workflow.md](incremental_walk_forward_stability_workflow.md) → [../ops/risk_off_v51_pit_factor_challenge_whitepaper.md](../ops/risk_off_v51_pit_factor_challenge_whitepaper.md)；PPI 路线 3正/7平/0负、10/10 非负且全部历史门通过，生成 V51 研究版本。Kitchin 路线仍因最差伤害被拒绝。 |
| 从 V51 优化 Gate3 退出右尾并挑战 V52 | [risk_off_v52_exit_tail_challenge_workflow.md](risk_off_v52_exit_tail_challenge_workflow.md) → [../ops/risk_off_v52_exit_tail_challenge_whitepaper.md](../ops/risk_off_v52_exit_tail_challenge_whitepaper.md)；1正/9平/0负、右尾 4→3、净增量 +0.050138，生成 V52 历史研究候选，生产权限关闭。 |
| 登记并接管 Risk-Off V53 试开发 | [risk_off_version_development_workflow.md](risk_off_version_development_workflow.md) → [risk_off_v53_false_hit_exit_delay_discovery_workflow.md](risk_off_v53_false_hit_exit_delay_discovery_workflow.md) → [../ops/risk_off_v53_false_hit_exit_delay_discovery_whitepaper.md](../ops/risk_off_v53_false_hit_exit_delay_discovery_whitepaper.md)；S0–S7 已完成，固定外层未通过，结果为 `no_selection_keep_v52`。后续版本使用“主 AI 先备齐交接包、用户单次决定、可选执行 AI、主 AI 最终验收”的双 AI 路线。 |
| 重开发 Risk-Off V53 第一门 | [risk_off_v53_gate1_redevelopment_workflow.md](risk_off_v53_gate1_redevelopment_workflow.md) → [../ops/risk_off_v53_gate1_redevelopment_whitepaper.md](../ops/risk_off_v53_gate1_redevelopment_whitepaper.md)；当前开发权威为 unified2009 v7：2009–2020 是一整块训练材料，不做内部滚动；训练 32/32、假 1/1、覆盖 32.73%，冻结后 2021 为 1/2，故真实裁决是 `rejected_2021_recall`。完整 V53、Gate2/Gate3 与生产权限均未建立，完整策略保留 V52。 |
| 重跑 V53 第一门纯训练参数曲面 | [risk_off_v53_gate1_cutoff2020_surface_workflow.md](risk_off_v53_gate1_cutoff2020_surface_workflow.md) → [../ops/risk_off_v53_gate1_cutoff2020_surface_whitepaper.md](../ops/risk_off_v53_gate1_cutoff2020_surface_whitepaper.md)；只用 2009–2020 的 32 个注册事件重新训练 72 个模型并展开 2,880 点，严格 32/32 面形成 525 点单一连通平台、122 个内部点和 7/7 维跨度；仅证明训练期参数稳健，未执行截止日后验证。 |
| 回放 V53 第一门训练曲面代表点 | [risk_off_v53_gate1_cutoff2020_surface_replay_workflow.md](risk_off_v53_gate1_cutoff2020_surface_replay_workflow.md) → [../ops/risk_off_v53_gate1_cutoff2020_surface_replay_whitepaper.md](../ops/risk_off_v53_gate1_cutoff2020_surface_replay_whitepaper.md)；先冻结 81 个去重代表点与 6 个多数票版本，再回放 2021–2026；六版本均为 11/12，训练厚曲面未外推成样本外稳定平台。 |
| 研究 V53 第一门曲面支持度 | [risk_off_v53_gate1_surface_support_workflow.md](risk_off_v53_gate1_surface_support_workflow.md) → [../ops/risk_off_v53_gate1_surface_support_whitepaper.md](../ops/risk_off_v53_gate1_surface_support_whitepaper.md)；840 点完整训练厚面在固定坐标逐年留一后变为 0 个联合可行点，定位为底层 RF 跨年校准/表征漂移；未读取外部年份。 |
| 开发 Risk-Off V54 第一门 | [risk_off_v54_gate1_development_workflow.md](risk_off_v54_gate1_development_workflow.md) → [../ops/risk_off_v54_gate1_development_whitepaper.md](../ops/risk_off_v54_gate1_development_whitepaper.md)；严格只用 2009—2020，独立验证三层因子并训练稀疏单调 GAM。Attempt001 的 216 点状态曲面无完整硬门可行点，已失败登记，不生成 V54 第一门。 |
| 复现并继续开发 Risk-Off V55 | [risk_off_v55_workflow.md](risk_off_v55_workflow.md) → [../ops/risk_off_v55_whitepaper.md](../ops/risk_off_v55_whitepaper.md)；V55 是无独立 Gate1 的三阶段持续时间通道具名研究版本，内部 V1/V2 只是机制尝试号。冻结期不得反向调参，生产和 Baylum 发布权关闭。 |
| 复现 V55 多尺度下降区间候选 | [risk_off_v55_multiscale_channel_candidate_workflow.md](risk_off_v55_multiscale_channel_candidate_workflow.md) → [../ops/risk_off_v55_multiscale_channel_candidate_whitepaper.md](../ops/risk_off_v55_multiscale_channel_candidate_whitepaper.md)；60m 背景 + 15m 持续下降通道 + 5m 完整子波。attempt019 固定先审计结构再看结果：实现型假命中必须为 0，结构成立后立即失败允许登记；当前训练 20/23，仍漏三处，`fresh_oos=false`，未替换现有 V55 或云端。 |
| 复现 V55 阶段二持续角力候选 | [risk_off_v55_stage2_tug_of_war_candidate_workflow.md](risk_off_v55_stage2_tug_of_war_candidate_workflow.md) → [../ops/risk_off_v55_stage2_tug_of_war_candidate_whitepaper.md](../ops/risk_off_v55_stage2_tug_of_war_candidate_whitepaper.md)；attempt004 只读 2009—2020，按阶段顺序治理训练素材，四次独立 9年选参/3年外折合计 18/18、严格假命中2段，仍为非生产看图候选。 |

---

## 快速开始与验收

绿波择时当前正式研究入口：[绿波择时策略5.0工作流](cloudridge_greenwave_v5_workflow.md)
→ [5.0技术白皮书](../ops/cloudridge_greenwave_v5_whitepaper.md)。5.0 只对云脊指数负责，
统一普通IIR、超级上涨、P800熊市三市场权威、逐棒专家和五张优化账；
不使用旧 ETF 跨载体晋级门。

V6 P300低通背景原型：[工作流](cloudridge_greenwave_v6_p300_lowpass_prototype_workflow.md)
→ [白皮书](../ops/cloudridge_greenwave_v6_p300_lowpass_prototype_whitepaper.md)。该原型工程闭环已通过，
但封存验证未打赢裸IIR或旧V5，不得冒充正式V6。

持续通道专项：[工作流](cloudridge_greenwave_v5_multiscale_super_bull_workflow.md)
→ [白皮书](../ops/cloudridge_greenwave_v5_multiscale_super_bull_whitepaper.md)。

| 文档 | 适用任务 |
|---|---|
| [quickstart.md](quickstart.md) | 安装后快速运行、最小研究路径和常用命令。 |
| [uat_checklist.md](uat_checklist.md) | 用户验收检查清单。 |
| [strategy_family_governance_workflow.md](strategy_family_governance_workflow.md) | 策略族基础设施归位、项目级依赖声明和策略专属门禁边界检查。 |

## CLI / AI 研究控制面

| 文档 | 适用任务 |
|---|---|
| [ai_research_cli_control_surface.md](ai_research_cli_control_surface.md) | 用 CLI/Codex 驱动 Idea → research decision；L7 自动循环只在 CLI/Codex，不在 UI。 |
| [research_resource_runner_workflow.md](research_resource_runner_workflow.md) | 动态资源感知研究脚本入口：实时 CPU/内存/I/O/active jobs admission、telemetry、历史画像，以及零侵入/深接入两条路径。 |
| [script_identity_governance_workflow.md](script_identity_governance_workflow.md) | 脚本身份治理：登记 project/strategy/historical/diagnostic/deprecated 状态、authority、引用、产物 lineage 和 safe-to-run 状态。 |
| [archive_dedup_migration_workflow.md](archive_dedup_migration_workflow.md) | 归档、去重、迁移与删除治理：登记 current/superseded/historical/deprecated/deleted/archive-only 状态和动作；当前 `move_later=0`、`delete_later_after_proof=0`，只保留已 proof 的删除 tombstone。 |
| [static_quality_gate_workflow.md](static_quality_gate_workflow.md) | 基于脚本身份账本运行 Ruff/Basedpyright，并复核 pytest 全量 collection；active 类型 baseline 是迁移棘轮，不是类型债务归零证明。 |
| [factor_middle_platform_workflow.md](factor_middle_platform_workflow.md) | 因子中台工作流：统一 FeatureSpec、FactorSpec、公开/宏观/内部/挖掘因子、CandidateReviewPackage、CandidateAsset 和模型工具治理。 |
| [execution_surface_enforcement_workflow.md](execution_surface_enforcement_workflow.md) | L7 执行面强制接入：策略执行面消费因子中台前，先过统一 hard gate；`production_authority=True` 只来自完整生产候选链。 |
| [strategy_family_governance_workflow.md](strategy_family_governance_workflow.md) | 策略族治理工作流：把 T0、多因子/Risk-Off/滤波择时的保留机制接到项目级中台，但不把策略阈值、门禁和版本语义上提。 |
| [baylum_daily_data_update_workflow.md](baylum_daily_data_update_workflow.md) | Baylum 每日数据更新：检查/可调度 DataHub 日常刷新、重建云脊指数；完整模式刷新 ResultPackage current 并上传 Cloud Relay current，截断模式只拉到 FactorLab 输出目录。 |
| [datahub_futures_main_continuous_daily_workflow.md](datahub_futures_main_continuous_daily_workflow.md) | DataHub 期货主力连续日线消费：从 DataHub `bars_cn_derivatives_1d_main_continuous` READY 版本拉取黑色、有色、能源化工等大品种 `*_MAIN` 日线。 |
| [l7_agent_automation.md](l7_agent_automation.md) | L7 Agent Automation 用户指南。 |
| [time_series_characteristics_workflow.md](time_series_characteristics_workflow.md) | 拿到指数/组合时间序列后，先做趋势/震荡/周期/随机/结构切换体检，再决定处理路线。 |
| [cloudridge_attribute_infrastructure.md](cloudridge_attribute_infrastructure.md) | 云脊指数底层属性基础设施：属性含义、日线属性时序、多周期均线和图形产物路径；只作为策略研究素材，不直接定义生产信号。 |
| [market_state_unified_kline_attribute_infrastructure.md](market_state_unified_kline_attribute_infrastructure.md) | V3为Cloudridge+六指数的14视图与年度属性atlas；新增1m、5m五相位、P10/P17和高频缺口排除门，按Layer 0—4渐进下钻。 |
| [market_state_all_frequency_timing_infrastructure_v2_1_workflow.md](market_state_all_frequency_timing_infrastructure_v2_1_workflow.md) | 全频段共同基础设施的唯一 current：3秒至日级共用统计、ASK-BID 回测与属性盈利关系评价。V1/V2 工作流只保留历史复现。 |
| [历史跨频缺口工作流](cross_frequency_return_sharpe_potential_infrastructure_workflow.md) | 已被[V2版本链](../ops/cross_frequency_opportunity_stability_version_registry@1.0.json)取代；只保留“为什么当时不可回答频段排名”的历史审计权。 |
| [market_state_lat_layer2_oracle_trade_quality_workflow.md](market_state_lat_layer2_oracle_trade_quality_workflow.md) | LAT 非因果单笔质量 oracle：主过滤族是未来路径效率，波动/振幅次优；不是 Layer 3 插件。 |
| [market_state_lat_hf_l2_triple_bucket_dual_objective_workflow.md](market_state_lat_hf_l2_triple_bucket_dual_objective_workflow.md) | LAT P8 无成本指数：L2 因果波动率×长期效率×中期反转分桶，每桶收益最大/单笔均收益两套参数；不是插件。 |
| [market_state_lat_hf_l2_matched_bucket_dual_objective_v2_workflow.md](market_state_lat_hf_l2_matched_bucket_dual_objective_v2_workflow.md) | V2：P8 同钟 1x/8x/80x 回看，纠正 V1 日线气候错配。 |
| [market_state_lat_hf_l2_matched_bucket_dual_objective_v3_workflow.md](market_state_lat_hf_l2_matched_bucket_dual_objective_v3_workflow.md) | V3：用户授权 2015—2023 重评 2 档 vs 3 档。 |
| [csi1000_lat_p8_l2_matched_bucket_prototype_external_ai_prompt.md](csi1000_lat_p8_l2_matched_bucket_prototype_external_ai_prompt.md) | P8 L2分桶半成品的外部AI接管提示词。 |
| [csi1000_lat_p8_l2_matched_bucket_layer4_adapter_workflow.md](csi1000_lat_p8_l2_matched_bucket_layer4_adapter_workflow.md) | 把两个完整候选接到 Layer 4 MO `StrategyForecastBundle@2.0`；不选合约、不开经济会话。 |
| [csi1000_lat_p8_layer4_mo_account_preflight_workflow.md](csi1000_lat_p8_layer4_mo_account_preflight_workflow.md) | P8 接 Layer 4 MO 账户的回测前预检；三个基础设施 gap 已闭合。 |
| [csi1000_lat_p8_layer4_mo_account_economic_evaluation_workflow.md](csi1000_lat_p8_layer4_mo_account_economic_evaluation_workflow.md) | P8 两个完整候选的身份对齐 MO 账户经济回放；当前执行 `@1.2` overlay 重建；`@1.1` 密封无经济候选；`@1.0` 无执行权。 |
| [csi1000_lat_p8_layer4_minute_overlay_gate_workflow.md](csi1000_lat_p8_layer4_minute_overlay_gate_workflow.md) | 分钟级 overlay 门 `@1.1`：方向、逐状态持仓成本、路径期望选择、到期英文映射；禁止静态实值政策。 |
| [csi1000_lat_p8_l2_matched_bucket_layer4_mo_account_external_ai_prompt.md](csi1000_lat_p8_l2_matched_bucket_layer4_mo_account_external_ai_prompt.md) | 转交 Layer 4：用本 P8 高频两候选做 MO 账户回测，禁止改用崩溃反弹 54 点。 |
| [timing_layer2_next_path_efficiency_forecast_workflow.md](timing_layer2_next_path_efficiency_forecast_workflow.md) | Layer 2 因果预估下一窗 Kaufman ER：简单回看均值是反转，组织度/双头比第一跑 `no_evidence`；不是 Layer 3 插件。 |
| [timing_layer2_adaptive_horizon_path_efficiency_workflow.md](timing_layer2_adaptive_horizon_path_efficiency_workflow.md) | 波动放大后用放大/缩小/波动映射回看探测 ER。跨尺度 RV 同向，第一跑 `no_evidence`。 |
| [timing_layer2_scale_shape_path_efficiency_workflow.md](timing_layer2_scale_shape_path_efficiency_workflow.md) | 把 RV 拆成共同尺度与形状残差。尺度跟路程，形状不能预估 CSI1000 下一窗 ER。 |
| [timing_layer2_implied_intraday_reversal_workflow.md](timing_layer2_implied_intraday_reversal_workflow.md) | Layer 2 隐含日内反转 K 线属性：V1.2 四个桶统计，不改 `@2.3` pointer。白皮书 [`../ops/timing_layer2_implied_intraday_reversal_whitepaper.md`](../ops/timing_layer2_implied_intraday_reversal_whitepaper.md)。合同 [`../ops/timing_layer2_implied_intraday_reversal@1.2.json`](../ops/timing_layer2_implied_intraday_reversal@1.2.json)。 |
| [timing_layer2_overnight_gap_ledger_workflow.md](timing_layer2_overnight_gap_ledger_workflow.md) | Layer 2 隔夜高低开账本：±30bp 普通开盘，高开/低开尾；消息只记第一天。白皮书 [`../ops/timing_layer2_overnight_gap_ledger_whitepaper.md`](../ops/timing_layer2_overnight_gap_ledger_whitepaper.md)。合同 [`../ops/timing_layer2_overnight_gap_ledger@1.2.json`](../ops/timing_layer2_overnight_gap_ledger@1.2.json)。 |
| [csi1000_lat_iarr_full_cost_frequency_curve_workflow.md](csi1000_lat_iarr_full_cost_frequency_curve_workflow.md) | LAT/IARR P16–P3840同轴频率曲线与MO全成本运输；拒绝普遍单调命题，但MO覆盖低于60%、无稳定峰和选频权。 |
| [csi1000_medium_frequency_asset_cost_corrected_workflow.md](csi1000_medium_frequency_asset_cost_corrected_workflow.md) | 当前V2：P510–P960纯IIR/LAT资产成本纠错。指数信号零成本；MO用真实成交价格再扣14元/边。P34在开发与重复信号层收益/夏普均领先；MO覆盖仍失败。V1只作事故证据。 |
| [timing_asset_cost_boundary_workflow.md](timing_asset_cost_boundary_workflow.md) | 当前 [`@2.0` 注册表](../ops/timing_asset_cost_boundary_registry@2.0.json)：股票1+6bp、股票ETF各1bp佣金、非可交易指数零成本、MO长期权Ask→Bid、短期权Bid→Ask与14+14元手续费的机器硬门；拒绝跨资产成本搬运。V1 只保留历史复现。 |
| [market_state_volatility_three_state_router_framework_workflow.md](market_state_volatility_three_state_router_framework_workflow.md) | 结果前三态波动率路由与P34高频分散入口：低态空仓/低仓/待登记震荡，中态LAT P34基线，高态六通道完整政策；P16-P32只冻结候选轴，主审P34+challenger 50/50回撤错位与同回撤预算收益。当前研究执行权为false。 |
| [market_state_volatility_regime_recognizer_battle_workflow.md](market_state_volatility_regime_recognizer_battle_workflow.md) | 历史复现：默认参数十家族赛。简单三分位第一。`current=false`，现役入口是 nested V2。 |
| [market_state_volatility_regime_recognizer_nested_v2_workflow.md](market_state_volatility_regime_recognizer_nested_v2_workflow.md) | 当前唯一识别器入口：10家族每家12参数、5个嵌套外层年、3个冻结重复年；简单滞回第一，简单分位第二，Bipower硬分桶第三。 |
| [market_state_attribute_pool_infrastructure.md](market_state_attribute_pool_infrastructure.md) | 核心K线、频谱、论文核、载体关系和衍生品执行五池统一管理入口；更新必须走[工作流](market_state_attribute_pool_update_workflow.md)。第5池高阶字段见[衍生品执行池工作流](market_state_derivatives_execution_pool_workflow.md)。 |
| [cloudridge_scale_parent_factor_workflow.md](cloudridge_scale_parent_factor_workflow.md) | CloudRidge 频段父级参数因子：用子频段几何中心公式推出核心/鲁棒父级，并生成振幅比、父级速度和父级压力等研究参数；只作为 internal FactorSpec 和 research artifact。 |
| [risk_off_strategy_versions.md](risk_off_strategy_versions.md) | Residual Risk-Off 版本工作流：运行版本注册表审计，确认 v1.0 是当前权威交接版；运行 v2 Gate1 审计，生成 `60D-85D` order 3 + 父级 pressure 参数化的研究候选 artifact。 |
| [risk_off_v62_post_optimization_evaluation_workflow.md](risk_off_v62_post_optimization_evaluation_workflow.md) | V62每轮优化后的双层跨期诊断：先用固定桶外路由、年均/单次/单K线指标筛查不一致，再用风险策略公共匹配内核和状态桶专用适配器区分机会组成变化与同类事件能力退化。 |
| [risk_off_v62_large_channel_parameter_audit.md](risk_off_v62_large_channel_parameter_audit.md) | V62最高优先级大通道桶的生命周期图形归因、公式参数/K线属性映射、连续确认与退出线稳定性挑战；当前结论是保留参数，不授权孤立峰。 |
| [risk_off_v62_paper_kernel_dynamic_profile.md](risk_off_v62_paper_kernel_dynamic_profile.md) | 论文EWMA多尺度状态选择V62完整W48/W72/W96 Profile的决生死验证；Oracle有空间，但主公式、错位检验和前向映射均失败，不开放动态P。 |
| [risk_off_v62_bare_w72_paper_signal_k_regime.md](risk_off_v62_bare_w72_paper_signal_k_regime.md) | 只用裸W72验证原生300/400/500日信号与K的正反向关系；两年Oracle不呈反向，6个反向组合全部败给固定K1。 |
| [risk_off_scorecard_workflow.md](risk_off_scorecard_workflow.md) | Risk-Off 版本记分卡与分层动态出场工作流：固定 T0/T1/T2 指标层级，跑候选和 baseline 的同口径差异表；出场优化额外跑 V2-V7 后验逐 bar 灰测和 bar-count focused 参数搜索，当前主线是 `bar_count_primary`。 |
| [risk_off_v49_nested_walk_forward_workflow.md](risk_off_v49_nested_walk_forward_workflow.md) | Risk-Off V49 宏观/基本面/板块/风格/量价因子嵌套 Walk-Forward；当前结论为 `fail_keep_v48`，不得把零改动写成 no-harm 优化成功。 |
| [risk_off_v49_vintage_store_workflow.md](risk_off_v49_vintage_store_workflow.md) | Risk-Off V49 行业/风格/基本面追加式 vintage store；冻结日为 2026-07-12，历史种子不得倒签，当前等待 post-freeze V48 segment。 |
| [risk_off_v49_graph_usage_challenge_workflow.md](risk_off_v49_graph_usage_challenge_workflow.md) | Risk-Off V48 + 日线图结构因子 exact-usage 试验；关闭前一 bar 可用性、SearchScope/multiplicity、CandidateAsset 和 CampaignReceipt，停在 binding 之前。 |
| [risk_off_v49_graph_prospective_validation_workflow.md](risk_off_v49_graph_prospective_validation_workflow.md) | 冻结图结构 severity 候选、追加 first-seen 因子账本并执行 prediction-before-outcome；当前无 active segment feed，正式状态为 waiting。 |
| [risk_off_v50_factor_challenge_workflow.md](risk_off_v50_factor_challenge_workflow.md) | 完整 V49 → V50 未纳入因子盘点、初始训练选择和固定年度外层 Walk-Forward；当前 V50 历史研究候选通过，生产权限仍为 false。 |
| [risk_off_v51_pit_factor_challenge_workflow.md](risk_off_v51_pit_factor_challenge_workflow.md) | 完整 V50 → V51 PIT 库存、阻断责任、FactorLab 公式冻结和残余新因子挑战；PPI 库存路线已生成 V51 历史研究版本，生产权仍关闭。 |
| [risk_off_v52_exit_tail_challenge_workflow.md](risk_off_v52_exit_tail_challenge_workflow.md) | V51 Gate3 图形归因、多因子批量挖掘、单机制优先选择与固定年度外层验证；失败启动修复生成 V52 历史研究候选。 |
| [risk_off_version_development_workflow.md](risk_off_version_development_workflow.md) | V53 起的版本开发登记、失败留痕、S4 用户单次交接决策、双 AI 分工与 S0–S7 阶段证据口径。 |
| [risk_off_v53_false_hit_exit_delay_discovery_workflow.md](risk_off_v53_false_hit_exit_delay_discovery_workflow.md) | V52 基座上压纯假命中与退出右尾的发现窗试开发；候选已冻结并交由 [risk_off_v53_fixed_walk_forward_workflow.md](risk_off_v53_fixed_walk_forward_workflow.md) 执行固定外层，结果为 `no_selection_keep_v52`。 |
| [risk_off_v53_gate1_redevelopment_workflow.md](risk_off_v53_gate1_redevelopment_workflow.md) | V53 第一门当前权威仍为 `risk_off_v53_gate1_full_clock_temporal_safe_current`。低容量生命周期候选虽将 OOF 假命中 34/228→18/86，冻结外层为 12/12、双向时点最差 4 根，但 2012–2020 最终拟合的 22 事件最晚入场 9 根，故未晋升。完整 V53、Gate2/Gate3 和生产权仍未建立。 |
| [filter_parameter_workflow.md](filter_parameter_workflow.md) | 对指数/组合先算长期滚动单位机会密度，再输出滤波频率参数推荐和参数变化趋势。 |
| [filter_directional_information_workflow.md](filter_directional_information_workflow.md) | 回测前扫描 DII 频率曲面，判断滤波方向是否稳定指向未来收益，并区分宽厚正山脊与孤立尖峰。 |
| [filter_prerequisite_workflow.md](filter_prerequisite_workflow.md) | 滤波策略前置研究：在策略开发前区分父频段结构显著性、子频段滤波有效性和父子交互解释力。 |
| [filter_prerequisite_optimizer_workflow.md](filter_prerequisite_optimizer_workflow.md) | 滤波前置评分机制优化工作流：优化父/子频段评分权重与验证边界。 |
| [filter_tool_selection_workflow.md](filter_tool_selection_workflow.md) | 在已固定频率区间上，用非收益信号质量评分选择 EMA / Fourier / IIR / Wavelet 工具。 |
| [filter_timing_strategy_workflow.md](filter_timing_strategy_workflow.md) | 用已注册策略模板构造滤波择时策略：既支持大周期方向门禁 + 本周期触发，也支持单周期滤波分量触发，并输出对照/并列回测。 |
| [filter_parent_flat_child_spacing_oracle_workflow.md](filter_parent_flat_child_spacing_oracle_workflow.md) | 父级横盘窗口与执行子频段的未来信息上限配频：先测 `L_flat/P_parent`，再用完整子周期公式决定尺度；当前单波先验为父/子约 5–6，非实盘授权。 |
| [filter_1000d_context_for_200d_workflow.md](filter_1000d_context_for_200d_workflow.md) | 因果验证`1000D→200D→40D`主链的第一条边；当前1000D方向有积极候选信息但阶数敏感，只允许进入200D图形训练素材，不得冻结成硬门。 |
| [filter_1000d_context_200d_graph_first_batch_workflow.md](filter_1000d_context_200d_graph_first_batch_workflow.md) | 在200D门内按完整事件训练无上下文、共享1000D连续上下文、上涨/横盘分桶三组图形执行器；当前共享收益不稳定、分桶失败，40D继续关闭。 |
| [filter_monthly_carrier_q_regime.md](filter_monthly_carrier_q_regime.md) | 把自然月作为行情载体，归因 P40 月内 Q 偏好，并用上月形态与 Butterworth 背景选择下月 Q；P160 月载体仅作尺度失配对照。 |
| [filter_frequency_band_crowding_out.md](filter_frequency_band_crowding_out.md) | 用五个因果 Butterworth 明确带通区分机械份额轮动与绝对功率挤出；历史结果只支持约 3 日中位持续的主导权轮换，不支持固定能量预算或动态 Q 路由。 |
| [filter_frequency_trade_quality.md](filter_frequency_trade_quality.md) | 五频段单笔质量对照：训练期选参的 Laplace IIR 随周期增大表现为胜率下降、盈亏比上升；明确 Butterworth 表现为胜率上升、盈亏比不单调。结果只是历史机制诊断。 |
| [cloudridge_3_0_hierarchical_phase_state_machine_workflow.md](cloudridge_3_0_hierarchical_phase_state_machine_workflow.md) | 3.0 图形归因、慢背景—本级别—快纠错状态机运行、输出解释与停止条件。 |
| [filter_timing_strategy_3_0_causal_action_router_workflow.md](filter_timing_strategy_3_0_causal_action_router_workflow.md) | 3.0/P40 事件级因果动作价值研究；初始与唯一左尾优化均回退 `always_trade`，当前决策 `keep_naked_p40`。 |
| [cloudridge_3_0_iir_mechanism_challenge_workflow.md](cloudridge_3_0_iir_mechanism_challenge_workflow.md) | 裸P40 IIR三项决定生死验证：当前低容量因子不能稳定拆出IIR右尾；固定通道突破专家在IIR空仓期取得4/4正折与约+1.30pp历史年化增量；支撑反弹和三动作no-harm失败。 |
| [cloudridge_3_0_trend_risk_continuous_challenger_workflow.md](cloudridge_3_0_trend_risk_continuous_challenger_workflow.md) | 用原价40/160/640趋势、64/640波动风险和五档连续仓位同暴露挑战裸IIR；主挑战者只保留15.73%净收益与41.88%右尾，不能替代IIR；简单趋势虽有4/4折同暴露时点价值，但只能作为低换手诊断基准。 |
| [cloudridge_3_0_iir_orthogonal_state_mining_workflow.md](cloudridge_3_0_iir_orthogonal_state_mining_workflow.md) | 冻结P40 IIR与模型，分两轮挖掘正交状态；宏观流动性/景气家族通过信息门（3/4折、错位分位0.972），但直接Q路由在成本和换手门失败，冻结信息资产并保留裸IIR。 |
| [cloudridge_3_0_trend_regime_segment_validation.md](cloudridge_3_0_trend_regime_segment_validation.md) | 3.0/P160 因果防抖趋势三态分段验证；对照后验通道和未来路径起点，当前裁决为 `trend_state_definition_not_yet_sufficient`。 |
| [filter_timing_strategy_3_0_frequency_fusion_fair_battle.md](filter_timing_strategy_3_0_frequency_fusion_fair_battle.md) | 3.0 多频公平对照：训练期相关甜点稳定选择 P40/P160/P640；先叠加后判方向 pooled 有 +3.62pp，但仅 2/4 正折且 15bps 失败，仍保留裸 P40。 |
| [filter_timing_strategy_3_0_amplitude_phase_compensation_workflow.md](filter_timing_strategy_3_0_amplitude_phase_compensation_workflow.md) | 3.0 振幅—相位因子工作流：验证近频相位差不等于独立信息，以 P40/P160/P640 构建因果速度容量/相位代理；减法版 pooled +6.18pp 且胜率改善，但仅 2/4 正折、盈亏比与假开仓门失败，仍保留裸 P40。 |
| [filter_timing_strategy_3_0_genetic_rf_dynamic_iir.md](filter_timing_strategy_3_0_genetic_rf_dynamic_iir.md) | 3.0/P160 遗传因子—随机森林动态 Q 验证：oracle 显示参数异质性很大，但价格内生因子无法稳定识别；GA+RF pooled -1.83pp，保留裸 Q=1，production=false。 |
| [cloudridge_3_0_factor_usage_discovery_workflow.md](cloudridge_3_0_factor_usage_discovery_workflow.md) | CloudRidge 3.0 因子用途发现工作流：8 个 namespaced action、0/1/N 用途发现、CLI 入口；identity=proposed，cutover=legacy_read，production_authority=false。 |
| [filter_timing_strategy_2_0_p13_boundary_workflow.md](filter_timing_strategy_2_0_p13_boundary_workflow.md) | 滤波择时 2.0 的 p13 父级斜率分桶工作流：输出四条候选切点、五桶原生 IIRP 年化贡献和单笔期望。 |
| [filter_timing_strategy_2_0_bucket_optimization_workflow.md](filter_timing_strategy_2_0_bucket_optimization_workflow.md) | 滤波择时 2.0 p13 五桶逐桶优化工作流：固化 B1 已验证的命中锁定、入场素材约束、出场图形归因、RF 逻辑提取、可解释状态机曲面和 L-level 平台期停止规则；B5 外部回传细节归档在 ops 回收报告。 |
| [filter_workflow_chain.md](filter_workflow_chain.md) | 把时间序列体检、DII 全频谱发现、正山脊聚类、载体投影、工具选择、周期层级配对、A股T+1/日线附近策略前执行风险提示、择时回测、图表渲染和 `research_decision` 决策矩阵串成一键闭环；参数工作流仅为独立诊断。 |
| [filter_opportunity_queue.md](filter_opportunity_queue.md) | 多层择时机会队列：把已固化 L1/L2/L3 的方向门和买点触发合成证据排序的状态队列和梯度仓位；不重新调频段。 |
| [cloudridge_tracking_basket.md](cloudridge_tracking_basket.md) | 云脊小篮子追踪框架：用十几只到几十只等权股票高相关、高波动追踪云脊指数，并用健康度决定持有或换仓。 |
| [filter_protected_reversal_workflow.md](filter_protected_reversal_workflow.md) | 大周期方向保护下的 1min/5min 小周期反向/乖离入场工作流；小周期不能无保护逆高一级趋势。 |
| [filter_post_walk_forward_tuning.md](filter_post_walk_forward_tuning.md) | WF 之后的生产就绪调优：渲染买卖点图，量化踏空/持有下跌/反复交易，输出跨周期通用调优卡；任何新治理算子必须做前后图形复核。 |
| [t0_fund_strategy_workflow.md](t0_fund_strategy_workflow.md) | T+0 可日内交易资产策略组主链路：ETF/LOF/QDII 基金资金池、`cn_t0_fund_v1`、Open/Stable/Low-follow/Discount、账户竞争、有效因子变体放大、事件库/归因/WF 迭代闭环，以及先候选/选票、再买卖点、最后账户竞争的优化优先级；Low-follow 是 ETF/LOF 与可转债扩展的统一 opportunity list 主场。 |
| [t0_convertible_bond_strategy_workflow.md](t0_convertible_bond_strategy_workflow.md) | T+0 可日内交易资产策略组下的可转债资产适配子链路：先区分低溢价正股跟随、高估值转债自身炒作和灰区；高估值炒作已作为 ETF/LOF 博傻低位补涨扩展接入 shared opportunity list，但保留可转债自己的转股溢价、正股联动、3 秒点火、卖点风险和容量/冲击门。 |
| [etf_lof_dynamic_label_rotation_workflow.md](etf_lof_dynamic_label_rotation_workflow.md) | ETF/LOF 动态标签 Top-1 轮动：不做持仓穿透，不用基金名称静态贴标签，用滞后价格/波动/流动性/NAV/coverage 行为标签驱动单品种轮动研究。 |
| [etf_lof_l0_usage_trial_v11_preview_workflow.md](etf_lof_l0_usage_trial_v11_preview_workflow.md) | ETF/LOF L0 V11 用途试优化：DataHub v5 全生命周期五门验收、5 簇真值候选、primitive-8 血缘修复基线和 Factor Usage v2 exact raw-feature 试验；当前 no-selection、legacy_read、production_authority=false。 |
| [etf_lof_proxy_factor_rotation_workflow.md](etf_lof_proxy_factor_rotation_workflow.md) | ETF/LOF 行业/风格代理因子轮动：代理暴露、Cloudridge/PIT 状态和 tree-first RF TopK 候选池识别；RF 只授权池内择一研究，不授权生产。 |
| [risk_off_residual_protection_strategy.md](risk_off_residual_protection_strategy.md) | Residual Risk-Off 风险防护策略：一级风险防护策略；旧 residual 风险预算 overlay 是基础能力，当前 production `final_publication_candidate_v1` 仍阻断，第一门已用信号时点代理把 weak-or-false 从 `13` 压到 `5`，并以 `research_preview_not_production` 预览包接入 CloudRidge 风险背景层；历史 research-only / corrected overlay 段落保留为历史归因证据和过度覆盖反例，不授权为独立交易系统。 |
| [multifactor_rotation_strategy_potential_workflow.md](multifactor_rotation_strategy_potential_workflow.md) | 多因子轮动策略潜力诊断工作流：运行 `audit_multifactor_rotation_strategy_potential_v1.py` 计算三层反事实上界（Universe Ceiling / Signal Ceiling / Realized）和 4 个归因缺口；`production_authority=False` 研究诊断，禁止作为交易信号。 |
| [multifactor_rotation_strategy_potential_attribution_workflow.md](multifactor_rotation_strategy_potential_attribution_workflow.md) | 多因子轮动策略潜力归因工作流：运行 `audit_multifactor_rotation_strategy_potential_attribution_v1.py` 做 per-guard 一阶反事实分解，定位回测收益与策略潜力之间的差距来源；2 个 sync guard 阻断漂移。 |
| [factor_rotation_technology_selection_governance_workflow.md](factor_rotation_technology_selection_governance_workflow.md) | 多因子轮动技术选型治理工作流：在运行模型前声明技术路线；RF/tree 是高维因子-状态交互的优先非线性研究层，并阻断 GNN/PPO 等高级模型绕过 PIT 图、泄漏测试、执行模拟和基线对照。 |
| [factor_rotation_best_practice_research_workflow.md](factor_rotation_best_practice_research_workflow.md) | 多因子轮动最佳实践研究工作流：说明 local smoke、DataHub 正式研究、技术路线选择和产物阅读顺序。 |

## 工具：因子构造与搜索

| 文档 | 适用任务 |
|---|---|
| [feature_factor_library_workflow.md](feature_factor_library_workflow.md) | 特征-因子库工作流：新特征先入 Feature Library，外部声明因子和内部研究因子再引用 FeatureSpec，最后通过策略绑定证据晋升或淘汰；标签/偷看未来特征不得进入生产推理。 |
| [macro_factor_pool_workflow.md](macro_factor_pool_workflow.md) | 宏观因子池工作流：物化 DataHub 宏观核心序列、超额流动性口径、广义周期位置代理和股票派生上下游相关性因子。 |
| [macro_micro_historical_replay_workflow.md](macro_micro_historical_replay_workflow.md) | 宏观—微观历史重放：固定版本数据用途门、PIT 对齐、机制解释票据、制度事件叠加和未解释问题队列。 |
| [public_factor_library.md](public_factor_library.md) / [public_factor_pool_index.md](public_factor_pool_index.md) | 公开因子库检索、WorldQuant 101 / Qlib Alpha158 / Qlib Alpha360 / GTJA Alpha191 池级成员索引与 V3 shared asset P2；也可用 `factor_spec:<spec_version>` 接入内部研究因子的上下文、记忆和交接预览。工具，不是策略组。 |
| [standard_factor_library.md](standard_factor_library.md) | 标准因子库使用；工具，不是策略组。 |
| [formulaic_alpha_dsl.md](formulaic_alpha_dsl.md) | Formulaic Alpha DSL 写法；工具，不是策略组。 |
| [mining_template_search.md](mining_template_search.md) | 模板搜索使用；工具，不是策略组。 |
| [genetic_factor_mining_workflow.md](genetic_factor_mining_workflow.md) | 遗传/符号挖因子项目级工作流：把 T0、多因子轮动、Risk-Off、滤波择时的补因子步骤统一到受约束搜索、候选资产和策略门禁。 |
| [symbolic_factor_search.md](symbolic_factor_search.md) | 符号因子搜索使用；工具，不是策略组。 |

## 工具：深度模型

| 文档 | 适用任务 |
|---|---|
| [deep_factor_models.md](deep_factor_models.md) | L6 深度因子模型训练和约束；可作为策略生产工具，不是策略本身。 |

---

## 维护规则

- 用户文档应从任务出发，优先给出命令、输入、输出和常见失败处理。
- 架构决策写入 [`../adr/README.md`](../adr/README.md)，运维/口径写入 [`../ops/README.md`](../ops/README.md)，schema 契约写入 [`../schemas/README.md`](../schemas/README.md)。
- 若用户指南声称某能力已实现，必须能在 [`../requirements/README.md`](../requirements/README.md) 找到对应事实和证据。

- [CloudRidge 父桶斜率分类器工作流](cloudridge_parent_bucket_slope_classifier_workflow.md)
- [CloudRidge 父桶四线有效性校准工作流](cloudridge_parent_boundary_effectiveness_workflow.md)
- [CloudRidge 父桶 B4/B5 暴跌反弹边界工作流](cloudridge_parent_b5_rebound_boundary_workflow.md)
- [CloudRidge 60m 基础滤波代理工作流](cloudridge_60m_base_filter_proxy_workflow.md)
- [CloudRidge 物理斜率父桶边界工作流](cloudridge_physical_slope_bucket_boundaries_workflow.md)
- [CloudRidge 统一形态五桶分类器工作流](cloudridge_parent_regime_shape_classifier_workflow.md)
- [滤波择时 2.0 p13 父级斜率分桶与 IIR event 交易边界工作流](filter_timing_strategy_2_0_p13_boundary_workflow.md) — 当前重建入口；父级 bucket 只做参数路由，同一原生 IIR 命中事件最多一买一卖。
- [滤波择时 2.0 p13 五桶逐桶优化工作流](filter_timing_strategy_2_0_bucket_optimization_workflow.md) — B1 已验证流程的复用入口；入场只用命中保留素材训练，RF/tree 默认只作出场逻辑提取，L-level 必须相对当前锁定版本过 fixed OOS；B5 单次回传证据不写在用户工作流正文，转到 `ops/filter_timing_strategy_2_0_b5_handoff_recovery_20260707.md`。

- [CloudRidge 2.5 全桶融合编排工作流](cloudridge_2_5_all_bucket_orchestration_workflow.md) — B1/B2~B4/B5 并行执行但策略不合并。
- [CloudRidge 2.5 完整策略信号代理审计工作流](cloudridge_2_5_full_strategy_proxy_audit_workflow.md) — 每桶候选拼接成完整策略信号 research proxy，并与 1.0 对比。
- [CloudRidge 2.5 当前五段组合发布工作流](cloudridge_2_5_current_full_strategy_publication_workflow.md) — 组合 PS001~PS005 当前候选，生成双基准回测并发布 Baylum current timing package。

## T0 基础设施现代化工作流入口

| 任务 | 入口 |
|---|---|
| T0 Feature Library 接入 | [t0_feature_library_workflow.md](t0_feature_library_workflow.md) |
| T0 Feature Panel / DataHub 证据门 | [t0_feature_panel_workflow.md](t0_feature_panel_workflow.md) |
| T0 失败桶与因子画像 | [t0_failure_bucket_factor_profile_workflow.md](t0_failure_bucket_factor_profile_workflow.md) |
| T0 L1 候选池识别 | [t0_l1_candidate_pool_workflow.md](t0_l1_candidate_pool_workflow.md) |
| T0 L2 opportunity row 排序压缩 | [t0_l2_opportunity_ranking_workflow.md](t0_l2_opportunity_ranking_workflow.md) |
| T0 L3 true-3s 账户验证 | [t0_true3s_account_validation_workflow.md](t0_true3s_account_validation_workflow.md) |
| T0 Experiment Recorder | [t0_experiment_recorder_workflow.md](t0_experiment_recorder_workflow.md) |
| T0 Production Gate / ResultPackage | [t0_production_gate_workflow.md](t0_production_gate_workflow.md) |
| 股票因子用途发现工作流 | [factor_rotation_factor_usage_discovery_workflow.md](factor_rotation_factor_usage_discovery_workflow.md) |
| ETF/LOF 因子用途发现工作流 | [etf_lof_factor_usage_discovery_workflow.md](etf_lof_factor_usage_discovery_workflow.md) |

所有入口绑定 `t0_infrastructure_modernization_v1`，并保留 `t0_pure_speculation_pool_framework_v1`。
- [多因子状态—因子配对研究数据准备手册](multifactor_research_data_readiness_workflow.md)：XDXR V9、自建行业 L1/L2/L3×四构造、165 个非财务因子、21 个严格年报 PIT 因子、宏观 V90 6+3 序列及全部指数面已 9/9 验收，八个状态也已完成 V9 复验。机器合同与白皮书见 [`multifactor_research_data_contract@1.0.json`](../ops/multifactor_research_data_contract@1.0.json) 和[数据准备白皮书](../ops/multifactor_research_data_readiness_whitepaper.md)。数据准备和 2009—2020 正式配对年度会话均已完成。
- [REAKA股票级机会账本工作流](reaka_stock_opportunity_ledger_workflow.md)：先冻结后见oracle合同，再生成主控股票赢家账、月/年复盘和去身份代理问题包；oracle只定位因子表征/装配缺口，不是运行信号或可实现收益。
- [REAKA策略—账本—因子提案三角工作流](reaka_factor_improvement_triangle_workflow.md)：先选表征/装配/开放问题，再按0.3并行组合构建隔离lane；代理月度H20证据必须由主控运输到周度H20权威视图，不得自行宣称策略改善。
- [REAKA因子代理并行组合工作流](reaka_factor_delegation_portfolio_workflow.md)：先合并同根问题，再分配唯一定向责任单元和最多两个开放lane；所有lane看全局去身份账本，但不读兄弟结果。
- [REAKA 0.3代理主控自演练工作流](reaka_factor_delegation_self_pilot_workflow.md)：主控亲自执行定向与开放lane，修复allowlist、全局问题图读取、候选字段校验和lint问题后从头重跑。
- REAKA 0.4第二轮分发文档已消费并删除；本轮验收仅保留O1冻结公式的v0.5干净重实例权，不再允许新公式分发。
- [REAKA V1距离账本案例](reaka_top10_opportunity_gap_casebook.md)：已被V2可交易、因子关联账本取代，仅作历史证据，不再用于用户归因。
- [REAKA可交易、因子关联机会账本V2工作流](reaka_stock_opportunity_ledger_v2_workflow.md)：重建日/周/月末账本，分离小盘与事件高开，并将每只Top股连到PIT市值、自建18-L1行业和98个注册因子。
- [REAKA方向性放量×同伴协同V2外部AI返工提示词](reaka_trend_coherence_volume_corrected_external_ai_validation_prompt.md)：封存无效的正趋势单臂，改用方向性20/60日放量、先过滤后rank，只重做成交确认、动态同伴和低估值三臂。
- [REAKA机会账本V3工作流](reaka_stock_opportunity_ledger_v3_workflow.md)：重算周度云脊成分，生成小盘/大盘等权指数实体，保留中盘个股，物化日/周/月账本与周度最差20段。
- [REAKA residual-only 当前模型状态](reaka_residual_only_model_status.md) → [P6.6固定K1残差工作流](reaka_intraday_K1_residual_contract_workflow.md)：用户已停止当前K2并保留`d8-h8-K1-r0` fit-prefix现任。P6.6.0合同已冻结，只开放P6.6.1预检；历史d16/线性/账户结论已撤权，不得继承。
- [REAKA P6.6.1外部AI接管提示词（历史已撤权）](reaka_p6_6_external_ai_handoff_prompt.md)：用户已明确改任Codex为当前主控；旧“外部AI不得验收”条款不再有dispatch authority，仅保留历史边界证据。
- [REAKA P6.6.2 V1.3工作流](reaka_intraday_K1_residual_simple_workflow_v1_3.md) → [执行结果](../ops/reaka_intraday_K1_residual_simple_result.md)：用户已改任Codex为主控；简单残差双重放完成等待用户复核。线性MSE改善但振幅身份失败，MLP不稳定，暂留K1+r0；DRC/账户关闭。
