# LCL-R3-INFOCLOCK-20260907-01 来源与信息时钟说明

只读追源。没有新 fit / inference / checkpoint reload / 全量 OT 重跑。  
`compare_prefix` 是脚本工具函数，本轮**没有**接通真实生成器，也**没有**声称全量前缀通过。

FactorLab 密封 HEAD 仍是 `b39bb12f43a46b165d18db93191a669234077444`。下列若干 intraday 生产器在工作区是 **untracked / dirty**，以实际磁盘字节为准，不能把它们写成该密封提交的已入库身份。

## 1. `selected_factor_states.available`

### 谁生成

本地实际 intraday OT2 函数：

`src/factor_lab/factor_rotation/reaka_intraday_orthogonal_ot_v1.py`  
`build_selected_states`（工作区 git blob `0f4fb9901567c2f97fa891b26bbdc8cda3c3ec46`，**不在 FactorLab HEAD**）

对每个 `(variant_id, factor_id)`：

1. 取已选 tool（本 TIMEISO 冻结：industry=`causal_haar_wavelet_bandpass`，market=`simple_moving_average_trend`，size=`laplace_iir_mixed_bandpass`）；
2. 用 `family_tool_state` / `family_naked_state` 生成 `timing_state`；
3. **`available = state.notna()`**。

相关摘录（`build_selected_states`）：

```python
"timing_state": state.to_numpy(dtype=float),
"available": state.notna().to_numpy(dtype=bool),
"signal_only": True,
"uses_forward_outcome": False,
```

`family_tool_state`（工作区 `orthogonal_factor_timing_state_v1.py` blob `54813602fdddae6371b43b9702a41ec08e9c0d11`；HEAD blob 不同：`51b26a4c3aeb39fdba20b54197e06ce57f4c2442`）：

- 前 `capability.warmup_bars` 个位置置 NaN；
- `log_level` 或 `returns` 为 NaN 则 NaN；
- market/industry clip 到 `[0,1]`，size 为有符号差。

本任务三个 tool 的 warmup_bars（工作区 CAPABILITIES，不是到达证书）：

| family | tool | warmup_bars |
|---|---|---:|
| industry | causal_haar_wavelet_bandpass | 128 |
| market | simple_moving_average_trend | 60 |
| size | laplace_iir_mixed_bandpass | 120 |

因此 available 取决于：有限正交收益、伪对数水平、tool 预热、以及后续 NaN。  
**不是**成交覆盖、成员数或标签。`uses_forward_outcome=False`。未发现 tick 到达日志。

### K1 如何物化

主题仓与 FactorLab 工作区同字节：

`reaka_intraday_k1_preflight_v1.py` git blob `6942fb2dc20d24307578bc7dda45368afaf3d1f5`

`build_state_store`（约 L245）只保留 `states["available"]==True` 的行，把 `timing_state` 写入 `state_values`，并把对应格写成 `1`。**该函数不校验发布/首次可读时间。**

`assemble_inputs`（约 L132）：

- 十个端点：`t + arange(-180, 1, 20)`，即 H20 间隔，不是最近连续十日；
- 状态/状态掩码索引：`variant = symbol_position % 5 + 1`，同一 endpoint、同一 fold 的股票共用同一 mask；
- 最大被读日历位置 = 决策日自身（offset 0）。

OT3 把 `effective_timestamp` 写成 `asof_dateT{14:30|14:45}:00+08:00_after_bar_close`。这是产品字符串，不是逐笔到达证据。K1 消费路径不再读取该字段。

### 本轮 profile 对 available 的数据事实（不是 PIT）

2018–2020 消费窗口：两时钟 `state_mask` 的 14 个因子通道 **全部恒为 1**（`all_factor_channels_constant=true`）。  
2011–2016：市场通道恒为 1，其余通道有约 1% 零；同一决策日跨 fold 的 mask 差分为 0。  
这只说明消费格子的 0/1 模式，不能单独证明“动态历史可得状态”或“泄漏”。

## 2. `d5_stock_exposures` / industry `reliability`

### 精确公式（intraday 包装器调用 daily helper）

本地实际拟合函数：`fit_intraday_stock_exposures`（同一 untracked OT1 文件）。

窗口（决策日 `day`，日历整数下标）：

```python
window = np.arange(day - LOOKBACK, day)  # LOOKBACK=120
# 即 [day-120, day)，不含决策当日
```

门槛：`MIN_OBSERVATIONS=96`，半窗 `HALF_MIN_OBSERVATIONS=40`，`MAX_CONDITION_NUMBER=1.0e8`。  
设计阵：`[1, history_basis[fold+1, window][:, selected_factors]]`，只保留因子完全有限的行；股票须在这些行上完全有限。

数值公式来自已入库 daily helper  
`orthogonal_index_timing_transport_ot1_v1.py`  
git blob **`bf63cfe9d2018d3b9f20095919ce6cfd743493da`**（与 FactorLab HEAD 一致，与云端记录一致）：

`_fit_stock_batch` / `_fit_stock_single`：

- `coverage = min(n / 120, 1)`
- 半窗 OLS（去掉截距）`drift = ||β_first - β_second|| / max(||β_full||, 1e-6)`
- `stability = 1 / (1 + drift)`
- `condition_reliability = 1 / (1 + max(log10(max(cond, 1)), 0))`
- **`reliability = min(coverage, stability, condition_reliability)`**

因此 reliability **确实使用** coverage、半窗 beta 稳定性、condition-number quality。它不是正确概率、未来拟合优度或独立 alpha。

industry 表：同一股票在该决策上的 **同一个 reliability** 被写到其 industry beta 行；不是另一套窗口。

### K1 再加工

`build_exposure_store` 只读 `available==True` 且 beta/reliability 有限的行，按 `asof_date` 必须落在 D5 `decision_positions`。  
`assemble_inputs` 实际消费 `reliability * exposure_mask` 与 `beta * exposure_mask`。

### 时钟 / asof

- `asof_date` = D5 决策日历日；
- 拟合窗口止于决策日前一交易日；
- 产品层声称 `14:30`/`14:45` 收盘后可读；
- **没有**历史 `available_at` 到达日志。不能把 asof_date 生成伪造到达时间。本轮 `time_evidence=[]` → **unknown**，不是 PIT 通过。

daily helper **不能自动代替**当前 untracked intraday 包装器身份；公式相同是因为包装器显式调用 `old_ot1._fit_stock_batch`。

## 3. 本任务必要来源身份

| 文件 | git blob / 备注 |
|---|---|
| 主题仓 `reaka_intraday_k1_preflight_v1.py` | `6942fb2dc20d24307578bc7dda45368afaf3d1f5`（与云端一致） |
| FactorLab 工作区同文件 | 同 blob，**untracked**，不在 HEAD `b39bb12` |
| FactorLab 工作区 `reaka_intraday_orthogonal_ot_v1.py` | `0f4fb9901567c2f97fa891b26bbdc8cda3c3ec46`，**untracked / 不在 HEAD** |
| FactorLab `orthogonal_index_timing_transport_ot1_v1.py` | `bf63cfe9d2018d3b9f20095919ce6cfd743493da`，在 HEAD |
| FactorLab 工作区 `orthogonal_factor_timing_state_v1.py` | work `54813602…` ≠ HEAD `51b26a4c…`（dirty） |
| 已验收 TIMEISO store manifest | 两时钟 `artifact_digests` 已作为 `expected_hashes` 绑定，本轮核验通过 |
| TIMEISO 选择 | `tmp/LCL-R3-TIMEISO-20260907-01/run01/{1430,1445}/prepared/selection/selected_tools.json` |
| 正式 OT 2007–2020 | `output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020/formal/{1430,1445}/{ot1,ot2,ot3}/manifest.json`；`post_2020_rows_read=0` |

未上传大源码快照。没有 tick 整湖。

## 4. 前缀核验

- 脚本 `compare_prefix`：**未接通**真实 OT1/OT2 生成器。
- 本轮 **没有**重跑全量 OT1。
- 另有 `reaka_residual_only_post2020_extension_v1_2009_2026/formal/store/post2020_extension_validation.json` 自称 `passed_result_free_prefix_exact`，但：schema 不是已验收 K1 store、股票数 5894≠3982、`sample_year_max=2026`。  
  **不能**当作 TIMEISO/XFINE 前缀通过，也 **不能**用作 2021–2025 迁移输入（2026 禁止）。

## 5. 时间证据

没有带时区的历史 `decision_at` / `dependency_max_at` / `available_at` / `source_ref` 行。  
只有 2026 年入库时间也不能回填 2018 年可得时间。  
因此 `time_evidence.status=unknown`。未申请 tick 整湖。

## 6. 2021–2025 跨期准备（只检查元数据）

冻结候选年：2021–2025。2026 禁止。本轮不打开新期标签或评分。

| 来源 | 覆盖 | 与已验收定义是否相同 |
|---|---|---|
| 已验收 TIMEISO/XFINE K1 store | calendar `2007-01-04`–**`2020-12-31`**；inference 2011–2020 | 本任务 profile 对象。2021–2025 = **`no_support`**（合法） |
| OT `reaka_intraday_orthogonal_OT_v1_2007_2020` | 正式 1430/1445 ot1/ot2/ot3 存在；`post_2020_rows_read=0` | 无 2021–2025 同定义 OT |
| P6 `reaka_intraday_joint_training_P6_4J_input_v7` | 决策约 2011–2016，`calendar_end=2016-12-29` | 14 个 factor 名称相同；`symbols.npy` digest 与 TIMEISO 相同 `c68ab8cb…`；**不含 2021–2025** |
| `reaka_residual_only_post2020_extension_v1_2009_2026` | `sample_year_max=2026`，5894 只股票，不同 schema | **禁止使用**（含 2026 + 宇宙不一致） |

factor 名称顺序（14）：market CloudRidge、size S-L、然后 12 个 `L1_FACTOR_CORE:l1_*`。TIMEISO store `factor_ids` digest `sha256:67128a19…`。P6/post2020 的 `factor_ids.json` 无 canonical 字段，digest 不同，但名称列表相同。

symbol 顺序：已验收 store `symbols.npy` digest `sha256:c68ab8cb18563a367860b468a4431cde741105fb90e5035f9d8898061bc8b460`，3982 只。post2020 扩展是 5894，**不能**默认延续。

### 四组原模型 checkpoint（只检查路径，未 reload）

全部 24 个目录存在且含 `manifest.json`：

- F：`tmp/LCL-R3-TIMEISO-20260907-01/run01/{1430,1445}/experiment/models/seed_{11,29,47}/F/checkpoint`
- STATE_VALUE_PLUS_E / BETA_ONLY / BETA_RELIABILITY：`tmp/LCL-R3-XFINE-20260907-01/run01/{clock}/models/seed_{seed}/{arm}/checkpoint`

缺少的直接来源：**没有**已验收、同 3982 宇宙、同 K1 schema、不含 2026 的 2021–2025 store/OT。这是准备记录，不是让本地现在补训练或物化的授权。

## 7. 本轮 profile 的结构观察（有界）

两时钟一致：

- 2011–2016 / 2018–2020 有支持；2021–2025 `no_support`；
- 2018–2020 的 state **mask 全恒 1**，state **values 非恒定**；
- masked reliability 在 market/size 上非零且非常数，行业通道大量为零（exposure mask 稀疏）；
- 跨 fold 同日 mask 无差异。

恒定 mask 不能证明“没有信息”，也不能证明“有可迁移信息”。消融增量仍可能来自非线性编码。这正是本审计要留下的界限。
