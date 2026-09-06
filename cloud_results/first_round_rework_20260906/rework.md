# 第一轮补件：原字节验收通过，返工推进至 R2 来源复核

本次在数据提交 `2575f9e4d12289fa3916d14f27cb637908614fd9` 上实际运行验收。用户点名的六项输入和旧账本合同已经恢复；六份 checkpoint 的物理张量与拟合/映射清单声明一致。**先前“六项输入未交付”的阻断已解除，不需要重复上传这些文件。**

继续返工时，停在 R2：金融残差构造及历史时点可得性（PIT）的上游证据没有交付。现有结果不能独立证明系数在正确时点冻结、因子状态在决策时已可得、成交输入来自正确的盘中时钟。按用户“数据卡住即停”的要求，没有越过此处开始训练或账户重放。

## 已完成的验收

| 对象 | 实际检查 | 结果 |
|---|---|---|
| 14:30/14:45 六项原输入 | 对照之前已记录的原文件 SHA-256；两个市场面板由分片还原后再校验整体 | 6/6 匹配 |
| 旧账本合同 @1.5 | 重算 canonical digest，并与旧 current 指针的预期摘要比较 | 匹配 `sha256:b2a7b150…` |
| 两个 K1 输入仓 | 各 15 个 manifest 引用文件的摘要、数组/日期/坐标、历史序列有限值和标签索引 | 各 853,732 条推断坐标，827,753 条有标签，25,979 条无标签仍保留 |
| 模型实体 | 两时钟 × seed 11/29/47；逐一校验所有 174 个张量文件，再以名称、dtype、shape、数组字节重算 state digest | 六份匹配；算子形状均为 `[1,8,8]` |
| 拟合/映射声明绑定 | normalizer 原文件、固定配置、checkpoint manifest 与 formal state digest、按训练前缀损失选周期的记录、冻结 review score 摘要 | 声明和物理文件一致；未重算分数生成过程 |
| 分数与市场面板 | 坐标唯一、日期/时钟正确、分数有限，与输入推断支持对应，市场覆盖全部分数坐标 | 各 853,732 条分数、6,459,216 条市场记录；无缺失连接 |
| 2023/2024 日线 | 24 个分片分别对照 data manifest 的摘要，检查所有分区日期 | 24/24 匹配；此前日线缺口解除 |
| 历史源码声明 | 127 个来源声明按原摘要核对；仅通过显式映射使用同摘要归档副本 | 117 匹配，8 缺失，2 漂移 |

共还原 14 个分片原文件；只在临时目录写入还原文件，上传分片和封存文件保持原样。完整数值及逐文件摘要见 [upload_audit.json](upload_audit.json)。这是原字节及内部身份/结构验收，不是金融效力重验，也没有证明真实历史拟合过程完全可复现。

## 必要返工的当前进度

| 步骤 | 本次处理 | 当前状态 |
|---|---|---|
| R0：金融对象与证据解释 | 进一步纠正拟合目标描述：fit-prefix 代码对历史 epsilon 序列做模型训练；`epsilon_future` 在 review 时作标签。r0 关闭潜动力残差网络，不表示没有使用或预测金融残差 | 文档裁决完成 |
| R1：冻结输入和模型身份 | 补齐并核验原字节、六份模型实体及声明链；如实保留历史来源未闭合的范围 | 交付字节通过；不宣称完整重现历史拟合 |
| R2：金融 epsilon 算术、系数冻结、因子状态及成交时钟 | 沿输入构造器追到 P6.1/P6.2 原始来源 | **数据/来源阻断，等待补件** |
| R3：因子/容量/残差证据再裁决 | 必须先确定 R2 是否改变被预测对象和有效支持；不因旧 K2/MLP/DDPM 问题自动重训当前 K1 | 未越过阻断执行 |
| R4：账户与归因 | 原分数验收通过，暂不重算；旧账户两个源码无法恢复的问题单独登记，待 R2 后决定独立验算或后继重放 | 未越过阻断执行 |

现任模型已经利用金融 epsilon 的历史信息。后续讨论“开发个股残差”时，需明确是改变金融残差预测，还是增加潜动力残差修正，不能把二者混同。当前证据不要求自动选 K2、启用残差网络，也不保证任何因子或残差必有正增益。

## R2 的具体缺件

只需与这条冻结策略有关的有界原始来源，不要求整套 DataHub 湖或 isolated 重复树。机器清单及预期摘要见 [recovery_request.json](recovery_request.json)。

1. **P6.1 原 target/fill 包**：`output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020/formal/` 下的原 manifest 及其指向的 calendar、symbols、decision positions、`entry_open_1430.npy` / `entry_open_1445.npy`，以及验证原观测/成交时钟所需的有界来源。对应旧回执记录的 manifest 摘要为 `sha256:82f57a1a…`；原入口价格数组的预期摘要亦已恢复。当前市场表只有日期和决策时钟标签，无法单独追证实际取价时刻。
2. **P6.2 两时钟 OT1/OT2/OT3 包**：`output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020/formal/{1430,1445}/` 的原合同、manifest、物化源码，以及 `ot1/stock_residual_surfaces.npz`、`ot1/d5_stock_exposures.parquet`、`ot1/d5_stock_industry_exposures.parquet`、`ot2/selected_factor_states.parquet` 和验证其生成所必需的依赖。需追证收益区间/复权口径、截距与 beta 的拟合窗口和冻结时点、cross-fit 成员、因子状态可得时间、历史/未来标签成熟时间。六个 formal manifest 的预期摘要已原样列入机器清单；根目录从已交付旧源码和合同恢复，并非猜测。
3. **8 个已声明却仍缺失的源码/测试文件**：P6.3 preflight 工作流文档、freeze/materialize/run/validate/close 五个脚本、preflight 测试，以及 fit-prefix successor 测试。完整路径和原摘要在机器清单中。此外，代码引用但未交付的 `reaka_intraday_target_fill_v1.py`、`reaka_intraday_orthogonal_ot_v1.py`、`reaka_intraday_k1_clock_attribution_v1.py` 也已登记，分别属于这两层上游来源和旧拟合诊断。

两份已明确找不到原 blob 的旧账户源码继续保留为历史可复现性缺口，不要求伪造或重新封存旧摘要。交付的 DataHub repair validation reports 已按映射验收，但报告副本不能代替上述输入的 PIT 来源。

## 验证与交接边界

[Actions 34009032502](https://github.com/staryocean0/factorlab-multifactor-stock-lab/actions/runs/34009032502) 已完成原字节验收，报告 `delivered_byte_acceptance=passed`、`errors=[]`。退出码 **2** 是对 R2 来源阻断的明确表达，工作流因此显示失败；它不表示文件验收失败或策略亏损。该次新增的 11 项损坏分片/路径越界/伪造模型状态反例测试均执行通过。

V1.3 的 146 份现行来源检查仍通过。代码提交 `d673615…` 的分支 CI 已执行 291 项测试，零失败、零错误、零跳过。首次 PR 合并快照因新增历史测试导入 `scripts` 时缺少根目录而发生 3 个收集错误，后继修复使用仅在 pytest 收集阶段加载的 `tests/conftest.py`。中间尝试修改 `pyproject.toml` 被原字节门拒绝，已恢复其原字节，没有重封 V1.3 摘要。后续合并检查的精确结果登记于 [validation_receipt.json](validation_receipt.json)。原失败回执保留，未冒充通过。

修复后的最终分支检查 [Actions 34009445599](https://github.com/staryocean0/factorlab-multifactor-stock-lab/actions/runs/34009445599) 仍为 **291 项通过、零跳过**。包含新上传历史源码的 PR 合并快照 `c4856c22055ebbc1335219a3e263e994011176e8` 的 146 份现行来源检查通过，但完整测试收集在缺失的 P6.1 模块 `reaka_intraday_target_fill_v1.py` 处停止（[Actions 34009447904](https://github.com/staryocean0/factorlab-multifactor-stock-lab/actions/runs/34009447904)）。这与 R2 的上游来源缺口相符。没有跳过旧测试、伪造模块或把该合并检查写为通过。

没有拟合新模型、重算冻结分数、选择 K、重放账户、签署金融验收或修改本地 FactorLab 指针。所有已消费区间仍为 `fresh_oos=false`。PR 未合并。补件后从 R2 恢复，先判定有无实际方法/时钟缺陷，再决定最小必要重算范围。
