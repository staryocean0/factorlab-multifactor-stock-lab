# 第一轮策略开发的必要返工：已完成口径复核，停在原始输入闭包

本次按用户要求使用新的 V1.3 基础设施，只返工受已确认缺陷影响的步骤；遇到数据阻断后停止，不另选更早年份、代理数据或其他模型继续试验。此记录属于返工证据，不建立新的现行数学合同，不覆盖原策略或旧验收结果。

**本次实际完成的是第一轮对象、证据用途与返工范围的文档裁决。第一个数值复核步骤尚未能执行：原始盘中输入和冻结合同没有随包交付。** 不能将这次元数据复核写成第一轮策略已经重新验证。

## 已完成的必要口径返工

| 项目 | 本次处理 | 重算裁决 |
|---|---|---|
| 金融产品及市场、大小盘、行业三个因子方向 | 保留既有主动多头选股目标和候选因子身份；没有把产品改为强制中性 | 不因本次审计从零重做因子定义；其效力仍须有原始证据 |
| 第一轮当前模型 | 原 current、result、execution receipt 的身份互相绑定，均指向 `d8-h8-K1-r0_fit_prefix_successor_incumbent` | 保留为待核验的旧模型身份；不拿旧 d8-K2 机会账替换它 |
| r0 的含义 | 指未启用潜动力残差修正网络；不等于未使用或预测金融收益残差 | 修正解释，不因 r0 名称或其他残差分支失败而自动重训 K1 |
| 实际收益目标 | 已交付 K1 构造器的 `assemble_inputs` 读取 `epsilon_history`，`assemble_batch` 目标读取 `epsilon_future`；原回执也列出这些前缀字段 | 必须恢复原输入/拟合清单，确认它们如何与冻结 checkpoint 绑定；当前不能声称已核验实际 checkpoint 的目标 |
| 因子效力 | 已实现归因和入选股票的平均收益为正，均不能单独证明增量预测或独立 alpha | 只对受估计对象、时钟或身份问题影响的证据重新裁决；不先假定所有因子都失败 |
| K 与潜残差 | 不把旧 MLP/DDPM 的幅度或 teacher-forced 验收问题自动传递成 K1-r0 失败 | 原证据齐全后先重新裁决；确有必要才重算受影响候选及下游，不保证必须选 K2 或启用残差 |
| 第二轮 CloudRidge 条件配对 | 属于新增条件的第二轮工作；旧重复月仍不合格 | 不将第二轮 Stage3/4 全部重跑列为第一轮返工前置；归因衍生表后续仍需按组件来源修复 |
| 账户与归因 | 原分数/账户身份不变且来源可核验时，优先复用冻结分数与账户快照 | 只需改汇总口径时不重训、不重放账户；上游预测内容改变时才使受影响下游失效 |

以上没有替任何因素签署“重新验证通过”，也没有把缺证判成策略失败。

## 当前停点 R1

恢复位置：**原始输入、冻结合同与模型绑定复核**。不能跳过这个步骤直接重训，或仅凭结果文件中的 `passed` 继续。

锁定的 GitHub main 快照为 `bff98222398d87391b405e03fcca9dbbfdc2894f`，完整 tree 为 `20d3f18ec2b3ef406817176ca515e9c42cdccec0`。该快照包含 2023 年 1—8 月日线，缺 9—12 月和 2024 全年；这些是用户正在推送的已知缺口。本记录不宣告后续上传状态。

**更早的阻断独立于这 16 个月日线。** 第一轮 `execution_receipt.json` 明确引用但该完整远端 tree 不包含以下 6 个输入：

| 类别 | 缺失路径 |
|---|---|
| 14:30 原始输入清单 | `output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020/formal/1430/manifest.json` |
| 14:45 原始输入清单 | `output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020/formal/1445/manifest.json` |
| 14:30 冻结分数 | `output/factor-rotation/reaka_intraday_portfolio_mapping_inputs_v2_2011_2020/formal/bounded_score_panel_1430.parquet` |
| 14:45 冻结分数 | `output/factor-rotation/reaka_intraday_portfolio_mapping_inputs_v2_2011_2020/formal/bounded_score_panel_1445.parquet` |
| 14:30 原市场面板 | `output/factor-rotation/reaka_intraday_portfolio_mapping_inputs_v2_2011_2020/formal/daily_market_panel_1430.parquet` |
| 14:45 原市场面板 | `output/factor-rotation/reaka_intraday_portfolio_mapping_inputs_v2_2011_2020/formal/daily_market_panel_1445.parquet` |

此外，当前旧账本指针引用的 `docs/ops/reaka_current_k1_account_ledgers@1.5.json` 没有交付；所需 canonical digest 为 `sha256:b2a7b1509fc64303ee7c72aac90db2b4f1e3a386b70b27f18c5a42e681c227b7`。原拟合清单、冻结配置及其链接的 checkpoint 也尚不能由所交付回执定位并核验；一个模型名称或 model-or-score digest 不等于模型文件已经交付。

完整逐文件清单及旧回执记录的预期摘要在 [rework_result.json](rework_result.json) 的 `required_initial_input_inventory`、`required_ledger_contract` 和 `missing_recorded_source_closure`。这是一份初始恢复清单，不承诺补齐六个文件后就再无依赖：还需沿原清单查验其实际引用。

恢复原字节时应匹配预期摘要。若只能重建，应另行登记可因果复现的后继身份，不能覆盖旧摘要。15:00 日线不能替代 14:30/14:45 的决策时信息或真实成交输入；仅缩短到 2022 年以前也不能补出未交付的 2009—2020 输入。

## 已执行检查与未执行范围

- V1.3 现行基础设施检查通过，146 份来源摘要一致；沿用已验证实现，没有改动其来源文件，也没有重复运行全部模型测试。
- 读取了完整 GitHub 目录快照及旧元数据，校验旧 current、result、execution receipt 的 canonical digest 和结果身份绑定。
- 对原回执的 6 个输入逐一核对远端路径存在性，全部缺失；这是远端缺失，不是本地未下载造成的误报。
- 没有下载行情、读取 2026 行情行、拟合模型、选择容量、生成新经济结果或运行账户；原数据、原报告、封存摘要未改写。

复现本次冻结快照下的检查：

```bash
python cloud_results/first_round_rework_20260905/replay_readonly.py
```

实际退出码为 **2：输入/合同缺失而阻断**，不是执行异常，也不是策略失败。脚本只复现本次保存的远端快照；后续文件到位后必须先取得新的远端 tree，不能拿旧快照判断最新上传状态。

用户已授权“必要的第一轮返工”，不需再次请求笼统授权。本次遵照“遇到数据卡住就停”的要求，在 R1 等待所需输入与模型来源到位。恢复后从 R1 继续，按实际缺陷决定需要重新计算的步骤；任何执行合同应绑定真实输入、任务、版本及证据范围。2018—2025 仍为已消耗比较，`fresh_oos=false`；不开放生产或更改用户本地 FactorLab 指针。
