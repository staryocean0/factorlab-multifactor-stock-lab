# LCL-R2-20260906-01 本地增量反馈

任务：LCL-R2-20260906-01  
对照：云端复核 [cloud_review.md](cloud_review.md) 第4节  
执行方：本地 Cursor / FactorLab 工作区  
时间：2026-09-06  
状态：**本地已反馈（增量）**。这不是全量 PIT 证书，也不是云端复核。原 [local_feedback.md](local_feedback.md)、原审计器 `scripts/reaka_r2_local_audit_v1.py` 和原 `r2_local_audit.json` 未改写。

## 执行方 / 环境 / 三个根目录

| 根 | 路径角色 | 身份 |
|---|---|---|
| 主题仓库 worktree | `factorlab-r2-handoff-20260906` | 分支 `codex/reaka-foundation-audit-20260905`，接手时 HEAD `d6cccfea5e9d7eddcae17a7833c0b15732d74e6f` |
| 原 FactorLab | 本机完整研究仓 | `master` HEAD `b39bb12f43a46b165d18db93191a669234077444`；未 reset / 未强制切换 |
| DataHub 1m raw | `unified_datahub/.runtime/live/lake/bars/dataset_version=bars_cn_a_1m_raw_canonical_4ceca170a851` | 与 P6.1 `lineage.json` 的 `dataset_version` 一致 |

Python：FactorLab `.venv` 3.11.11；numpy 2.4.6；pandas 2.3.3；pyarrow 19.0.1。未启动 ROCm，未重训，未重放账户，未调用 Actions。

源码 Git blob：

- 原审计器 `scripts/reaka_r2_local_audit_v1.py`（未改）= `a003fe75fbb127761b63b963c320deecd88de539`
- 后继审计器 `scripts/reaka_r2_local_audit_v1_1.py` = `a076bcf6d48f4c3c49e56ea3a65deb16ecb1491c`
- `IntradayK1InputStore.assemble_inputs` 所在 `reaka_intraday_k1_preflight_v1.py` = `6942fb2dc20d24307578bc7dda45368afaf3d1f5`
- `reaka_intraday_target_fill_v1.py` = `580e8130a6fccc25d2771f3d04db406a3a5ec33e`

大文件仍留本地：`tmp/LCL-R2-20260906-01/local-20260906-delta/r2_local_audit_v1_1.json`。  
公开小产物：本文件、[local_audit_delta_summary.json](local_audit_delta_summary.json)、[local_audit_delta.json](local_audit_delta.json)、后继审计器与反例测试。

## 实际命令及退出码

后继审计器（**退出码 0 = 检查跑完并写了 JSON**，`full_pit_certified=false`）：

```bash
PYTHONPATH=<FactorLab>/src:<worktree>/src <FactorLab>/.venv/bin/python \
  <worktree>/scripts/reaka_r2_local_audit_v1_1.py \
  --factorlab-root <FactorLab> \
  --datahub-root <DataHub 1m raw dataset> \
  --original-report <FactorLab>/tmp/LCL-R2-20260906-01/local-20260906/r2_local_audit.json \
  --output <FactorLab>/tmp/LCL-R2-20260906-01/local-20260906-delta/r2_local_audit_v1_1.json
```

开始 `2026-09-06T07:48:21Z`，结束约 34 秒。容差仍为先声明的 `abs(a-b) <= 1e-6 + 1e-5*|reference|`。未重扫 P6.1 价数组或 OT1 residual 大面。

反例测试（**退出码 0，7 passed**）：

```bash
python3 -m pytest -q tests/unit/test_reaka_r2_local_audit_v1_1.py
```

## 补充 A：严格身份与审计器判定

从原 `r2_local_audit.json` 导出全部 81 条 `A.rows`，保留相对路径、原期望、原声明口径、原 raw 摘要和原状态。79 个非 selection 文件复用原 raw 比对（身份未变，不重哈希大数组）。2 个 `selected_family_tools.json` 按仓库 `canonicalization.canonical_digest` **重算正文**，不信任嵌入字段，raw 失败也不改口径。

| 时钟 | 本地 raw | 云端已公布 raw | 重算 canonical | 与 manifest/原 expected |
|---|---|---|---|---|
| 14:30 | `cd5d7ed8…b08c00` | 相同 | `eec20a28…3c5af3` | 相同 |
| 14:45 | `fffcd456…0ee345` | 相同 | `cd28262b…156bae6` | 相同 |

81/81 后继 `byte_match`。这是可复算身份，不是“嵌入字段等于期望”。原 v1 对这两份 JSON 曾在 raw 失败后改口 canonical；本次按预声明 canonical 重算后仍然对齐，**没有证实选型文件被改坏**。

用原报告已有统计量按 G2–G5 父门重判，**未重扫价格或 residual 数组**：

- G2：C 的 `only_left_finite/only_right_finite` 均为 0 且 `compared>0`，仍通过
- G3：D 的 `recomputed_vs_stored` 违规为 0，现纳入父门后仍通过
- G4：evaluation 分别为 819,842，非空，仍通过
- G5：DataHub 抽样状态是 `passed`，不是 `blocked_missing_dependency`

原数值观察未被这次重判推翻。后继 `digest_row` 不再静默改口径；合成反例证明 G1 篡改正文+保留旧摘要字段现在会 `byte_mismatch`。

## 补充 B：K1 实际消费支路

`assemble_inputs` 按 `symbol_position % 5 + 1` 取 `state_values/state_available`，再拼 `stock_factor_exposures`、`exposure_reliability`、`exposure_available`。`full_reference`（index 0）不进入该 K1。OT3 transport **不进入** 该 K1 特征；`materialize_store` 只读 OT1 残差/暴露和 OT2 已选状态。P6.1 lineage 里的 OT3 过滤只作用于 P6.1 inference，不是本 K1 消费链。

在声明支持上、结果前固定容差后：

| 检查 | 14:30 | 14:45 |
|---|---|---|
| 由 OT2/OT1 重建 K1 `state_values/state_available` | 286,104 格，误差 0 | 同左 |
| 由 OT1 暴露/行业暴露重建 beta/reliability/mask | 32,556,832 格，误差 0 | 同左 |
| 5 个 consumed fold × 14 个因子的固定工具前缀 vs 全样本，以及 vs 存盘状态 | 70/70 通过，未覆盖 0 | 同左 |

前缀覆盖：每时钟 industry 60、market 5、size 5。状态值检验与工具选择时钟分开：选型年仍是 2009–2020，`fresh_oos=false`，不能写成历史上当时已选好。

装配抽查（映射公式，不是全 inference 重装配）：

- 2015-01-06 `000001` pos0 → `crossfit_fold_0`，inference 存在，暴露存在
- 2018-01-08 `000002` pos1 → `crossfit_fold_1`，inference 存在，暴露存在
- 2018-01-08 `000020` pos14 → `crossfit_fold_4`，**无 inference、无暴露**；与原 OLS 抽查该日该股 `no_exposure` 一致，不记通过
- 2020-12-31 `000004` pos2 → `crossfit_fold_2`，inference 存在，暴露存在

未做：六模型全推理、全账户、新拟合、把 OT3 全组件重建为 K1 输入。

## 补充 C：时间合同

现有代码把 `timestamp` 当字符串，取 `[11:16]` 作为会话墙钟。DataHub 文档合同 id 为 `cn_a_session_end_label_no_noon_partial_v2` / `session_end_label_v2`。原记录例子：

```text
symbol=000001 trading_day=2009-01-07
raw_timestamp=2009-01-07T14:30:00Z
p61_slice=14:30
available_at=2026-05-04T15:28:00.747316+00:00  # 不等于 bar 时间
```

`Z` 在这里是拼写后缀，不是 UTC→上海的转换回执；HH:MM 落在 A 股交易时段，P6.1 按中国会话墙钟使用。lineage 字面 `entry_open_t_plus_20_div_entry_open_t_minus_1` 仍只澄清为 `(entry_open[t+20] / entry_open[t]) - 1`，不改原摘要、不重算数组。

明确保留未验证：

- 事件/到达时间、close 首次可读、下单完成是否早于入场 open
- 成交可执行性
- `available_at` 不是 2009–2020 当时可得

因此 C 状态为 `label_proxy_reproducible_event_availability_unverified`，**不能用这次观察关闭 PIT**。

## 覆盖与未关闭项

| 项 | 本地增量结论 | 仍不是什么 |
|---|---|---|
| A 81 项身份 | 可复算；selection raw 对齐云端已核副本 | 不是全项目所有文件，不是官方盘点通过 |
| A G1–G5 | 后继门禁已修；原统计重判仍通过 | 不是原 v1 被改写 |
| B K1 消费 | 两时钟 crossfit 状态/暴露/掩码与 OT 重建一致；70 个消费组合前缀通过 | 不是选型过程历史因果，不是 OT3 全链，不是全特征 PIT |
| C 时间 | 标签代理可重现 | 不是事件可得性或可成交性 |
| Stage4 / 旧账户 | 未重做 | 保持原 not_accepted / 原 blob 未找回 |
| 全量 PIT / 生产 / 重训 | false / 未授权 / 不需要 |  |

## 没有执行的步骤

- 重扫 P6.1 价数组或 OT1 residual 大面
- 全湖分钟、tick、可成交性
- 14:45 / 其他 seed 冻结推理
- 账户重放、重训、Actions
- 写回旧 Stage4

## 建议云端下一动作

读取本文件、`local_audit_delta_summary.json` 和后继审计器。按断言复核 A 身份与 G1–G5、B 消费支路、C 的“能证明/不能证明”边界。不要把脚本退出 0 写成全量 PIT。本地不填写“云端已复核”。R2 保持 `partially_reviewed_not_closed` 直到云端自己改。
