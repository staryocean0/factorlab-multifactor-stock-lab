# R3 entry-open target source / successor label bundle 云端验收

日期：2026-09-08。任务：`LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01`。
本地结果提交：`5fac86f7bd0434c784dd7a589425979f62247b97`。
本地执行基点：`d6f4bd3a6a7150250fba89e0365d506588e3cf1d`。

## 裁决

**通过，状态 `completed_with_limits`。**

恢复后的P6 future raw定义与历史验收一致：`entry_open[t+20] / entry_open[t] - 1`。本地生成的有界2021–2025 target source在两时钟上均通过旧P6结构成熟锚点；successor label bridge v1.1随后在同一批结构成熟旧D5上精确重放accepted TIMEISO `epsilon_future`。没有证据要求再次修改target producer、OT实现、锚点或容差。

本任务到label bundle为止；本地正确保持 sidecar=0、archived-score preflight=0、24 score jobs=0、new model fit=0、checkpoint reload=0、2026 target=false。

## 1. 本地执行与代码身份

本地报告：

- 主题仓执行HEAD：`d6f4bd3a6a7150250fba89e0365d506588e3cf1d`
- FactorLab HEAD：`b39bb12f43a46b165d18db93191a669234077444`
- target-source bridge Git blob：`a72b531707f41f5539f895c88993dcedc0a2162f`
- label bridge v1.1 Git blob：`28fc75615d50fcc901f36ae448c33c42846c4c6a`
- guard-test Git blob：`ad4f25d8f900b39fb89cb2e1ede0ae024eef5574`
- intraday OT source SHA256：`sha256:4a8ff5fc74adfa474e12a2f0e9c6b770eb7afdb713fe6d676baa423fe5b23c86`

相对执行基点，本地提交只新增回传结果/日志并更新沟通状态，没有修改上述producer、label successor、测试或容差。targeted tests为71 passed、0 failed/error/skipped。

## 2. Target-source硬门：通过

`target_source/bundle.json`：

- schema `factorlab.r3_transfer_entry_open_target_source@1.0`
- status `bounded_entry_open_targets_prepared`
- target定义 `entry_open_t_plus_20_div_entry_open_t_minus_1`
- horizon=20 trading positions
- historical prefix = accepted P6 arrays
- tail origin = bounded DataHub 1m entry-open rule
- calendar end = 2025-12-31
- `contains_2026_target=false`
- fit/score/reload均0

结构成熟锚点为两时钟共同的：2018-01-08、2018-09-25、2019-06-20、2020-03-10、2020-12-03；没有使用2020-12-31作为future target锚点。

DataHub→旧P6事件重放：

- 每个锚点的t和t+20 entry-open都支持一致、max abs error=0；
- 两时钟 `entry_minute_mismatches=0`；
- 由重建entry-open计算的future H20相对旧P6，两时钟五锚点全部support mismatch=0、max abs error=0、above tolerance=0。

因此前一轮定位到的 `raw_future_H20_path_diverges` 已被精确修复，而不是通过改容差绕过。

## 3. Successor label bundle硬门：通过

两时钟 `target_anchor_checks.json@1.1` 均：

- `passed=true`
- `anchors_checked=5`
- `support_mismatches=0`
- `max_abs_error=0.0`
- selection rule为结构成熟2018–2020旧D5盲锚点

每锚点finite支持依次为2559 / 2949 / 3321 / 3445 / 3630。两时钟label bundle均声明：

- `raw_future_definition=entry_open_t_plus_20_div_entry_open_t_minus_1`
- target source task = `LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01`
- calendar=4618日，3982股票，tail decisions=242
- historical prefix reused accepted arrays
- no model fit/inference/reload
- no 2026 completion

这关闭了旧错误label bridge中“decision close作为future H20”的目标定义缺陷。

## 4. 2025尾部与DataHub读取边界

冻结target-source代码在写盘前硬检查：若最后20个日历位置任一future target有限则直接失败；本次进程成功结束，因此本地执行证据支持最后20位置未用2026补标签。云端没有读取本地大`future_h20_raw.npy`逐格独立复核，所以不称为云端全量数组重放。

`source_receipt.json`列出的读取月份为9个旧锚点验证月份和2021-01至2025-12，共69个月份；没有2026月份。DataHub分区记录了path、size和mtime，但**没有记录分区内容SHA256**。因此当前接受绑定的是该本地运行及其路径/文件状态，不升级为不可变原始数据内容封存或完整PIT证明。

历史timestamp取`[11:16]`作为会话墙钟的约定继续沿用R2已验收实现；这不是UTC→上海时区转换证明，也不是交易可执行性证明。

## 5. 云端验收范围

云端重新读取并交叉核对了：

- 本地提交diff：仅回传产物/沟通状态，没有producer代码改变；
- 71项本地测试摘要；
- target source bundle / 完整anchor checks / source receipt；
- 两时钟successor label bundle、target anchor checks与顶层result；
- target-source冻结代码中的最后20位置hard-fail逻辑；
- 本地提交对应Actions runs为空。

云端未重新读取DataHub大分区、entry_open大矩阵、future_h20_raw大矩阵或epsilon_future大矩阵，未运行OT生产器、sidecar、checkpoint replay或model score。因此验收是“本地真实数据执行 + 云端源码/小回执复核”，不是云端全量独立数据重算。

## 6. 下游兼容性修复

验收时发现现有sidecar builder仍硬编码只接受旧错误label metadata `@1.0`，会对正确的`@1.1`产生工程假失败。该问题不影响本任务target科学验收。

云端新增：

- `scripts/reaka_r3_transfer_sidecar_v1_1.py`
- `tests/unit/test_reaka_r3_transfer_sidecar_v1_1.py`

新adapter严格要求：label bundle `@1.1`、entry-open raw-future定义、正确target-source task、结构成熟anchor `@1.1`、5/5 anchor、support mismatch=0、max error<=1e-7；显式拒绝旧`@1.0`。随后仅建立临时**metadata schema兼容视图**，所有数组通过symlink保持原字节不变，再复用原sidecar完整坐标、fold、全历史prefix、maturity和finite-target检查。另写`label_source_binding_v1_1.json`绑定真实@1.1来源。

由于当前云端容器DNS无法clone GitHub，新增adapter的5项新测试**尚未在云端实际运行**，不得写成通过。恢复真实评分前，本地必须先运行这一个新增测试模块及原transfer evaluation/preflight回归。

## 7. 后续放行边界

`LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01`到此关闭，不需要再次生成target source或label bundle。

下一阶段可以恢复原`LCL-R3-TRANSFER-EVAL-20260908-01`，但顺序为：

1. 新adapter targeted test + 原evaluation/preflight tests；
2. 用`reaka_r3_transfer_sidecar_v1_1.py`从现有两时钟label bundle建立sidecar；
3. archived-score read-only preflight 24/24通过；
4. 才运行24个fresh-process无标签score jobs；
5. 全部score落盘后才评价两项冻结primary contrast。

不重建target，不新增arm/seed/年份，不训练，不改normalizer/checkpoint，不读2026补标签。

证据身份仍为 consumed historical transfer，`fresh_oos=false`、`PIT_certified=false`、`production_authority=false`。
