# REAKA 论文公式版挑战者 V1 白皮书

> 策略族职责合同见[`REAKA 人类供给—模型学习职责白皮书`](reaka_human_model_authority_whitepaper.md)，论文留白怎样研究和装配见[`状态—因子联合研究与策略装配手册`](reaka_state_factor_joint_research_whitepaper.md)。本文只说明公式忠实 V1；带项目训练护栏的一次冻结版见[`最佳实践 V2 白皮书`](reaka_best_practice_v2_whitepaper.md)。

## 1. 冻结结论

`reaka_paper_formula_faithful_v1` 已经把 Liao 等人 ICASSP 2026 论文的主干计算图落成一个独立挑战者：收益/特征双路 LSTM、特征路控制的 gate、自适应 Koopman 算子选择、条件 DDPM 残差、return decoder，以及 `L_rec + L_koop + L_diff` 等权联合训练。历史代理 `reaka_adaptive_koopman_v1` 没有被改写，两者使用独立 `strategy_id` 和拟合状态。

这一版同时冻结两个必须分开的结论：

1. **公式架构完成**：论文明示的主干模块已经在同一训练图中连通，梯度能到达双 LSTM、gate、selector、operator codebook、denoiser 和 decoder。
2. **当前训练健康未通过**：FactorLab 月频适配诊断的扣费年化多空为 `-7.00%`，平均 Rank IC 为 `-0.0115`；还出现单算子完全垄断，残差吞噬、OOD 和完整收敛轨迹的证据不足。因此 `training_health_certified=false`，不允许替换旧代理或 incumbent。

用户决定的“后续开发方向以论文挑战者为主”已经冻结；但“研究方向”不等于“当前模型已证明更赚钱”。

## 2. 论文主干计算图

```text
(y1:T-1, x1:T-1)                  (y2:T, x2:T)
       |                                  |
 LSTM_y + LSTM_x                    LSTM_y + LSTM_x
       |                                  |
 G = GateNet(H_x)                         Z+
 Z = H_y ⊙ G + H_x ⊙ (1-G)             |
       |                                  |
 selector([Z, H_y]) --Gumbel/argmax--> K_s Z
       |                                  |
       +------------- R = Z+ - K_s Z -----+
                              |
                    conditional DDPM(R | Z)
                              |
                    Z~+ = K_s Z + R_hat
                              |
                       return decoder
                              |
                    最后一个输出 = 下期收益分数
```

训练期 selector 使用 soft Gumbel-Softmax 混合 codebook 中的多个算子；推理期使用 argmax 选择单个算子。残差扩散的逆过程从高斯噪声开始，不再使用旧代理的零起点；最终排序直接取 decoder 最后一个收益输出，不存在额外 Ridge 排序头。

## 3. exact、论文未说明与项目适配

| 层 | 归类 | V1 处理 |
|---|---|---|
| 双重叠时窗、双 LSTM、特征 gate | 论文公式明示 | 按公式实现 |
| selector 读取 `[Z,H_y]`、训练 Gumbel、推理 argmax | 论文公式明示 | 按公式实现 |
| `R=Z+ - K_sZ`、条件 DDPM、高斯反推 | 论文公式明示 | 按公式实现 |
| decoder 重建两窗并用末元素预测 | 论文公式明示 | 按公式实现 |
| `L_rec + L_koop + L_diff` | 论文公式明示 | 等权相加，端到端反传 |
| 潜空间维度、算子数、epoch、batch、optimizer | 论文未公开 | 在 `ReakaPaperConfig` 显式冻结，标为 assumption |
| Gumbel 温度/退火、DDPM 步数/日程 | 论文未公开 | 显式冻结，不冒充作者参数 |
| 训练期修正 latent 如何进 decoder | 论文未完整说明 | 用一步 `x0` 估计，显式标为 assumption |
| 日频 Alpha158 + 日收益 | 论文 benchmark | 当前项目诊断未复制；另立月频 adapter |

所以“公式忠实”指的是论文已公开计算图的忠实实现，不是作者代码的 bit-exact 复制，也不是论文数值复现。

## 4. 两个输入合同

### 4.1 论文 benchmark 合同

- 日频 Alpha158；
- 连续 10 个交易日窗口；
- 同步历史日收益路；
- CSI 300/S&P 500 按论文切分作数值 sanity。

当前 FactorLab/DataHub 还没有为该挑战者发布这张完整、独立、可重放的日频面，因此 V1 不声称完成论文 benchmark 复现。

### 4.2 FactorLab 月频适配合同

- 输入为 Round 3A 的 172 个股级非财务特征；
- 收益路只使用决策时刻前严格已可见的历史 20 交易日目标，固定滞后 2 个月期；
- 取 10 个月频观测组窗，不足、不可交易或尚未可见的窗口直接剔除，不补零；
- 慢宏观和 6 个上下文不进入论文核心，因为原文把宏观信号列为未来工作。

这个 adapter 只用于验证项目代码能否在真实数据面上跑完，不能隔空变成日频 Alpha158。

## 5. 首次真实诊断

| 指标 | 公式版 V1 |
|---|---:|
| 2021—2025 扣费年化多空 | -7.00% |
| 平均 Rank IC | -0.0115 |
| 多空 Sharpe | -1.489 |
| 多空最大回撤 | -34.01% |
| Top50 年化收益 | -2.80% |
| Top50 等权超额 | -4.19% |

该运行已在拟合前冻结一套参数，没有看到结果后回调。同配置在独立目录重放，`spec.json` 和 `diagnostic_result.json` 均字节一致。

旧论文启发代理在 Round 3A 的 `+5.55%` 仍是已封存的临时研究领先。公式版的 `-7.00%` 不是新科学票，因为 2021—2025 已被打开；它也不是与旧代理的严格论文级公平 battle，因为旧代理的输入路径、排序头和残差训练均不同。

## 6. 训练健康门

| 门 | 结果 | 证据 |
|---|---|---|
| 联合目标/公式路径 | 通过 | 15 个 fold×seed 收据均为等权联合损失、无后拟合残差、高斯反推、decoder 直接分数 |
| 双路 gate 不饱和 | 通过 | gate mean 范围 `0.4965—0.5241` |
| operator 多样性 | 失败 | 某个 fit 单算子占用率 `1.0`，超过 `<0.99` 操作健康门 |
| 残差不吞噬主动力 | 缺证据阻断 | 当次收据没有 `advanced_latent_energy`，不能计算比值 |
| OOD 输入 | 缺证据阻断 | 当次收据没有 `ood_fraction` |
| 收敛轨迹 | 缺证据阻断 | 只保留末 epoch，没有首末 loss 对照 |

末 epoch 的 reconstruction loss 约 `1.92—2.05`，diffusion loss 约 `0.98—1.00`；在归一化收益与标准高斯噪声下，它们仍接近素朴基线。这是“当前 fit 学得很弱”的证据；“epoch 太少”或“月频适配造成失败”只是合理假设，尚未被独立验证。

## 7. 台账和已消费考卷保护

公式版诊断追加为机器台账序号 16，健康阻断另行追加为序号 17，首次提交前的类型边界迁移以无市场重读 validation 追加为序号 18；`scientific_claim_count` 仍为 4。序号 18 确认序号 16/17 的结果文件摘要不变。项目台账现在还使用独立 `exam_scope_digest`，只按 target、action、universe、period 和 fold 识别已打开的考卷。即使换了模型、特征打包或 mechanism，也不能在同一考卷上新增一张科学票。

本轮永久为 `fresh_oos=false`、`scientific_vote_allowed=false`、`eligible_for_promotion_review=false`、`formal_replacement_allowed=false`、`production_authority=false`。

## 8. 代码和证据地图

| 用途 | 入口 |
|---|---|
| 公式模型、月频 adapter、单 fold 训练 | `src/factor_lab/factor_rotation/reaka_paper_v1.py` |
| 五年聚合诊断和 spec/result 验证 | `src/factor_lab/factor_rotation/reaka_paper_v1_runtime.py` |
| 训练健康 fail-closed 门 | `src/factor_lab/factor_rotation/reaka_paper_v1_health.py` |
| 首次提交前源码迁移验证 | `scripts/register_reaka_paper_v1_implementation_migration.py` |
| 固定运行器 | `scripts/run_macro_regime_dual_strategy_reaka_paper_v1.py` |
| 健康审计 | `scripts/audit_reaka_paper_v1_health.py` |
| 单测 | `tests/unit/test_reaka_paper_v1.py` |
| 实证包 | [`round3a_reaka_paper_v1_implementation_diagnostic_20260810/`](evidence/macro_regime_v1_vs_reaka_v1/round3a_reaka_paper_v1_implementation_diagnostic_20260810/) |

## 9. 下一次合法验证

后续责任项：`bd://fl-wtbm9`。

本节只管理论文日频 benchmark 与输入/训练健康线；当前策略状态—因子研发顺序由[`REAKA 状态—因子联合研究与策略装配手册`](reaka_state_factor_joint_research_whitepaper.md)管理，两条线不得互相冒名。

在继续挖因子之前，后续责任是先把论文输入与训练健康证据补齐：

1. 发布日频 Alpha158 和同步历史收益的独立、可重放输入面；
2. 在打开结果前冻结论文未公开超参数，不用 2021—2025 调参；
3. 强制记录首/末 epoch loss、latent/advanced/residual energy、OOD fraction、operator 占用和切换；
4. 先在未打开的开发面完成论文的 `w/o gate`、`w/o AKS`、`w/o DRC`、vanilla AE 和 residual-MLP 固定消融；
5. 只有所有健康门通过后，才能把冻结模型送入新鲜时间 lockbox 与 incumbent 做正式 battle。

这五步之前，不因为当前负结果而改 epoch、seed、算子数或扩散步数；那会把已消费的考卷变成调参集。
