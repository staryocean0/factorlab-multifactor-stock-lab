# REAKA V2 Stage3 可观测条件支持白皮书

## 目的

本阶段只关闭用户输入的 `S_obs`：上一自然月 CloudRidge 1σ 趋势条件。它回答该条件是否满足 PIT、有哪些 episode、怎样转移、持续多久，以及时间样本与股票截面支持分别有多少。它不决定 `K_i`、`N_max` 或 `N_effective`。

## 数据处理

V1 已经生成并通过双树验证的四个原始测量文件保持不变：`state_months.csv`、`state_episodes.csv`、`state_support.csv`、`transition_counts.csv`。当前 authority correction 只保留这些文件的 `S_obs` 描述权，撤销旧 certificate 和 result 的 operator 推论。

Stage3 V2 不重读 CloudRidge 行情、不重跑因子或模型，只从这四个已验文件生成新证书。2011-05至2016-12决定证书；2017只列示；2018-2025只作已消费对照。

## 合法结论

上涨和下跌的持续段较少，必须在 Stage4 条件效应中诚实报告不确定性、分年度和episode分布，并使用结果前冻结的收缩/连续估计。这个事实不能用于禁止K2/K3，也不能把外部状态直接映射成operator标签。

Stage3 V2 的终态为 `observable_context_ready_for_stage4`：状态定义与支持足以进入有界配对研究。它不是“状态有效”“条件能赚钱”或“模型需要几个K”的结论。

## 权限

Stage4、Stage5、Stage6、模型训练、operator容量、residual、SSA、账户、指针和生产均关闭。本阶段通过后停在用户 Stage4 checkpoint。
