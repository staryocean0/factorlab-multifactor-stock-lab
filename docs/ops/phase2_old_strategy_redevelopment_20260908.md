# Phase II 启动任务：用新实验室重新开发旧实验室策略

日期：2026-09-08
任务 ID：`P2-BASELINE-MAP-20260908-01`
状态：`active_cloud_mapping_no_new_model_run`

## 1. 开始条件

`docs/ops/phase1_lab_validation_20260908.md` 已将 Phase I 判为：

- mathematical_integrity = PASS
- financial_implementation_capability = PASS

因此按 `docs/ops/reaka_research_mission.md` 正式进入 Phase II。

## 2. Phase II 的研究对象

Phase II 不是继续优化 R3 子机制，也不是把旧 checkpoint/参数原样搬进新实验室。研究对象是：**旧实验室已经开发过的 REAKA 主动多头 A 股策略的金融任务与可辨识行为**。

第一步必须恢复并冻结以下旧策略语义：

1. 预测/排序的金融对象；
2. 股票 universe 与资格过滤；
3. 市场/指数、size、industry、股票横截面等输入及其当时角色；
4. 决策 clock、label horizon、fill 语义；
5. score/ranking、TopN/权重、买入受阻与换仓规则；
6. 成本、账户与比较基准；
7. 旧策略共同根、分支关系与历史证据边界。

不能以版本名相似代替这一身份恢复。

## 3. 已恢复的历史事实与当前解释

已确认的历史材料包括：

- `docs/user/reaka_strategy_v2_external_ai_handoff_v2.md`：旧 V2 金融任务曾把上一自然月 CloudRidge 1σ observable condition 配到指数/行业通道，size 不配该条件；这属于旧设计材料，不自动成为新实验室必选结构。
- `docs/ops/reaka_v2_stage4_observable_factor_pairing@1.0.json`：旧 Stage4 有 index/industry component contribution 的实际 pairing contract；但历史 Stage4 当前仍未被接受，不能当成新策略已验证增量。
- `docs/ops/strategy_slice_rebuild_whitepaper.md`：V5/V6/旧 V7 是共享 V4 common root 的并行历史实验；旧 V7 污染，V6 与 V2 账户等价且落后 V5；2021-2026 已被旧研究消费，不得重新包装成 fresh evidence。
- `docs/ops/strategy_progressive_development@1.0.json`：新实验室重开发仍要求金融语义、数学身份、时序因果、账户、来源与证据范围等 hard-validity gate；progression 与候选 promotion 分层。

这些材料现在只用于**恢复旧金融任务和身份**，不用于从历史赢家中偷选参数。

## 4. 新实验室映射原则

### 4.1 先建等价基线

先回答“同一个旧金融任务，在新实验室正确语义下能否重建一个可比较基线”，然后才允许问新实验室增加了什么。

禁止一开始就把 R3 reliability、state-mask、K 数或 residual arm 当新策略答案。

### 4.2 paper core 与 optional factors 分离

新实验室当前 paper core 是 `CORE_SPATIAL_H20` 48 identities。market/index、size、industry/context 可作为金融/条件/可选因子进入，但不因论文名字而强制进入 core。

size/industry 若使用当前 structural registry，必须先满足 `available_at`/PIT availability gate；历史 Stage4 的 pairing existence 不等于当前因子准入。

### 4.3 总收益目标优先

旧策略若最终目标是主动多头股票排序，则迁移后的 primary target 必须是与持仓决策一致的股票未来总收益/可交易排序对象。金融 `epsilon` 可以作为子通道，但不得默认把 residual-only score 等同于总收益 score。

### 4.4 时钟和账户不降级

迁移不得因为“复现旧策略”而恢复已知乐观/错误时钟。信号可用 qfq 视图时仍不代表 fill 可用 qfq；具体 clock/fill 必须由现行时间合同裁决。最终可投资候选需要 post-training account audit，但本任务不提前运行账户。

## 5. 本任务立即执行范围

`P2-BASELINE-MAP-20260908-01` 只做云端可完成的身份恢复与映射，不进行新模型训练：

1. 建立 old-component -> new-lab-object 对照表；
2. 标出 `directly_mappable / requires_semantic_redefinition / requires_local_source_evidence / historical_only_rejected`；
3. 固定第一版等价基线的 target、clock、factor roles、score/ranking/account 接口；
4. 找出真正需要本地数据/旧源码才能闭合的最小依赖；
5. 只有映射冻结后，才发出一个具体可执行的本地 rebuild 任务。

## 6. 初始映射

| 旧策略对象 | 新实验室对象 | 当前状态 | 规则 |
|---|---|---|---|
| 股票横截面预测/排序 | H20 stock-specific score | directly_mappable | primary 必须保持股票级总收益排序语义 |
| 历史股票特征 | `CORE_SPATIAL_H20` 48 paper core | directly_mappable at role level | 具体 48 identities 按冻结产物，不把可选因子偷塞进 core |
| 市场/指数共同成分 | market/index optional financial/context channel | directly_mappable at math level | 只有通过 beta/股票异质响应才可宣称影响横截面 |
| size | structural size exposure | requires_local_source_evidence | registry 已有接口但当前 requires availability gate |
| industry | structural industry exposure / optional pairing | requires_local_source_evidence | registry 接口存在；旧 Stage4 不是当前 PIT 通过证据 |
| CloudRidge 1σ `S_obs` | optional observable condition | requires_semantic_redefinition | 不等于 latent state/operator；公式身份未闭合前不得猜 |
| financial epsilon | financial residual subchannel | directly_mappable | 不等于 latent residual；不能自动替代 total-return score |
| latent residual | post-operator dynamics correction | directly_mappable as optional model mechanism | 不能修补 upstream financial semantics failure |
| old score | ranking candidate | requires exact old identity | 先恢复公式/normalization/clock，不直接继承 checkpoint |
| old account | score+portfolio+cost+execution | requires exact old identity | 历史缺失来源保留为限制；不能伪造完整复现 |

## 7. 当前最小阻塞项

云端现有仓库还不足以唯一恢复“旧策略等价基线”的完整可执行身份，至少还需从**已有仓库历史/本地原策略材料**闭合：

- 旧策略最终被用户认可/使用的 canonical policy id 或共同根具体实现；
- 对应 score 构造、TopN/权重、调仓、成本与 fill 的精确参数/源码身份；
- 若等价基线需要 size/industry，实际 PIT 可得性来源；
- 若需要 CloudRidge 1σ，精确 `S_obs` 公式身份（此前 R3 已明确不得猜）。

这里不是要求重新上传已接受的 R1/R2 大数组。优先复用仓库历史和本地已有源码/中间量，只补身份缺口。

## 8. 与正在进行 R3 的关系

已完成 R3 结果保留为 Phase I/未来增量研究材料，不删除、不改写。自本任务生效后：

- 不再把 R3 transfer/score 扩展作为总研究“下一步”；
- 已在本地进行中的同任务边界检查可以完成并回传，但不得自动启动新的 24 项评分；
- Phase II 等价基线身份冻结之前，不使用 R3 结果选择旧策略迁移参数。

## 9. 下一检查点

云端下一动作：继续从仓库 Git 历史/旧策略权威材料恢复 canonical old policy，并形成 `P2-BASELINE-SPEC`。若精确执行身份只存在用户本地 FactorLab，则随后提交单一 `LCL-P2-...` 任务，命令只引用仓库中实际存在的脚本；在脚本落库前绝不虚构命令。

本任务没有授权 production、fresh-OOS 声明或真实资金执行。