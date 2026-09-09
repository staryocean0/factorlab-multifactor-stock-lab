# R3：历史残差建模与原有条件信息的最小可比设计

日期：2026-09-06。任务：`R3-CONDITION-DESIGN-20260906-01`。基点：开发分支 `1c061e658772cfe668924644c556731cd18a2687`；main 查询点 `3f67b9fd0a20da8d0f2f33276f4870bba2cbf04e`。这是云端与本地协作，沿用 AGENTS Protocol 1/2。本文件是一次研究设计与执行任务，不是新的全局准入合同。

## 1. 这一步的结论

上轮零拟合比较已经完成，不重复。它证明在既有2017样本上，现任K1相对四个已固定历史规则存在描述性平均排序优势，但不能把约0.027的RankIC差直接归给条件特征。参见[已验收结果](../../cloud_results/local_handoff_R3_20260906/cloud_acceptance/cloud_review.md)。

本轮检查了现有消融注册表、实际编码/gate、特征装配、normalizer与fit-prefix训练路径。**已核阅证据中，没有可直接接受为“同一K1训练配方、同一支持、只移除原有条件信息”的结果。** 这不是对所有本地未上传文件的不存在证明。重复扰动或账户归因不能补上该比较。

最小主比较只有两臂：**F（完整输入）与H（同结构、仅历史epsilon可变输入）**。已有四个零拟合基准B全部保留为参照，不能追封均值反转为事前唯一基准。只有需要分开状态与暴露来源时，才增加可选E桥接臂；不强制三臂全部训练，不开K/学习率/残差网络搜索。

云端已实现和测试三种输入视图及局部模型子类适配器；它们不是完整训练runner。本轮没有执行真实拟合或新推理。需要本地执行的受限计算及实现接线写在第7节；由用户转交，不声称已经派发。

## 2. 现有证据的复用裁决

| 已读取对象 | 可以复用 | 不能代替主对照的原因 |
|---|---|---|
| 现任fit-prefix两时钟formal、已验收冻结分数 | F的数值参照；身份和数值路径一致时可作F臂结果 | 仅有全输入模型，没有已核实的同配方H臂 |
| `reaka_r3_frozen_compare.py`与上轮490行日表 | 原目标、支持、逐日rank-z集成、四个B基准和已有描述结果 | B没有经过与K1相同的表示学习，F−B同时包含多种差异 |
| `ReakaPaperAblation` / `stage6_arm_spec` 的 `without_gate` | 参考何谓去掉gate | 原注册还涉及adaptive selector和diffusion；K=1也不会自动关掉diffusion。且gate关闭是图结构变化，不是同图移除X信息 |
| `vanilla_autoencoder`、`without_drc`、`without_aks`、旧residual分支 | 相应算法定义或特定诊断 | 改变转移/残差/选择器；不等于只移除条件输入；代码中有分支不等于对应结果已执行 |
| 原clock attribution及小幅input perturbation | 相应时钟、配置、数值敏感性诊断 | 不是独立训练的H对照 |
| 现行output目录中的机会账、K线selector、Stage3/Stage4 | 各自已有证据范围 | 账户选择/归因和状态描述，不是本目标的配对特征消融；旧Stage4仍未接受 |

检索还包括默认分支关键词 `no_feature`、`ablation`（无结果）及当前output目录。搜索未命中不是全工程不存在证明；本地只需在已知相关实验目录查找同口径结果，不需要全湖或全盘扫描。命中结果须有输入/模型/训练/评价身份，名称相似不足以复用。

当前paper与Stage6文件blob分别为 `40cde6c455bbe7adfebaec2b1e677eed1ab93afa`、`6f626ac46d3a73a16ab718f3e64a8fcffde66889`，与R1输入提交的文件blob不同。已读取的旧/新encode核心一致，但**没有据片段一致宣布整套训练数值路径相同**。普通守卫或说明变化不自动要求重训；复用F时要判断真正影响计算的差异。

## 3. 金融问题与三个输入视图

所有臂预测同一个 `epsilon_future` H20金融残差，使用同一个已存盘的历史epsilon。**H不是“没有任何因子信息”**：epsilon本身经过金融残差化，已包含这一来源的影响。这里移除的是模型的直接X特征通道，不重新定义收益或上游残差。

现任 `assemble_inputs` 的71通道（零起点、左闭右开）：

| 通道 | 实际含义 | F | H | 可选E |
|---|---|---|---|---|
| 0:14 | 14个OT状态值，消费股票所属cross-fit分支 | 保留 | 置零 | 置零 |
| 14:28 | 状态可用性掩码 | 保留 | 置零 | 置零 |
| 28:42 | 股票因子暴露 | 保留 | 置零 | 保留 |
| 42:56 | 暴露可靠性 | 保留 | 置零 | 保留 |
| 56:70 | 暴露有效掩码 | 保留 | 置零 | 保留 |
| 70:71 | 原实现恒为零的age占位 | 原零 | 零 | 原零 |

第70号通道不是any-available指标。E的暴露与可靠性也随时间变化，不能称作静态或“完全无条件”模型。

三个视图都保留原10点历史序列、原K1/r0、同网络拓扑与名义维数。**H保留feature-LSTM和gate，但输入恒为零；其bias仍可学习，零输入不等于隐藏向量恒零，也不等于 `without_gate`。** 输入权重在H中可能天然无梯度，不能用“所有参数都必须更新”拒绝H。这是同拓扑信息移除对照，不承诺相同的有效自由度或优化难度。

### 对比能回答什么

- 主量 `F−H`：在固定表示/训练配方下，直接X信息包的描述性增量。
- `H−B`：同样的历史epsilon经K1式表示学习，相比固定历史规则的增量；不能自动归为Koopman算子本身，因为还含编码、非线性、训练和集成。
- 可选 `F−E`：给定暴露/可靠性/其掩码后，OT状态值及状态可用性这一包的增量。
- 可选 `E−H`：暴露/可靠性/有效性这一包的增量，不是纯beta单项贡献。

这些是算法输入消融，不是市场经济因果效应，也不是信息论意义的“只有这一机制”。同支持下指标差可以算术相减，但不是唯一可加的金融归因；交互使不同消融顺序的解释不同。第二轮“上一自然月CloudRidge趋势条件”不在本次X修改中，不能继承结果。

## 4. 保持可比的训练与评价配方

### 不改变训练目标

源 `fit_seed` 对 `assemble_inputs` 的历史epsilon运行 `training_objective`，不传future target。模型把十点序列拆成前九/后九错位窗口；重建损失与潜转移损失一起学习。`epsilon_future`只进入冻结模型后的2017评价。不得把H改为直接监督拟合future，再将差值称作条件效应。

采用现任数值配方作为本次受控选择，不宣称它是论文唯一最优参数：latent=8、hidden=8、K=1、r0、Adam LR=0.03、weight_decay=0、batch_size=4096、每臂每seed最多3个完整无放回cycle。种子仍为11/29/47，两时钟分开，集合结果沿用逐日每seed rank-z再平均，不是原始分数直接平均。

fit支持沿原 `split_indices`：inference_rows年份<=2016；不为H另按future标签过滤训练行。评价沿已核2017 labelled行，原顺序与支持digest不变。normalizer沿原fit-prefix身份；不因H数据看似少而重选窗口或重估review尺度。2017决策行的H20标签可能到2018才成熟，不能把“无2018决策行”写成“没有2018实现结果信息”。

### 视图必须贯穿四个实际入口

唯一改动在**原normalization之后、模型使用之前**。F原样复制；H清空全部71个X通道；E清空前28个。必须一致地作用于：DMD初始化、每个训练batch、每cycle的checkpoint损失、评价forecast。训练objective的两个错位窗口都来自同一已投影视图。推理阶段单独置零只支持敏感性，不可当作本实验H。

同一seed各臂从同一预DMD随机初始化出发，不能用已经看过X的F权重/优化器或F的DMD算子warm start H/E。DMD须分别用该臂train-prefix视图估计；优化器状态独立。不同臂相同seed/cycle共享样本遍历顺序。

原 `canonical_loss` 实际只用训练索引最前一个4096行batch。保留这项选择规则：每臂独立选最多3cycle内最小fit-prefix canonical loss，平局取最早；不选2017最优cycle，不暗改成全训练平均。跨臂潜空间不同，loss只用于该臂选周期，不作跨臂金融优劣指标。

### 复用与资源上界

先复用已有、确实同口径的结果。F的原输入、normalizer、配置、seed/cycle选择与数值路径可对应时，沿原六份冻结score复用；不可仅凭模型名字或部分推理一致宣布所有拟合步骤相同。仅有文档/守卫差异不强制重训。

若F可复用且H未做过，主比较最少新增 **2时钟×3seed=6次H拟合，上限18个完整cycle**。若真正的计算差异使F不再可比，则F/H同配方新建隔离对照，最多 **12次拟合、36cycle**，并把原F仅列历史参照；不覆盖现任。这个fallback必须在读取新对照结果前写清具体原因，不能因为H表现太好而重跑F。

可选E另需6次拟合/18cycle；**不是本地任务默认范围**，仅在后续确需状态与暴露拆分时安排。不新增seed、不扩大参数网格、不自动重启更长训练。崩溃的原样续跑记录失败尝试与资源；不能挑seed或cycle扔掉不利结果。

数值非有限/支持不一致/数据身份不符是执行问题；性能弱或负是合法研究结果。不要求每臂复制F的梯度/条件数/能量现象才能给出结果；对应诊断如实保留，确实无效的拟合不能硬算成功比较。

## 5. 评价和结论规则

主评价量是同一天、同一股票集合上的 `RankIC(F)−RankIC(H)` 再按49日等权平均。保留每seed及原rank-z集成，不仅报挑选后的最佳seed。支持不一致不静默取交集或删困难股票，应先报告；原共同支持的局限沿R2/上轮回执保留。

同时输出配对中位数、胜负日、四相位、H20残差十分位差及Top30相对全支持均值。Top30沿原稳定排序和原行顺序，记录ties，不新增按股票收益挑选的tie-break。全体B已有结果可复用到相同支持，不重算分钟、不重放账户。

49日有H20重叠，两个时钟、三seed、四phase不能计为独立市场重复。该2017pilot不根据iid公式宣布p值；若今后要正式推断，须另作与重叠及剩余序列依赖匹配的配对时间块/HAC分析，不能凭“至少4个间隔”保证依赖已经消除。本次预算不为了寻显著性扩年或扩参。

结果读取预先明确：F−H为正，只支持本配方/已消费支持下X包有增量；接近零则该设置未体现增量，不等于所有条件信息无用；负值则在该比较上X包有害，不改方向或重训到正；两时钟相反则保留不一致。即便有正增量，事后OT选型、事件时钟和全量PIT限制不变。

## 6. 本轮代码与测试边界

[输入视图与模型适配实现](../../src/factor_lab/factor_rotation/reaka_r3_condition_views.py)提供两层接口：NumPy批次的复制/验证/信息投影，以及 `condition_model_class` 创建的局部子类，在 `_encode_and_gate` 统一投影输入。原Stage6 objective的两个错位窗口、继承的forecast均调用此方法，DMD及canonical loss再调用objective；因此可以避免只在最终预测入口干预、遗漏训练支路。子类不增加参数或buffer，不猴补原类、不改变旧模型或存盘文件。

[33项合成测试](../../tests/unit/test_reaka_r3_condition_views.py)实际通过。前29项覆盖完整臂恒等、不修改源数组、移除掩码/可靠性、保留E暴露、形状/dtype/有限值/占位及错误输入；后4项用明确标为合成的神经载体，检查子类的参数/状态键不变、F的objective/forecast恒等、H训练双窗口与预测对原X不敏感、bias仍可学习，以及E保留暴露响应。后4项不是原完整Stage6模块的导入/训练回归，也不是实证结果；只执行前向/反向性质检查，没有优化器拟合。

本地接线可以采用以下构造方式；实际config、seed设置和初始化仍必须沿原固定配方：

```python
ControlledModel = condition_model_class(Stage6ReakaModel, "history_only")
model = ControlledModel(
    feature_dim=71,
    config=original_config,
    arm_id="fixed_k_no_residual",
)
```

必须在模型构造前设置原seed，并调用原声明初始化，再在该臂数据上单独DMD；上述片段不自动完成这些步骤，也不从F的训练权重初始化H。四条真实入口应共享这个模型实例，并仍使用原normalizer。

它不是trainer、权限开关或审计器全仓认证。**尚未把它接到原DMD/训练/loss/forecast的所有真实路径，尚无新H或E市场结果。** 不能把单测通过写成训练消融完成。实跑与来源核阅记录见 [execution_receipt.json](../../cloud_results/r3_condition_design_20260906/execution_receipt.json)。

## 7. 本地最小执行任务：LCL-R3-COND-20260906-01

**状态：待用户转交，未自动派发、未执行。** 这是明确包含受限对照拟合的新任务，不是上轮NOFIT重跑，不是重训/替换现任策略。云端没有本地完整输入及原训练模块运行环境；只把实际接线与原数据上的拟合/评分放本地。理论选型、对照定义和验收由本方案固定，不能外包自由调参。

### 本地操作

1. 在主题仓独立worktree读取AGENTS、本文和原R3验收；原FactorLab脏工作区不修改。只查看已知相关实验目录是否已有匹配H/F；有充分身份则先复用。不需要再次R1/R2盘点，不递归全湖。
2. 核对原K1输入manifest、normalizer和原fit-prefix函数；每项路径从原任务/manifest实际读取。输入根仍为原FactorLab：`output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020/formal/{1430,1445}/`；F原参照为 `reaka_intraday_K1_fit_prefix_successor_v1_2011_2017/formal/{1430,1445}/`。本轮不要求分钟DataHub、账户或2026+数据。
3. **需本地实现的部分**：新建隔离的 `scripts/reaka_r3_condition_compare.py`，当前尚无此完整runner，不能直接运行一个假定命令。复用原纯数值函数或有明确差分的适配，接入本次视图/子类适配器；不得解除旧writer守卫、猴补全局normalize函数或覆盖旧formal。提供真实CLI与实现diff。输出为新的 `FactorLab/tmp/LCL-R3-COND-20260906-01/<run-id>/`。
4. 先对F视图恒等与四条接线做合成/小batch回归；确认DMD与canonical_loss也经过视图，H对任意原X变动不敏感，没有`epsilon_future`/评价行流入训练；同seed预DMD初态、样本顺序一致。小batch只是接线，不先查看新2017得分选择实现。以结果前身份记录说明F复用或fallback理由。
5. 只执行主F/H比较，遵守第4节6次或12次拟合上界。无可比来源时准确报告缺口，不挑另一个旧checkpoint凑对照。先完成全部冻结选周期再读2017，差结果照报。E不默认执行。
6. 回传实现/测试、小结果和失败明细；大张量、模型、原数据留本地，不推Actions。收集已运行命令与退出码，不能声称脚本已存在而省略实施步骤。

现在可运行的命令仅是视图单测：

```bash
python -m pytest -q tests/unit/test_reaka_r3_condition_views.py
```

### 一份反馈与必要小产物

回传到 `cloud_results/local_handoff_R3_condition_20260906/`：`local_feedback.md`（版本、输入/normalizer/支持摘要、复用理由、实际拟合次数、cycle、种子、命令、环境、失败与未验范围）、`comparison.json`、`paired_daily.csv`。每seed训练损失和所选cycle可放JSON；大checkpoint/原分数只存摘要和本地位置。候选结果若未完成，清晰列出缺的时钟/seed/比较。

验收看身份与实际干预是否一致、训练与review隔离、同支持、四入口接线、无有利重跑、配对统计能复算，不以金融结果必须为正作为任务通过条件。更新同一沟通记录为“本地已反馈”；云端复核后再改状态。此任务不代签生产、PIT或条件因果性。

## 8. 主要源码定位

- 当前分支 `src/factor_lab/factor_rotation/reaka_intraday_k1_preflight_v1.py`，blob `6942fb2dc20d24307578bc7dda45368afaf3d1f5`：`assemble_inputs`、`normalizer_from_store`、`normalize_batch`，本轮读取1–245、440–575及620–780行。
- 当前 `reaka_paper_v1.py`，blob `40cde6c455bbe7adfebaec2b1e677eed1ab93afa`：注册表与encode/transition/training/forecast，读取1–260、430–700行。
- 当前 `reaka_stage6_daily_engine.py`，blob `6f626ac46d3a73a16ab718f3e64a8fcffde66889`：arm注册表、Stage6ReakaModel的targets=None分支，读取1–260、280–530行等；旧文件blob `ccf4572ee48ee9f9d2440cb12da1a27e461d1d2e`不是当前字节。
- 原输入提交 `2575f9e4d12289fa3916d14f27cb637908614fd9` 的 `reaka_intraday_k1_fit_prefix_successor_v1.py`，blob `f2538b64478c1c05a16c347e69864751661af4cb`：固定配置、fit_seed；原 `reaka_intraday_k1_training_v1.py` 的split_indices/canonical_loss及clock-attribution中的rank-z路径沿已读取R3来源使用。
- 原paper blob `20a2d65790f2511822b6127405b103c05205bfcc`的480–560行与已读当前encode核心相符；这只是片段核对，不是整仓源码认证。

这些来源定位说明设计根据什么代码提出，不要求每次文档修订重新封全仓。未读授权论文全文、未拉市场湖、未合并main、未调用Actions。
