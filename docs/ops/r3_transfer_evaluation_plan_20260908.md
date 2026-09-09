# R3：2021—2025 冻结模型历史迁移评价

日期：2026-09-08  
任务：`LCL-R3-TRANSFER-EVAL-20260908-01`

## 1. 研究目标

2021—2025 同定义无标签 feature stores 已完成并验收。下一步不再训练模型，而是复用已经冻结并保存的四组 arm：

- `F`
- `STATE_VALUE_PLUS_E`
- `BETA_ONLY`
- `BETA_RELIABILITY`

只评价两个此前已经登记的 primary contrasts：

1. `F − STATE_VALUE_PLUS_E`
2. `BETA_RELIABILITY − BETA_ONLY`

第一项只能解释为既有 state-mask **算法路径**的跨期表现。INFOCLOCK 已证明2018—2020评价期的14个 state-mask 通道均恒为1，因此不得重新把该对比称为“动态mask信号”。第二项是 reliability 的冻结算法增量，仍不是PIT或经济因果证明。

2021—2025在现行数据治理中属于 consumed historical material，因此本轮成功也不是 fresh OOS。

## 2. 冻结预算与禁止事项

固定：

- clocks = `1430`, `1445`
- seeds = `11, 29, 47`
- arms = 上述4组
- fresh-process score jobs = **24 exactly**
- new model fits = **0**
- checkpoint selection = **0**
- normalizer refit = **0**
- DMD reinitialization = **0**
- tool reselection = **0**

禁止：新增seed/arm/年份；重训；根据2021—2025结果换checkpoint；使用2026补2025年末标签；启动账户、总收益或CloudRidge月度实验。

## 3. 标签和评分严格分离

评分 worker 的输入合同中**没有 label/target 路径**。它只能看到：

- accepted transfer feature store；
- frozen candidate/normalizer；
- accepted checkpoint + fit receipt；
- theme / FactorLab source identity。

24个score jobs全部完成后，主进程才打开独立 label sidecar 并按坐标评价。feature store本身继续没有 `epsilon_future` 或 `assemble_batch`。

2025年末那些已经产生预测但 `decision_position + 20 >= bounded_calendar_end` 的行仍保留在score文件里，但不会进入label评价。禁止读取2026补齐。

## 4. 标签生产合同

本地标签桥接：

`scripts/reaka_r3_transfer_label_bridge.py`

使用与transfer features相同的固定3982股票队列、同一交易日历、同一cross-fit fold与盘中金融残差配方。原始未来H20收益定义为：

`decision_close[t+20] / decision_close[t] - 1`

仅使用截至2025-12-31的有界价格数组；最后20个交易位置自然为NaN。

标签bundle必须声明：

- schema `factorlab.r3_transfer_label_bundle@1.0`
- `calendar_end=2025-12-31`
- `contains_2026=false`
- `target_definition=H20_financial_residual_epsilon_future_K1_v1`
- `horizon_trading_positions=20`
- `labels_used_for_features=false`
- `fold_policy=explicit_incumbent_symbol_position_mod5`

历史2007—2020 target前缀沿用accepted TIMEISO数组；该复制不是独立producer replay。

### 旧target锚点门槛

为了验证当前尾部target生产器没有改变数值定义，在2018—2020旧D5中按**与目标数值无关的固定索引分位**选5个锚点。当前生产器对这些锚点重新生成 `epsilon_future`，必须满足：

- finite-support mismatch = 0
- max abs error <= `1e-7`

锚点不通过，立即停止，不建立sidecar、不启动24项评分，也不得通过改变容差或挑其他锚点转绿。

该锚点检查只是有界数值桥，不认证全量历史PIT。

## 5. label sidecar

`build_label_sidecar` 先验证：

- label bundle raw SHA256；
- calendar与feature store完全一致，且不存在2026；
- 原3982 symbol身份和fold；
- 14 factor身份；
- target-anchor checks；
- accepted 2007—2020 `epsilon_future` 全前缀：有限支持完全相同，有限值绝对误差 <= `1e-7`。

之后只在feature store已有 `maturity_eligible_indices` 上取有限target，生成：

- `evaluation_indices.npy`
- `rows.npy`
- `targets.npy`
- `manifest.json`

sidecar不改变模型预测支持，不向score worker暴露。

## 6. 评分前 checkpoint / numerical replay gate

正式运行前自动执行：

`src/factor_lab/factor_rotation/reaka_r3_transfer_score_preflight.py`

对2 clocks × 3 seeds × 4 arms = **24组**accepted模型逐一：

1. 核对FactorLab HEAD、accepted numerical environment、TIMEISO/condition-view/X-decomposition及transfer-input源码身份；
2. 核对checkpoint manifest与fit receipt；
3. fresh load冻结checkpoint；
4. 在原2018—2020 accepted store上，按score文件长度固定均匀抽取最多64个旧坐标；
5. 重新 `score_no_labels` 并与原保存score比较，row必须相同，max abs error <= `1e-7`。

这个gate读取旧score，但不读取旧future target，也不产生2021+ score。任何一组失败都禁止正式迁移评分。

## 7. 正式24项评分

入口：

`scripts/reaka_r3_transfer_evaluate.py --run <spec>`

CLI先执行上述read-only preflight；通过后才顺序启动24个fresh Python worker。每个worker：

- CPU；
- 加载唯一指定的accepted checkpoint；
- 使用transfer feature store的全部 `prediction_indices`；
- 调用冻结TIMEISO `score_no_labels`；
- 写 `scores.npz` 和 `score_receipt.json`；
- receipt必须记录 `target_values_read=0`、`label_path_received=false`、`new_model_fits=0`。

正式评分失败不得原目录resume-by-guessing；保留失败目录，修代码时另建新output root，并说明是否已经生成部分score。不得按表现重跑。

## 8. 评价口径

每个clock、seed、arm的score只在sidecar有限成熟target坐标上评价。

seed ensemble沿用既有冻结定义：**每日每seed截面rank-z，三个seed等权平均**。

primary：每日截面Spearman RankIC差。

两时钟主量：同一日期先取1430与1445 contrast的等权平均，再跨日期平均。时钟和seed均不能当成独立市场重复。

同时预先报告：

- per clock / seed；
- 2021 / 2022 / 2023 / 2024 / 2025逐年；
- phase 0/1/2/3；
- moving-block 4 / 8 / 12；
- residual decile spread；
- residual Top30-minus-universe。

secondary不得救活失败的primary；pointwise block区间不得冒充两个primary的联合95%显著性。

## 9. 云端开发验证

新增：

- `src/factor_lab/factor_rotation/reaka_r3_transfer_evaluation.py`
- `src/factor_lab/factor_rotation/reaka_r3_transfer_score_preflight.py`
- `scripts/reaka_r3_transfer_evaluate.py`
- `scripts/reaka_r3_transfer_label_bridge.py`
- 对应两个evaluation/preflight/label-bridge测试模块

云端纯逻辑/合成范围实际运行 **24 tests，24 passed**，并通过py_compile。覆盖label bundle/sidecar、2026拒绝、旧target prefix漂移、5锚点合同、24-job预算、worker无label路径、seed rank-z、两时钟聚合以及旧score preflight辅助逻辑。

没有在云端读取用户真实2021—2025标签、加载真实checkpoint做forward或产生市场结果；完整FactorLab测试也未运行。

## 10. 证据边界

本轮完成后仍必须保持：

- `fresh_oos=false`
- `PIT_certified=false`
- `production_authority=false`

不得将结果写成股票总收益、账户alpha、unique causal attribution或生产可交易策略。
