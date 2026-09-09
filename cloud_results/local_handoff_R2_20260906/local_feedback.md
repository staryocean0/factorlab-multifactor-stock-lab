# LCL-R2-20260906-01 本地反馈

任务：LCL-R2-20260906-01  
执行方：本地 Cursor / FactorLab 工作区  
时间：2026-09-06  
状态：**本地已反馈**。这不是全量 PIT 证书，也不是云端复核。

## 执行方 / 环境 / 三个根目录

| 根 | 路径角色 | 身份 |
|---|---|---|
| 主题仓库 / 任务书 worktree | `factorlab-r2-handoff-20260906` | 分支 `codex/reaka-foundation-audit-20260905`，接手时 HEAD `5d371c574b7d1c9cbe636241566641086ce2e338` |
| 原 FactorLab | 本机完整研究仓 | `master` HEAD `b39bb12f43a46b165d18db93191a669234077444`，无 remote，工作区约 6544 项脏改动；**未 reset / 未强制切换** |
| DataHub 1m raw | `unified_datahub/.runtime/live/lake/bars/dataset_version=bars_cn_a_1m_raw_canonical_4ceca170a851` | 与 P6.1 `lineage.json` 的 `dataset_version` 一致 |

Python：FactorLab `.venv` 3.11.11；numpy 2.4.6；pandas 2.3.3；pyarrow 19.0.1；torch 2.11.0+cpu。冻结推理只用 CPU，未启动 ROCm，未重训。

源码 Git blob（工作区当前字节，与任务书 main 定位一致）：

- `reaka_intraday_target_fill_v1.py` = `580e8130a6fccc25d2771f3d04db406a3a5ec33e`
- `reaka_intraday_orthogonal_ot_v1.py` = `0f4fb9901567c2f97fa891b26bbdc8cda3c3ec46`
- 盘点器 `scripts/reaka_local_source_receipt.py`（worktree）= `619ec7a22e4febb2486830b2e0dbcec26d11582c`

输出根（大文件留本地）：原 FactorLab `tmp/LCL-R2-20260906-01/local-20260906/`。  
公开小产物：本目录 `local_audit_summary.json`、本文件、`scripts/reaka_r2_local_audit_v1.py`。

## 实际命令及退出码

官方盘点（**退出码 2**，JSON 仍有用；不是 R2 通过）：

```bash
python3 scripts/reaka_local_source_receipt.py \
  --request <FactorLab>/cloud_results/first_round_rework_20260906/recovery_request.json \
  --input-root <FactorLab> \
  > <FactorLab>/tmp/LCL-R2-20260906-01/local-20260906/local_source_inventory.json
```

计数：`byte_match=13`，`present_unbound=17`，`missing=0`，`byte_mismatch=0`。P6.2 大文件在 recovery 清单中是“等待原 manifest 绑定”，不是缺失。

独立审计器（**退出码 0 = 检查跑完并写了 JSON**，`full_pit_certified=false`）：

```bash
PYTHONPATH=<FactorLab>/src <FactorLab>/.venv/bin/python \
  <worktree>/scripts/reaka_r2_local_audit_v1.py \
  --factorlab-root <FactorLab> \
  --datahub-root <DataHub 1m raw dataset> \
  --output <FactorLab>/tmp/LCL-R2-20260906-01/local-20260906/r2_local_audit.json
```

容差先声明：`abs(a-b) <= 1e-6 + 1e-5*|reference|`。数值比较、文件字节、排序/交易路径未互相替代。

F 项单元测试（**退出码 0，9 passed**）：

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/unit/test_reaka_current_k1_account_ledgers_v1.py \
  tests/unit/test_reaka_intraday_orthogonal_ot_v1.py
```

这是当前源码的合成/单元闭包，不是原账户 blob 找回，也不是真实 P6 全量审计。

## A 来源盘点与绑定

官方盘点不能停在“文件找到了”。本地原产物齐全（非 theme `.parts`）：

- P6.1 formal 完整 npy + `manifest.json` raw `sha256:82f57a1aba896c1e31a0030dcc6677bc0b74eb45eefa478ed5d4321d306aab0f`
- OT formal 1430/1445 的 ot1/ot2/ot3 parquet/npz 均在
- K1 formal 1430/1445 manifest raw 分别为 `sha256:7b8050270c72894ff2e6c67f1fb4a5a5513ca46e8cc0b8c02ed7e0ce3523dfd3`、`sha256:e979fce98e3a6e67f6e5b2bef2701f100d2b174fcdef4539e417ba3aa0c9a7e7`
- 14:30 normalizer raw `sha256:e766372db83b591edbbe162281fbf9e553cc21a9c46089d6225862c35f92b547`
- checkpoint：`output/factor-rotation/reaka_intraday_K1_fit_prefix_successor_v1_2011_2017/formal/{1430,1445}/checkpoints/seed_{11,29,47}`

审计器把 OT/K1 大文件绑到**各自 manifest** 的 `files` / `artifact_digests` / `*_digest`。`selected_family_tools.json` 的 `selection_digest` 是文件内 `canonical_digest`，不是 raw SHA；按 raw 比对会假失败，按 canonical 比对后 **81/81 byte_match，0 missing，0 mismatch**。

recovery 清单的 `present_unbound` 仍然描述其自身口径，不能改写成“官方盘点已通过”。本次 A 结论是：后续 B–E 所需对象都有本地原文件，并且与当前 formal manifest 字节/canonical 对得上。

未绑定/未找回：两份旧账户源码仍与历史期望摘要不符（见 F）。R1 已验收且本次未重读的上传包继续引用旧回执，不宣称本次重验。

## B P6.1 时间 / 价源 / 收益标签

坐标：calendar 3406 日、2007-01-04–2020-12-31，唯一且升序；symbols 3982 唯一；decision 584 个，间隔恒为 5 个日历轴交易位置；首末决策 2009-01-07 / 2020-12-31。

全量数组重算（两时钟）：

```text
history[t] = decision_close[t] / decision_close[t-20] - 1
future[t]  = entry_open[t+20] / entry_open[t] - 1
```

14:30/14:45 history 有限比较约 7,457,575 / 7,457,579，future 约 7,457,583 / 7,457,522；违规 0；最大绝对误差约 2.38e-7（float32）。决策分钟最大 870 / 885，入场分钟最小 871 / 886，且决策分钟 < 入场分钟。inference 各 845,252 行，其中 25,410 行无未来标签仍保留；evaluation 819,842 行恰为 inference 中未来有限子集。未用未来标签剔除推断坐标。

**lineage 字符串与实现不一致，数组与代码一致。** `lineage.json` 写 `entry_open_t_plus_20_div_entry_open_t_minus_1`；实现和独立重算都是 `entry[t+20]/entry[t]-1`。这是命名缺陷，不是收益算错。不要为了对齐字符串去重算数组。

预声明 DataHub 抽样（结果前记录）：2009-01-07、2015-01-06、2018-01-08、2020-12-31，外加一个 14:30 close 含 NaN 的决策日 2015-01-13；股票位 0/14/100/500 = `000001/000020/000517/002086`。两时钟价与分钟 **0 处不匹配**。

分钟标签：抽样日均为 `09:30`–`15:00`，无 `13:00`、有 `13:01` 与 `15:00`，符合 TDX/A 股 1 分钟 **end-label**。因此 `timestamp[11:16] <= 14:30` 取到的 close 对应在 14:30 结束的 bar；`time > clock` 的第一 open 是决策后第一根分钟。时间戳带 `Z`，但数值落在中国交易时段，按中国会话墙钟使用，不是 UTC。`available_at` 全是约 2026-05-04 入库时间，与 bar 时间相等份额为 0，**不能当当时可得性证明**。当时可得只能由 end-label + `time<=clock` 推断。

成交可执行性（停牌/涨跌停/无成交）**未核验**，只报价源/时间。收益是声明的 raw 价格收益，未证明等于投资者总收益或账户收益。

未检：除抽样日外的全湖分钟、除权事件逐笔、2026+。

## C OT1 基底 / 暴露 / epsilon 算术

独立计算 `epsilon = r - intercept - X @ β`，因子来自 `factor_basis_*` 的 `crossfit_fold_*`（variant 0 是 `full_reference`，拟合用 `fold+1`），收益来自同时钟 P6.1 raw H20。系数应用到 `[asof, next_decision)`。

两时钟：

- 暴露 1,142,919 行，行业暴露 684,119 行
- `crossfit_fold == symbol_position % 5`
- `uses_future` 全 false
- `fit_end_date == calendar[day-1]`
- 应用格子 5,699,923
- 与存盘残差比较：history 5,632,172、future 5,501,746，违规 0，最大误差 0（float32 支持上完全一致）
- 日历/股票轴与 P6.1 一致

OLS 抽查（同一预声明日×股票，独立 `lstsq`，窗口 `[t-120,t)`）：每时钟 10 个有暴露格点，系数违规 0。2009-01-07 四个抽样股票无暴露行（该日未进入该批股票的拟合支持）；2015/2018 的 `000020` 同样无暴露。这不是把无暴露写成通过。

未做：全样本重拟合 OLS；未重做行业成分/权重从 DataHub 到基底的正交化全链。C 证明的是**存盘系数应用到存盘因子与 P6.1 收益后，与存盘 epsilon 算术一致**，以及抽查点上系数可由同一 120 窗 lstsq 复现。

## D OT2 / OT3 状态与选择时钟

两时钟选型相同：industry = `causal_haar_wavelet_bandpass`（retrospective_tool_selected），size = `laplace_iir_mixed_bandpass`（retrospective_tool_selected），market = naked 对照（`no_tool_increment_keep_transparent_control`）。`fresh_oos=false`。评价年 2009–2020 全部进入选型；`evaluate_annual_tools` 用 **future 因子收益**。这是已消费开发材料上的方法选择，不能称为当时已选好，也不能当 fresh OOS。

状态值本身用 `history_basis` / `full_reference` 重建。对选定工具做 2016-12-31 前缀 vs 全样本：industry/size/market 前缀稳定，违规 0；与存盘 `selected_factor_states` 一致（industry 抽查第一条 `L1_FACTOR_CORE*`，不是全部行业核）。Haar/Laplace 实现是因果滚动/IIR。OT3 transport 1,142,919 行，时钟字段与当前时钟一致。

共同市场状态复制给多只股票，不能当成等数量独立市场观测。未把旧持仓已实现贡献写成预测增量。

## E K1 消费绑定 / 冻结推理

两时钟 K1 `calendar/symbols/decision_positions` 与 P6.1 一致；`epsilon_history/future` 与 OT1 存盘面逐值一致（5,632,172 / 5,501,746，误差 0）。labelled 恰为 inference 中未来有限子集。K1 inference 853,732 vs P6.1 845,252：K1 用 epsilon 历史完整 + 暴露支持，不是 P6.1 的 history+OT3 过滤。inference 年 2011–2020；无标签 25,979 行保留。

冻结推理（未重训）：14:30 seed 11，`split_indices()["review"]` 的前 256 + 后 256 行（去重后 512），CPU `load_state_tree` + `score_rows`，对照 `review_scores_seed_11.npy`（长度 82,321）。比较 512，违规 0，最大绝对误差约 7.75e-7。只报告该切片；不是全 review、不是 14:45、不是 seed 29/47。

normalizer `fit_end_year=2016`，`target_used=false`。r0 只关潜残差网，金融 epsilon 仍被消费。

## F 历史测试及 Stage4 / 账户诊断

过滤器 `src/factor_lab/filtering/cloudridge_3_0_hybrid_filter_bank.py` 本地存在（git blob `4138527273446745344ee4b3e534ecfb8d9bf77c`）。两个原未跑模块现可跑，9 passed。这是**当前源码**，不是旧缺失时的历史 blob。

Stage4 正式面板在主题仓，不在原 FactorLab output：

- `output/factor-rotation/reaka_v2_stage4_observable_factor_pairing_v1_2011_2025/formal/pairing_panel.csv` 356 行 / 176 个月
- 重复键 4 个：`(consumed_repeat_comparison_no_retune, 14:30|14:45, 2018-01|2021-01)` 各 2 行
- 根因在 `monthly_selector_panel.csv`：同月被 `first_date` 拆成两行。早行（2018-01-02 / 2021-01-04）只有 `other`；晚行（2018-01-08 / 2021-01-08）才有 index/industry/size
- pairing 把两行拷到同一 `(period, clock)`，未去重
- isolated 副本缺失；组件账、linked-log 不在本快照，归因守恒未验证
- **未 drop_duplicates，未按结果挑行，未写回旧目录**
- 旧 Stage4 保持 `not_accepted`

账户：当前文件存在但不是历史期望字节。

| 文件 | 当前 raw SHA | 历史期望 |
|---|---|---|
| `reaka_current_k1_account_ledgers_v1.py` | `cce2c26db12aaba5a7feb212215fbc71b802b8377fd8ec8472fb88cdeb95b139` | `bf97a470c28d52379a2bce9abbdb25b058c9727c38ee748813e2afe0dd9373c1` |
| `account_research_bundle.py` | `8228972eeff82b6489a4eb6db40919f76d4abdef42bfc334925d8ec3255cca2f` | `7480480ad82d94f2ac4df361c084fe16a1d2f77405ee8989d83a1848ccaa5a97` |

保留“原历史字节过程不可完全复现”。当前单元测试通过 ≠ 找回原账户实现。未重放账户。

## 覆盖、通过 / 失败 / 未运行

| 检查 | 状态 | 覆盖 | 不是什么 |
|---|---|---|---|
| A 官方盘点 | 退出 2 / unbound | recovery 30 条 | 不是 R2 通过 |
| A manifest 绑定 | passed | 81 个 OT/K1/P6.1 文件 | 不是全项目所有文件 |
| B 数组与时钟 | passed | 两时钟全量 H20 与分钟序 | 不是全湖分钟、不是可成交性 |
| B DataHub 抽样 | passed | 5 日 × 4 股 × 2 时钟 | 不是全量 PIT |
| C epsilon | passed | 存盘有限支持全量 | 不是全样本重做正交化 |
| C OLS | passed | 每时钟 10 个有暴露抽查点 | 不是全部股票/日 |
| D 状态前缀 | passed | 选定工具 + 一条行业核 | 不是全部行业核 |
| D 选型时钟 | 记录为已消费 | 2009–2020 future 评价 | 不是 fresh OOS |
| E 绑定 | passed | 两时钟全量 epsilon |  |
| E 冻结推理 | passed | 14:30 seed11 的 512 review 行 | 不是全 review / 其他 seed / 14:45 |
| F 单测 | 9 passed | 当前源码 | 不是原账户 blob |
| F Stage4 | 历史唯一性失败 | 已装船 formal 面板 | 不是 K1 消费链缺陷 |
| 账户重放 / 重训 / 2026+ | not_run |  | 任务禁止 |

## 缺陷 vs 证据不足

明确发现、但不要求重算 P6/K1 输入或分数：

1. `lineage.json` 未来公式命名写了 `t_minus_1`，数组与代码不是这个公式。
2. DataHub `available_at` 是 2026 入库时间，不能当 2009–2020 当时可得。
3. OT2 工具身份用了 2009–2020 未来因子收益；状态值本身前缀稳定。已标 `fresh_oos=false`。
4. Stage4 2018-01/2021-01 重复月，来自组件覆盖起点进入月键；无组件账则不能守恒证明。
5. 两份旧账户源码历史字节未找回。

未发现：决策/入场分钟序错误、H20 算错、epsilon 应用算术错误、系数抽查与 120 窗 lstsq 不符、K1 吃错 OT1 面、冻结推理切片分数漂移、用未来标签剔除 inference。

证据不足、不得升级为全量通过：全湖分钟、可成交性、全部行业核状态、14:45/其他 seed 全量推理、账户路径复现、除权逐笔。

## 最小必要返工与可复用原产物

**R2 在已声明支持上：P6.1 价源/标签、OT1 系数应用与 epsilon、OT2 状态值因果性、K1 消费绑定，没有发现需要重算输入或现任分数的构造错误。** 身份未变时优先复用：

- 可复用：P6.1 formal 两时钟数组；OT1/OT2/OT3 formal；K1 input formal；`d8-h8-K1-r0_fit_prefix_successor` 六份 checkpoint 与 14:30 seed11 review 分数（至少该切片一致）；R1 已验收上传包。
- 不可把旧分数冒充修复后结果：本次没有修复后的新分数。
- 不可复用为独立月份证据：Stage4 pairing / selector 2018-01、2021-01。
- 不可复用为当时可得证明：DataHub `available_at`。
- 不可复用为原账户实现：两份 unrecovered 源码。
- 不必为 lineage 字符串重跑物化；后继合同改正文字即可。
- 不必因 OT2 选型用了已消费区间而重训；保持 `fresh_oos=false`，不要改口。

影响表：

| 问题 | 影响范围 | 直接消费者 | 原产物 | 是否重算 |
|---|---|---|---|---|
| lineage 命名 | 文档 | 读者 | 数组可留 | 否 |
| available_at 非当时 | 字段解释 | PIT 话术 | 价数组可留 | 否 |
| OT2 选型用 future | 方法身份 | 状态工具选择 | 状态值可留 | 否，已消费 |
| Stage4 重复月 | 2018-01/2021-01 两时钟 | 旧 Stage4 统计 | pairing 只读 | 不在本次 K1 链；要后继版本才重建 |
| 账户原 blob | 旧账户复现 | R4 | 当前源码可测、不可冒充原字节 | 不重放 |

R3：云端只复核本文与小产物；可选扩大冻结推理到其他 seed/14:45，或后继合同改 lineage 字面。不要自动重训。  
R4：账户仍走独立不变量或另行标识的后继重放；本次未开。

## 没有执行的步骤

- 全湖分钟重建、可成交性、除权逐笔
- 全部行业核状态前缀
- 14:45 / seed 29/47 冻结推理
- 账户完整复现或 NAV 重放
- 写回旧 Stage4、去重、金融签字
- 训练、K 搜索、指针、生产、Actions

## 建议云端下一动作

读取本文件与 `local_audit_summary.json`，核对版本、范围、断言和异常。不要把脚本退出 0 或抽样通过写成全量 PIT。本地不填写“云端已复核”。原研究状态保持 `r2.not_independently_verified` 直到云端自己改。
