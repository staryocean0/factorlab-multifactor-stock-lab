# REAKA论文未披露参数治理白皮书

日期：2026-08-26

> **2026-08-31 盲测收官覆盖：** 同身份 post-2020 输入扩展通过旧前缀和双运行，
> 固定 `d16-h16-K1-r0` 随后只执行一次 2021--2026。RankIC 六年全正，但
> Top30 1×成本累计/年化约 -6.71%/-1.30%，最大回撤约 -53.15%，只有
> 2/5 完整年份为正，裁决失败。该结果没有产生任何新参数；盲区已消费，不得反调。

> **2026-08-30 residual-only 收官覆盖：** 当前 residual-only 论文层级已执行完
> K1/K2、简单残差、论文 DRC 与固定账户。K2、MLP、DRC 均拒绝；条件线性残差
> 虽通过组件 MSE/RankIC 门，却在 2019--2020 固定真实账户中败给 K1+r0，因此
> 完整策略选择 `d16-h16-K1-r0`。这不是回填默认值，而是事前冻结完整候选间的
> 金融账户裁决。2021--2026 输入尚未同身份物化，盲测和任何再训练仍关闭。见
> [`residual-only收官白皮书`](reaka_residual_only_paper_completion_whitepaper.md)。

> **2026-08-26 继任审计覆盖：** 当前不是 Stage5 或 Stage6 选参阶段，而是透明联合核心的 `joint_core_freeze_review_pack_completion`。旧 LR-boundary、受限 confirmation、GateA/GateB、残差身份、root routing `@1.1`、Stage5 compilation `@1.1` 及论文残差探针全部只读，无当前参数或路由权。补齐主动行业/市值/风格暴露且用户回执绑定透明核心结果前，不得外派神经保真。见[`REAKA二号主控继任审计与装配恢复白皮书`](reaka_controller_succession_audit_whitepaper.md)。

机器目录：[`reaka_paper_parameter_catalog@1.1.json`](reaka_paper_parameter_catalog@1.1.json)

自由度审计：[`factorlab_training_degree_of_freedom_audit.json`](evidence/reaka_paper_parameter_governance_v1_1_20260825/factorlab_training_degree_of_freedom_audit.json)

未决队列：[`unresolved_parameter_queue.json`](evidence/reaka_paper_parameter_governance_v1_1_20260825/unresolved_parameter_queue.json)

## 一句话结论

论文没有写的值不是默认值，更不是可以自由填写的空格。未来每个参数只能取得四种合法来源之一：论文明确值、数学推导、训练前缀测量路由、用户批准的项目政策。其余全部标记为`unresolved`并阻断相应训练。

当前目录覆盖63项参数：论文明确13项、只给公式8项、完全未说明36项、内部不一致1项、FactorLab适配项5项。作者数值复现仍有36项阻断。FactorLab原有22项训练阻断经约束闭包后，压缩为3个真正独立的设计自由度；其余19项成为公式强制值、产品合同值、条件派生值或训练前测量值。

## 1. 外部核查结论

项目已复核本地五页IEEE论文、页面公式和图表，并检索ICASSP官方会议入口、论文题名、作者与公开代码/补充材料。能确认正式论文和会议信息，但没有发现作者公开代码、supplement、environment lock或超参数表。因此当前不能把任何仓库默认值追认为作者值。

## 2. 五类参数身份

| 身份 | 含义 | 可否直接训练 |
|---|---|---:|
| `paper_fixed` | 正文明确给出结构或数值 | 只在同一论文问题下可直接继承 |
| `mathematical_derived` | 可由时间坐标、自由度或不变量推出 | 公式与输入测量齐全后可用 |
| `measured_route` | 没有唯一常数，但有结果前测量算法 | 测量回执通过后可用 |
| `project_policy` | 数学不唯一，由项目明确冻结 | 必须写明不是作者参数并绑定回执 |
| `unresolved` | 当前既无作者证据，也无合法项目决定 | 不得训练，不得回落到类默认值 |

`ReakaPaperConfig`、`Stage6FreezePolicy`及PyTorch构造函数里的现有值只描述历史实现，均不自动拥有未来训练权。

## 3. 可以确定的部分

### 3.1 论文明确的内容

- 日频输入、Qlib Alpha158、窗口T=10；
- 双路径LSTM；
- feature-controlled sigmoid gate，`G`权重属于收益路径；
- selector输入`Z`与`Hy`，使用LeakyReLU和Gumbel-Softmax；
- 训练软选择、推理argmax；
- latent residual定义为`Z_plus-K_selected*Z`；
- decoder最后一个元素作为预测；
- 总损失结构为`Lrec+Lkoop+Ldiff`；
- 2010—2017训练、2018验证、2019—2020测试；
- 日度RankIC评价和Top30模拟。

这些内容可以叫论文固定，但只适用于论文原生问题。把日频改H20、Alpha158改48因子或增加外部金融状态，都必须升为FactorLab适配身份。

### 3.2 可以由数学推导的内容

1. **时间坐标**：历史收益、特征端点、latent推进、decoder、residual和预测目标必须同一步长。当前H20因此是20日动力步、T10、完整足迹200日；5日只负责启动四条相位链。
2. **K容量**：K1永远是最小参照；K>1必须由独立episode、`n_k_eff/DOF`、算子差异、占用和多seed稳定共同解锁。
3. **矩阵结构**：full、diagonal或low-rank由有效转移相对自由度决定，不能默认full `d*d`。
4. **batch与精度**：选择最快且数值等价、显存可容纳的组合，不作为科学调参。
5. **扩散步数和draw数**：取满足残差SNR、分布拟合与Monte Carlo排序收敛的最小值，不继承图像DDPM常数。
6. **checkpoint选择**：先过因果/数值健康门，再使用与产品一致的内层RankIC/价差；重构MSE不能单独决定股票排序模型。
7. **外部状态**：论文没有用户命名状态接口。外部状态必须保留透明主干和上下文依赖证书，不能只缩放特征后交给gate自行处理。
8. **模型叠加**：透明主干系数固定1；模型只以训练前缀正交、非负、有上限残差进入，失败时精确退化为0。

### 3.3 已明确的FactorLab项目政策

- 缺失值使用显式availability mask；
- 2009—2020是已消费开发材料，2021—2026不得读取；
- 三个固定seed只负责暴露随机不稳定，不代表作者seed；
- A股成本使用项目执行合同，不冒充论文成本；
- 自然年与四相位拆分强制报告；
- 论文RankICIR印刷公式内部不一致，FactorLab使用标准`mean(RankIC)/std(RankIC)`并标为项目纠正；
- 当前两个状态采用透明主干，K1只登记为独立时序残差专家。

## 4. 22项表面参数的自由度审计

### 4.1 判据

本审计不问“作者有没有写数字”，而问四个更强的问题：

1. 改变该值是否改变论文方程或产品身份？如果是，它不是同一模型里的普通调参；
2. 给定上游量后，该值是否被维度、时间尺度、概率目标或执行时钟确定？如果是，它是条件派生量；
3. 该值是否只影响同一目标的数值求解？如果是，它是必须有回执的测量型nuisance，不是科学自由度；
4. 在所有约束闭合后，是否仍存在两个数学自洽但不可由训练前事实排序的方案？只有这种情况才登记为真正自由度。

这里的“确定”指FactorLab已声明问题下的最小公式实现，不等于推断出了作者私有实现。作者数值复现门因此仍保持36项阻断。

### 4.2 五项由公式强制

| 参数 | 自洽裁决 |
|---|---|
| `selector.straight_through` | 方程14使用soft alpha混合K；训练前向必须`hard=False`。 |
| `residual.target_gradient_attachment` | DDPM把R当目标分布样本；`Ldiff`必须对R stop-gradient，防止目标移动来降低自身损失。 |
| `residual.x0_mapping` | 方程16直接对R加噪，x0与R同坐标同维；映射必须是identity。 |
| `loss.scale_normalization` | 方程28系数为1:1:1；每个MSE按样本和元素取mean，`Lrec`为两个mean之和，不另加可学习权重。 |
| `optimizer.weight_decay` | 正weight decay会在三项损失外增加第四项；论文原式必须为0。 |

### 4.3 三项由产品合同确定

| 参数 | 上游决定量 | FactorLab裁决 |
|---|---|---|
| `data.stock_universe` | 产品标的与PIT可交易性 | 全A有效日期股票池，执行时买卖真值门；不是模型超参数。 |
| `portfolio.rebalance_frequency` | H20的5日决策启动网格与成交时钟 | 每5个交易日产生新目标，下一交易日开盘执行，其余日期carry。 |
| `portfolio.weighting` | Stage6组合执行合同 | 等权目标、强制携带、确定性同分规则和不可买回填。 |

### 4.4 六项由上游参数条件派生

| 参数 | 依赖 | 派生规则 |
|---|---|---|
| `encoder.layer_count` | 确定性容量根 | 在最小嵌套家族中从一层开始；只能随同一个容量根改变，不能另开深度搜索轴。 |
| `koopman.initialization` | latent gauge、K结构、20日物理步 | 用训练前缀regularized DMD闭式暖启动，再投影到已声明稳定类。 |
| `selector.gumbel_schedule` | selector松弛根 | 最小家族使用常数；只有根自由度明确选择新松弛路径时才允许退火。 |
| `residual.time_embedding_dimension` | latent维度d、残差网络族 | 固定为d；它是同一score network的条件坐标，不建立第二个容量轴。 |
| `decoder.architecture` | d、确定性网络容量根 | 时间点共享的最小一隐层`D:R^d->R`，宽度跟随确定性容量根。 |
| `training.general_initialization` | 激活、fan-in、窗口T、K初始化 | 激活感知方差保持、循环正交、由T给出的chrono forget bias；K单独走DMD。 |

### 4.5 五项只是数值求解nuisance

| 参数 | 训练前选择规则 |
|---|---|
| `optimizer.family` | 在同一目标下选择通过驻点、多起点解等价和性能门的最快求解器。 |
| `optimizer.learning_rate` | 对选定求解器做训练前缀range test，取最大稳定无量纲步长。 |
| `training.coverage_budget` | 按无放回完整覆盖循环计数，运行到预注册收敛容差或最大预算。 |
| `training.early_stopping` | 先过数值/因果健康门，再以内部RankIC/价差平台停止；不得读取外年。 |
| `training.gradient_clip_norm` | 梯度有限时关闭；确需保护时由未裁剪梯度尾部分位数确定。 |

它们不再需要用户逐项拍数字，但每次新训练都必须重新生成测量回执。求解器快不等于可以得到不同科学目标；如果多求解器不能达到预注册解等价，基础设施必须报告`optimization_nonidentifiability`，而不是挑赚钱者。

### 4.6 最终保留的三个真正自由度

1. `network.hidden_dimension`：作为确定性非线性容量根，登记一个以`h/d`为锚的嵌套深度/宽度家族，同时支配encoder、gate与最小decoder；输入输出维度无法唯一决定它。
2. `selector.gumbel_temperature`：在logit尺度归一后仍控制soft离散化的熵与梯度方差；公式只要求正数。
3. `residual.denoiser_architecture`：条件score函数的容量族；DDPM方程规定输入输出和概率目标，但不唯一规定函数类。

这三个是三条根，不是把其下游参数继续拆开搜索。它们必须各自采用一个有界、预注册、计入multiplicity的家族；当前历史值`32/0.75/two-hidden-layer MLP`只有旧实现身份，没有权威。

### 4.7 两层训练门

- **自由度门**：三个根未裁决前保持`blocked`；
- **实例化门**：三个根裁决后，仍须显式写出全部22项的本轮值并绑定条件派生/测量回执。任何缺值、缺回执或catalog digest不一致继续`blocked`。

因此22降到3不是放松门，而是把“需要讨论的科学选择”和“机器必须计算并证明的依赖量”分开。

## 5. 反复运行的固定流程

```text
P0 声明任务身份：论文数值复现 / FactorLab适配 / 消融
P1 加载参数目录，禁止读取类默认值作为权威
P2 冻结数据、时间、目标和证据边界
P3 计算r_eff、episode、n_eff、残差SNR、梯度和硬件测量
P4 先裁决三个根自由度，再按依赖图自动实例化其余19项
P5 输出自由度队列、全部22项值和证据receipt
P6 自由度门与实例化门同时通过后才训练
P7 训练后补签gate、算子、残差、损失—RankIC和上下文依赖证书
P8 未见挑战前只保留研究候选
```

每次新运行引用目录digest和逐项决定receipt。重复第二、第三、第四次时，只重测随数据变化的量；论文固定项和已冻结项目政策不重新猜测。

## 6. 两道机器门

`author_numeric_replication`目前阻断36项。未取得作者实现细节前，只能声称公式级独立实现，不能声称作者数值复现。

`new_factorlab_neural_training`从22个表面阻断压缩为3个根阻断。裸catalog在没有根回执时保持`blocked`；当前H20数学路由回执已经使三个根的scope门通过，但逐次运行的22项实例化门仍为`blocked`。因此暂不得启动完整REAKA训练；透明锚定候选和既有checkpoint只可按封存合同重放，旧checkpoint不得续训。

## 7. 三个根是否随预测内容改变

会。三个根不是全项目永久常数，而是预测任务身份的数学函数：

```text
root_policy = f(target, horizon, cadence, input_rank, n_eff,
                episode_structure, operator_count, residual_SNR)
```

- 确定性容量根随目标、输入有效秩、训练前缀和有效样本变化；
- selector根只在`K>=2`且episode可识别时激活，并随K和状态可分性变化；
- denoiser根只在残差获得执行权时激活，并随交叉拟合残差SNR、尾部和条件可预测性变化。

这仍是数学责任，不需要用户逐参数决定。用户只负责改变或确认金融任务身份；机器一旦发现身份digest变化，必须自动废止受影响的根回执。

### 7.1 根路由的数学裁决

1. **确定性容量**：冻结嵌套`h/d={1,2,4}`家族，使用训练前缀、HAC不确定性和one-standard-error原则选择与最佳内部目标指标同带的最小模型。不是选历史收益峰值。
2. **Selector**：K1时`alpha_1=1`对任意正温度恒成立，因此温度严格不适用。K>=2时先归一logit尺度，再用二分法令中位选择熵等于`0.5 log K`，即有效算子数落在1与K的几何中点；梯度健康不通过则K家族不获执行权。
3. **Denoiser**：diffusion未获执行权时严格不适用。激活后只比较宽度`{d,2d,4d}`、深度`{1,2}`的嵌套条件MLP，选择交叉拟合diffusion loss处于最佳一个标准误内且不伤害排序指标的最小成员。

机器回执：[`reaka_prediction_root_routing@1.0.json`](reaka_prediction_root_routing@1.0.json)。

### 7.2 预测内容改变后的Stage回退状态机

| 改变内容 | 最早重开Stage | 原因 |
|---|---|---|
| 仅硬件、精度、求解器或训练前缀 | Stage5参数闭包 | 金融材料不变，只重算nuisance与容量 |
| latent、K、residual模式或根路由版本 | Stage5参数闭包 | 模型数学身份变化，Stage6必须从预检重启 |
| 因子×状态机制或multiplicity家族 | Stage4 | 配对和压缩结论失效 |
| 状态定义、采样步或episode口径 | Stage3 | 可观察性与K资格失效 |
| target、horizon、收益时钟、universe或输入因子身份 | Stage1/2；若冻结Stage2已含该目标则Stage3 | 因子效力、状态时间尺度和三个根都会变化 |
| 仅报告图表或不改变任何身份 | 不回退 | 科学计算图未变 |

回退只重开最早受影响Stage及其下游，不机械重跑更早的有效材料；旧checkpoint一律历史化，不从中续训。

### 7.3 当前H20任务裁决

当前预测内容、48因子、两个状态、H20时间坐标、全A股票池均未改变。本次变化只有`model.root_policy_version`，所以：

- Stage0—4保持有效，不重跑；
- 回到**Stage5参数闭包子阶段**，冻结三个数学路由并生成本轮22项实例化；
- 然后从**Stage6神经参数校准预检**重新开始，不接续旧checkpoint；
- 当前K1使selector根不适用，diffusion未授权使denoiser根不适用；实际活跃根只有确定性容量家族；
- Stage7继续关闭。

当前状态回执：[`current_stage_status.json`](evidence/reaka_prediction_root_routing_v1_20260825/current_stage_status.json)。

## 8. 白皮书必须具备的“金融意图编译能力”

合格白皮书不能只解释参数，也不能把一张未决清单交给下一位AI。它必须把用户锁定的金融意图编译为完整数学合同：

```text
用户金融输入
  target / horizon / cadence / universe / factor / state / execution
        ↓
预测身份digest与最早Stage回退
        ↓
三个根的激活、失活和数学路由
        ↓
22项显式值或有界校准算法
        ↓
无后见的trial矩阵、证据清单与失败关闭门
```

验收标准固定为：

1. 黑箱输入只含金融意图，不允许输入hidden size、temperature、optimizer、learning rate或epoch；
2. 输出必须覆盖22/22项，`user_math_inputs_required=[]`；
3. 每个结果必须是公式值、产品值、条件函数、测量算法或显式不适用，不得读取类默认值；
4. 所有校准trial在结果前冻结并计入multiplicity，外层年份不得选参；
5. 必须同时输出最早Stage回退和下一合法动作；
6. 任何缺项、未知依赖、digest漂移或仍向用户询问数学数字均fail closed。

### 8.1 快速能力验证与修复

首轮黑箱验证发现旧白皮书只能完成根路由，不能自动生成22项Stage6校准实例，`run_instantiation=blocked`；按本节标准判定不合格。现已补充金融意图编译器并再次验证：

- 编译参数：22/22；
- 用户数学问题：0；
- 当前活跃容量候选：`h={8,16,32}`；
- 学习率候选：`{1e-4,3e-4,1e-3}`；
- 结果前冻结校准trial：9个；
- K1下selector严格不适用；diffusion未授权下denoiser严格不适用；
- 能力验证：`passed`。

机器合同：[`reaka_stage5_parameter_compilation@1.0.json`](reaka_stage5_parameter_compilation@1.0.json)。

能力证书：[`whitepaper_capability_validation.json`](evidence/reaka_stage5_parameter_compilation_v1_20260825/whitepaper_capability_validation.json)。

### 8.2 当前Stage5执行结果

当前H20 Stage5已完成`stage5_parameter_calibration_contract_frozen`。Stage0—4继续有效，旧Stage6 checkpoint只保留历史身份。下一合法动作是Stage6参数校准预检；9个trial用于产生学习率、梯度、容量、DMD初始化和覆盖收敛回执，不得提前解释为正式模型比较。完整Stage6训练、K2、diffusion和Stage7仍未开放。

Stage5封存：[`stage5_closeout.json`](evidence/reaka_stage5_parameter_compilation_v1_20260825/stage5_closeout.json)。

## 9. 数值范围右删失状态机

参数编译器不仅要给出候选值，还必须处理“所有已测值都健康、稳定边界在网格之外”的情况。右删失只说明数值范围不足，不说明模型无效、策略无增量或应该选择网格上界。

### 9.1 唯一健康谓词

同一数值参数在screening、边界probe和正式preflight中必须使用同一个健康谓词：

```text
health = finite(loss, gradient, parameter, DMD)
         AND endpoint_loss < fixed_pre_loss
         AND loss_slope_on_true_cycle_axis < 0
         AND no_sustained_explosion
         AND update_parameter_ratio_auditable
```

`fixed_pre_loss`必须在DMD注入、optimizer重置之后、任何joint optimizer step之前测量。probe至少2个完整cycle；当前合同固定4个。禁止另造删除其中某一条件的`numerical_health`、`smoke_health`或其他弱布尔来改变科学路由。

### 9.2 顺序边界规则

当预注册上界仍健康：

1. 当前Stage6立即停止，不选上界；
2. 只有主控验收可确认right-censored；外部执行器只能写`pending_controller_acceptance`；
3. 回Stage5新版本，沿结果前冻结的对数尺度顺序探针向外扩展；
4. 每个探针不生成验证期预测，不进入科学候选分母；
5. 遇到首个不健康点，选择前一个已验收健康值；
6. 全部新探针仍健康则再次right-censored并失败关闭，不得在同一运行中继续扩网格。

装配顺序以状态—因子手册为准，不是以9格选参为准：透明核心 → 零残差神经保真 → Koopman容量 → 残差由简到繁。论文latent公式`R=Z_next-KsZ`已确认可落地，但这只是身份探针，不是步骤8授权。当前不得派hidden×lr筛选或confirmation。diffusion仍关闭。

### 9.3 科学候选与数值探针分账

- hidden `{8,16,32}`仍是3个科学容量候选；
- 学习率边界探针是optimizer nuisance测量，不是策略/容量候选；
- numerical probe进入execution-attempt账，不增加科学candidate denominator；
- 2017/2018预测对边界probe严格禁止；
- 每个hidden必须先有唯一可辨识学习率，才进入confirmation。`h32@0.1`受限confirmation已验收并塌成透明主干身份，科学状态是无增量继任；原三hidden×三seed confirmation仍关闭，formal fit仍关闭，外部执行未授权。

### 9.4 证据与权限

- 每个attempt绑定可恢复源码Git blob、合同、input/cache和环境；
- validator验证当前字节或历史Git blob，合法源码修订不得让封存执行失去可恢复性；
- attempt count以最终ledger为准，运行中的自指快照只作过程字段；
- 外部AI禁止创建`controller_acceptance`或关闭主控任务；
- right-censored时`formal_fit_gate_ready=false`、Stage7关闭。


### 9.5 精度不可辨识

两次打回不是执行失败，而是合同缺口：

1. 右删失状态机只处理“全健康”，没有处理“float32健康、AMP爆炸”；
2. 无scaler的fp16 Adam被当成科学精度；
3. `no_sustained_explosion` 原先用`gradient_max<1e6`，放过高学习率瞬态。

现行规则：

```text
authoritative_precision = float32
amp_float16 = implementation_parity_probe_only
if float32_health != amp_health:
    status = precision_nonidentifiability
    selected = null
    do_not_label_stable
    do_not_label_first_unstable
    do_not_select_previous_healthy
    stop_current_stage6
```

### 9.6 参数身份门与因子效力门必须分开

Stage5不是因子有效性检验。把“参数能不能点名”和“因子有没有增量”收成同一扇门，会让流程在选参里空转。

```text
GateA = nameable_parameter_identity
        能点名 hidden × learning_rate × coverage
        不要求它是容量赢家
        不要求它已经证明因子有效

GateB = non_baseline_incremental_identity
        被点名的身份必须是非主干K1残差
        gamma=0 或 RankIC等于透明主干 => GateB失败
        GateB失败不是参数编译失败，也不是执行失败

因子效力 = 不在Stage5
        只有GateA和GateB同时通过，才能进入后续效力/formal-fit讨论
        GateB失败后禁止再派同一参数家族的Stage5/Stage6探针

论文残差与项目残差不是同一身份：
        paper: R = Z_next - Ks Z ，可正可负，加在 latent 下一步
                Z_tilde_next = Ks Z + R_hat
        project: score = 1 * baseline + gamma * orth(K1, baseline)
                gamma clip 到 [0, 0.25]，gamma<=0 精确退回主干
        二者不得互相冒名。GateB失败只关闭项目分数残差，不自动授权 diffusion。
        下一合法动作是 Stage5 参数闭包重开 paper latent K1 residual，不是再选 lr/hidden。
```

2026-08-26 继任审计更正：上述 GateA 定义本身保留，但历史证据没有通过它。`hidden_selected=false`与“能点名 hidden×learning_rate×coverage 参数身份”不能同时成立。`h32@0.1@coverage=4` 只能重新标记为 `restricted_solver_probe_tuple_observed_parameter_identity_not_closed`。相应地，`gamma=0` 只关闭本次受限的项目分数层非负残差家族，不是全部非主干身份或因子效力的 GateB 实证。旧 `@1.0` 合同不改写，由继任审计合同降级其当前权威。

当前H20证据：

- GateA：`passed_restricted_family_only`，唯一可点名配对是`h32@0.1@coverage=4`，`hidden_selected=false`
- GateB：`failed_collapsed_to_transparent_baseline`，因为`gamma=0`
- 因子效力：未授权
- 同类探针：未授权
- 下一合法动作：Stage5参数闭包，冻结论文latent残差身份；diffusion仍关闭

历史两扇门只读：[`reaka_stage5_identity_factor_gates@1.0.json`](reaka_stage5_identity_factor_gates@1.0.json)。

当前机器合同：[`reaka_stage5_residual_identity@1.0.json`](reaka_stage5_residual_identity@1.0.json)。

机器合同：[`reaka_stage5_lr_boundary@1.2.json`](reaka_stage5_lr_boundary@1.2.json)。

历史v1.0合同只读：[`reaka_stage5_lr_boundary@1.0.json`](reaka_stage5_lr_boundary@1.0.json)。

当前机器合同：[`reaka_stage5_lr_boundary@1.1.json`](reaka_stage5_lr_boundary@1.1.json)。

Stage5 v1.1封存：[`stage5_closeout.json`](evidence/reaka_stage5_lr_boundary_v1_1_20260825/stage5_closeout.json)。

V2.1执行封存：[`controller_handoff.md`](evidence/reaka_stage6_lr_boundary_v21_20260825/controller_handoff.md)。

V2.1主控验收：[`controller_acceptance.md`](evidence/reaka_stage6_lr_boundary_v21_controller_acceptance_v1_20260825/controller_acceptance.md)。

V2.2执行封存：[`controller_handoff.md`](evidence/reaka_stage6_lr_boundary_v22_20260825/controller_handoff.md)。

V2.2主控验收：[`controller_acceptance.md`](evidence/reaka_stage6_lr_boundary_v22_controller_acceptance_v1_20260825/controller_acceptance.md)。

V2.3执行封存：[`controller_handoff.md`](evidence/reaka_stage6_lr_boundary_v23_20260825/controller_handoff.md)。

V2.3主控验收：[`controller_acceptance.md`](evidence/reaka_stage6_lr_boundary_v23_controller_acceptance_v1_20260825/controller_acceptance.md)。

当前机器合同：[`reaka_stage5_lr_boundary@1.2.json`](reaka_stage5_lr_boundary@1.2.json)。

Stage5 v1.2封存：[`stage5_closeout.json`](evidence/reaka_stage5_lr_boundary_v1_2_20260825/stage5_closeout.json)。

当前机器合同：[`reaka_stage5_lr_boundary@1.3.json`](reaka_stage5_lr_boundary@1.3.json)。

Stage5 v1.3封存：[`stage5_closeout.json`](evidence/reaka_stage5_lr_boundary_v1_3_20260825/stage5_closeout.json)。

历史联合合同只读：[`reaka_stage5_capacity_lr_joint@1.0.json`](reaka_stage5_capacity_lr_joint@1.0.json)。

联合合同封存：[`stage5_closeout.json`](evidence/reaka_stage5_capacity_lr_joint_v1_20260825/stage5_closeout.json)。

受限confirmation执行封存：[`controller_handoff.md`](evidence/reaka_stage6_restricted_confirmation_h32_lr0p1_20260825/controller_handoff.md)。

受限confirmation主控验收：[`controller_acceptance.md`](evidence/reaka_stage6_restricted_confirmation_h32_lr0p1_controller_acceptance_v1_20260825/controller_acceptance.md)。测量通过，hidden未选中，formal fit关闭。

历史透明主干身份封存只读：[`reaka_stage5_baseline_identity_closeout@1.0.json`](reaka_stage5_baseline_identity_closeout@1.0.json)。

透明主干身份封存：[`stage5_closeout.json`](evidence/reaka_stage5_baseline_identity_closeout_v1_20260826/stage5_closeout.json)。

历史无增量继任只读：[`reaka_stage5_no_incremental_successor@1.0.json`](reaka_stage5_no_incremental_successor@1.0.json)。

无增量继任封存：[`stage5_closeout.json`](evidence/reaka_stage5_no_incremental_successor_v1_20260826/stage5_closeout.json)。

历史两扇门只读：[`reaka_stage5_identity_factor_gates@1.0.json`](reaka_stage5_identity_factor_gates@1.0.json)。

两扇门封存：[`stage5_closeout.json`](evidence/reaka_stage5_identity_factor_gates_v1_20260826/stage5_closeout.json)。

历史残差身份只读：[`reaka_stage5_residual_identity@1.0.json`](reaka_stage5_residual_identity@1.0.json)。

残差身份封存：[`stage5_closeout.json`](evidence/reaka_stage5_residual_identity_v1_20260826/stage5_closeout.json)。

当前机器合同：[`reaka_stage5_parameter_compilation@1.1.json`](reaka_stage5_parameter_compilation@1.1.json)。

论文latent K1残差封存：[`stage5_closeout.json`](evidence/reaka_stage5_paper_latent_k1_residual_v1_20260826/stage5_closeout.json)。
