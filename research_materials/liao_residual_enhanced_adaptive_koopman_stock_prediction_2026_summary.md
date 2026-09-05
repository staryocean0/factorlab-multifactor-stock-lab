# Residual-Enhanced Adaptive Koopman Autoencoder：正式全文精读卡与 FactorLab 架构裁决

> 证据状态：`licensed_publisher_full_text_reviewed`
>
> 全文复核日期：2026-08-09
>
> 责任台账：`bd://fl-y117d`（承接 `bd://fl-jzxqw`）
>
> 权限边界：`full_text_obtained=true`、`reproduction_completed=false`、`production_authority=false`

## 1. 书目信息与文件边界

- 题名：*Residual-Enhanced Adaptive Koopman Autoencoder: A Deep Latent Dynamics Model for Stock Prediction*
- 作者：Lei Liao、Yang Zhang、Jun Wang、Jinghua Tan、Yinchao Liao
- 载体：ICASSP 2026，页码 2696–2700，共 5 页
- DOI：[10.1109/ICASSP55912.2026.11465125](https://doi.org/10.1109/ICASSP55912.2026.11465125)
- IEEE 文档号：[11465125](https://ieeexplore.ieee.org/document/11465125/)
- 项目保存件：[`liao_residual_enhanced_adaptive_koopman_stock_prediction_2026.pdf`](liao_residual_enhanced_adaptive_koopman_stock_prediction_2026.pdf)
- 文件 SHA-256：`e47b342414508a2d1ab7859c6e6a7df1ceb99141e0561a3598e866645f14d21e`

保存件是 IEEE Xplore 出版者排版全文，不是摘要页。页脚显示它于 2026-08-09 通过清华大学授权下载，并带有使用限制；因此项目只作内部研究保存，不把它标记为开放获取，也不提供对外公开分发权限。

本卡已经逐页复核方法、数据切分、三张结果表、投资模拟、结论和参考文献。论文没有公开的代码、完整超参数、交易成本或严格 PIT 审计；这些缺口不能被正式全文身份自动补齐。

## 2. 论文到底做了什么

REAKA 是一个端到端的下一期股票收益预测模型，不是宏观状态资产配置框架，也不是完整的多因子治理体系。它把股票收益和辅助特征编码到潜在空间，用可切换的局部线性动力推进状态，再用扩散模型补偿线性动力未解释的残差。

```text
历史收益 y + Alpha158 特征 x
  -> 双路 LSTM encoder
  -> gate 融合得到 latent Z
  -> Adaptive Koopman Selector 从 {K1, ..., KN} 选择/混合 Ks
  -> Z_hat_next = Ks Z
  -> conditional diffusion 生成 latent residual R_hat
  -> Z_tilde_next = Z_hat_next + R_hat
  -> decoder
  -> 下一期收益预测与股票排序
```

这一结构直接对应论文的两个核心判断：金融市场存在会切换的动力机制；有限维 Koopman 线性化留下的残差不是白噪声，而可能含有状态相关的冲击和高阶非线性。

## 3. 页码级方法复核

### 3.1 双路潜在状态编码（论文第 2697 页）

- 历史收益序列被拆为重叠的 `y[1:T-1]` 与 `y[2:T]`；LSTM 的逐时点输出形成隐式 delay embedding。
- 第二个 LSTM 同样编码股票辅助特征 `x`。
- `GateNet(Hx)` 是 MLP + sigmoid，逐元素融合收益表征 `Hy` 和特征表征 `Hx`：`Z = Hy * G + Hx * (1-G)`。
- 论文因此不是只对价格做 Koopman 分解；Alpha158 特征直接进入状态表征。

### 3.2 自适应多 Koopman 选择器（第 2697–2698 页）

- 候选算子构成可学习 codebook `{K1, K2, ..., KN}`。
- `SelectorNet(Z, Hy)` 使用单层 MLP + LeakyReLU 产生匹配分数。
- 训练时用 Gumbel-Softmax 得到可微的近似 one-hot 权重，并形成软混合算子 `Ks = sum(alpha_i * Ki)`。
- 推理时公式明确使用 `argmax SelectorNet(Z, Hy)` 选取算子，再计算 `Z_hat_next = Ks Z`。

这确认了此前公开材料无法确定的两点：训练采用 Gumbel-Softmax；推理采用离散 argmax。论文仍未给出算子数量 `N`、温度日程、持续期约束、切换成本或跨折算子身份匹配方法。

### 3.3 动态残差修正器（第 2698 页）

- 潜在残差定义为 `R = Z_next - Z_hat_next`。
- 训练采用标准 DDPM 前向加噪与噪声预测目标，去噪网络以当前 latent `Z` 为条件。
- 推理从高斯噪声开始逐步反向去噪，生成 `R_hat`，再修正 Koopman 推进状态。
- 扩散模型的作用是学习条件残差分布，而不是把一个确定性 MLP 误称为不确定性模型。

### 3.4 损失与预测（第 2698 页）

全文给出的总损失是未注明额外权重的三项和：

```text
L_total = L_rec + L_koop + L_diff
```

其中分别约束历史/下一期重构、Koopman 一步一致性和扩散噪声预测。推理只使用历史收益与特征，最终以重构序列的最后一个元素作为下一期收益预测。

## 4. 实验与结果的精确证据

### 4.1 数据与切分（第 2698 页）

| 项目 | 论文设定 |
| --- | --- |
| 市场 | CSI 300、S&P 500 |
| 样本期 | 2010-01-01 至 2020-12-31 |
| 输入 | Qlib Alpha158，158 个技术特征 |
| 回看长度 | 10 个交易日 |
| 训练 | 2010-01-01 至 2017-12-31 |
| 验证 | 2018-01-01 至 2018-12-31 |
| 测试 | 2019-01-01 至 2020-12-31 |
| 对照 | LightGBM、LSTM、GRU、ALSTM、TCN、ADGATs、FactorVAE、MASTER |

这是单次固定 train/validation/test 切分，不是 nested walk-forward。论文没有披露退市/停牌/涨跌停处理、标签的精确收益期限、特征归一化时钟、随机种子重复、超参数搜索预算或前缀不变性。

### 4.2 排序预测结果（第 2699 页，Table 1）

| 市场 | 模型 | RankIC | RankICIR |
| --- | --- | ---: | ---: |
| CSI 300 | MASTER（最强对照） | 0.052 | 0.481 |
| CSI 300 | REAKA | **0.064** | **0.568** |
| S&P 500 | MASTER（最强对照） | 0.048 | 0.456 |
| S&P 500 | REAKA | **0.061** | **0.541** |

论文报告 REAKA 在两市场均领先全部八个对照。需要保留一个文本质量警告：第 2698 页的 RankICIR 定义式把分母再次排成 `mean(RankICt)`，而标准定义通常应使用波动率/标准差；项目复现时必须以代码或作者说明确认，不能机械继承该公式。

### 4.3 消融结果（第 2699 页，Table 2）

| 变体 | CSI 300 RankIC / RankICIR | S&P 500 RankIC / RankICIR | 能证明什么 |
| --- | --- | --- | --- |
| w/o AKS | 0.053 / 0.455 | 0.051 / 0.447 | 多算子自适应选择相对单算子有增量 |
| w/o DRC | 0.051 / 0.480 | 0.049 / 0.463 | 潜在残差修正有增量 |
| w/o GM | 0.045 / 0.421 | 0.044 / 0.419 | 收益/特征门控融合有增量 |
| autoencoder | 0.038 / 0.364 | 0.034 / 0.325 | Koopman 与 residual 组合不是纯 AE 等价物 |
| residual-MLP | 0.052 / 0.491 | 0.050 / 0.469 | 论文样本内，扩散 residual 优于 MLP residual |
| REAKA | **0.064 / 0.568** | **0.061 / 0.541** | 完整模型最好 |

这是 REAKA 最有价值的证据：两个核心模块都经过同表消融，而且方向在两个市场一致。但表中没有置信区间、跨随机种子分布或多重性校正，不能据此直接推断项目数据上的稳定增量。

### 4.4 投资模拟（第 2699 页，Table 3 与 Figure 4）

论文按预测分数选 Top 30：

| 市场 | 模型 | 年化收益 AR | Sharpe |
| --- | --- | ---: | ---: |
| CSI 300 | MASTER | 0.265 | 1.25 |
| CSI 300 | REAKA | **0.339** | **1.50** |
| S&P 500 | MASTER | 0.261 | 1.67 |
| S&P 500 | REAKA | **0.291** | **1.71** |

这些是正向结果，但论文没有披露调仓频率、交易成本、滑点、换手、容量、最大回撤、权重规则或 A 股可交易性约束。因此 `AR=33.9%` 不能被项目直接当作可复制的成本后收益承诺。

## 5. 全文支持与不支持的结论

### 高置信度证据

- REAKA 的确是“多 Koopman 算子 + 条件选择 + latent diffusion residual”的端到端股票预测实现。
- 训练时是 Gumbel-Softmax，推理时是 argmax 选算子。
- Alpha158、CSI 300 和 S&P 500 的固定测试结果均为正；AKS、DRC、门控和 diffusion-vs-MLP 均有消融。
- 论文直接做了 Top-30 投资模拟，而不只是报告预测误差。

### 仍然未知或未证明

- 所选 operator 是否可稳定解释为增长、通胀、信用、流动性或风险偏好状态；
- 算子身份、选择频率和 residual energy 是否在时间折之间稳定；
- 数据是否满足 FactorLab 的 first-release PIT、退市和可交易性合同；
- 收益在真实成本、容量和多随机种子下是否显著；
- 论文结果能否在 2021 年后的独立新鲜样本上维持；
- 模型是否优于本项目完整的“宏观 + 快状态 + 条件因子溢价”体系；该体系目前尚未完成同口径实证。

论文结论还明确把“加入宏观信号、建模跨资产依赖和不确定性估计”列为未来工作。这直接说明当前 REAKA 不能替代 FactorLab 已冻结的慢宏观层、跨因子经济语义和风险/组合层。

## 6. 与 FactorLab 当前框架逐层比较

| 层面 | FactorLab 冻结 V1 | REAKA 全文 | 裁决 |
| --- | --- | --- | --- |
| 目标 | 学习共享因子基线与宏观/快状态条件偏离 | 端到端预测下一期股票收益 | 可并行竞争，不是同一经济命题 |
| 慢宏观 | 带 `available_at` 的连续宏观机制向量 | 未使用；论文列为未来工作 | 不能替代 |
| 快状态 | 因果 HMM belief / Jump path，有持久性和回退语义 | latent 条件下选择 Koopman operator | 升格为高优先级挑战者，不能直接改名为宏观状态 |
| 因子 | 因子中台保存身份、方向、证据、用途和生命周期 | Alpha158 被视作模型特征 | 不能绕过因子/特征基础设施 |
| 非线性动力 | 当前主要是解释性状态 + 收缩条件溢价 | 自适应局部线性动力 + 分布式 residual 更先进 | 应模块化吸收 |
| 验证 | anchored/nested 时间折、SearchScope、DataUsage、PIT 和前缀不变性 | 单次固定切分，缺少成本和显著性细节 | 论文结果不能替代项目 OOS |
| 组合与交易 | 主动行业/市值、成本、容量、集中度、回退和授权分层 | Top 30；执行细节不足 | 保留现有组合与治理层 |
| 当前证据 | Round 3A 非财务影子赛支持适配挑战者临时领先；正式严格财务确认尚未跑 | 两市场固定切分报告明显正结果 | 项目代理已有同口径正证据，但实现不等于论文原模型，仍不能判整框架替代 |

## 7. 是否替代现有框架：最终裁决

**不适合全盘替代；适合把 REAKA 升格为最新版框架中的高优先级动力与直接排序挑战者。**

原因不是保守，而是层级不同：REAKA 是一个表现亮眼但验证信息不完整的预测器；FactorLab V1 是数据、因子、宏观状态、条件溢价、组合、回退和生产治理组成的投资系统。用预测器替换整套系统会丢掉论文根本没有覆盖的能力。

建议采用双通道公平竞争：

```text
DataHub 固定版本 + 因子/特征中台
  ├─ incumbent：慢宏观 + HMM/Jump + 共享因子基线 + 收缩条件偏离
  └─ challenger：REAKA
       ├─ operator 选择概率/身份 + residual energy -> 快状态诊断
       └─ next-return head -> 独立直接排序分数
             ↓
      同一 universe / target / fold / 成本 / 组合层公平比较
             ↓
      no-harm gate 后才决定模块替换或组合
```

这里允许直接排序头以盈利为目标，不要求把行业、市值等潜在暴露先中性化；但它必须与现有因子路线共享同一交易约束、成本和样本外门，不能靠另一套宽松口径获胜。

### 模块吸收优先级

| 优先级 | 模块 | 当前决定 |
| --- | --- | --- |
| P0 | 多 Koopman codebook、Gumbel 训练、argmax 推理 | 纳入正式研究挑战，直接对应“市场动力不同” |
| P0 | operator 占用、切换率、稳定性、residual energy | 作为快状态质量与 OOD 诊断，不直接下单 |
| P1 | REAKA 直接收益排序头 | 独立 `strategy_id` 与 incumbent 公平比赛 |
| P1 | 确定性 simple residual / residual-MLP | 作为扩散 residual 的必要低复杂度基线 |
| P2 | 条件 diffusion residual | 只有 adaptive-K 与简单 residual 在项目 OOS 通过后才启用 |
| 拒绝 | 用 REAKA 替换 DataHub、因子中台、慢宏观、组合和治理全栈 | 论文没有覆盖这些层，也没有足够验证证据 |

## 8. 项目复现与替换判定门

只有同时满足下列条件，REAKA 才能从“文献挑战者”进入局部替换裁决：

1. 先逐项复现论文固定切分，仅把它作为实现 sanity check，不冒充项目 OOS；
2. 每个 outer fold 独立训练 scaler、encoder、selector、operator、residual 和 decoder；
3. 追加未来数据后历史 latent、operator selection 和 prediction 前缀不变；
4. 固定比较简单时序、LightGBM、现有共享因子基线、HMM/Jump、fixed-K、adaptive-K、residual-MLP 与 diffusion residual；
5. 同时报告 RankIC、RankICIR 定义、成本后收益、换手、最大回撤、容量、覆盖偏差和多随机种子分布；
6. 审计 latent collapse、operator 抖动/置换、residual 吞噬主干、OOD 和状态不确定回退；
7. 输入必须通过 DataHub 与因子/特征中台的用途合同；严格个股 PIT 未就绪时不得声称完成 A 股个股复现；
8. 只有 challenger 在预注册独立样本上通过 no-harm gate，才允许替换对应的快状态或评分模块；整套框架替换需要另立更高层证据门。

## 9. 一句话结论

正式全文把 REAKA 从“有趣的文献启发”升级成“值得尽快实证的核心挑战者”，但它应挑战并可能替换当前框架的快状态/排序模块，而不是替换宏观、因子、组合和治理组成的整套投资框架。

## 10. FactorLab 实现审计与三层归因（2026-08-10）

回到全文逐模块对照后，当前 Round 3A 挑战者必须命名为“REAKA 启发的适配代理”，不能命名为完整复刻：

| 论文模块 | 当前状态 | 主要差距 |
|---|---|---|
| 收益/特征双路 LSTM + gate | 缺失 | 当前是因子+宏观通道的单 LSTM |
| adaptive Koopman selector | 适配 | 四算子、Gumbel 训练/argmax 推理已有，selector 只读 `Z` |
| conditional DDPM residual | 适配 | 分开训练，推理为确定性零初值路径，不是论文的联合随机反推 |
| decoder / next-return head | 适配 | 当前为特征重建 + 训练窗 ridge 排序头 |
| 联合损失端到端训练 | 缺失 | 当前主干损失与残差拟合分开 |
| Alpha158 10 交易日输入 | 适配 | 当前为 172 股级输入 + 6 宏观、6 个月序列 |

对当前同一已训练模型，共享排序分数可精确拆为因子编码底座 `(b+w'Z)`、自适应状态动力 `w'(KsZ-Z)` 和动态残差 `w'Rhat`。在 2021—2025 已消费考卷上，扣费年化多空路径为 `-0.72% → +5.76% → +5.55%`；消除状态/残差加入顺序的 Shapley 归因为因子 `-0.72%`、状态 `+6.15pp`、残差 `+0.13pp`。

因此，当前代理的主要经济收益来自状态动力与因子底座的交互，残差层整体贡献微弱。状态增益又高度集中于 2023 年，2021/2024 年为负，不能概括为每个市场状态都稳定增益。详细收益归因、年度表、机器合同和权限边界见 [`Round 3A REAKA 三层收益归因`](../../docs/ops/evidence/macro_regime_v1_vs_reaka_v1/round3a_reaka_layer_attribution_20260810/README.md)。论文双路门控、完整 selector/decoder、条件 DDPM 和联合损失的完整复刻由 `bd://fl-a7g56` 承接。
