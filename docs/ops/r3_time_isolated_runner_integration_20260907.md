# R3 时间隔离 F/H：运行链接线与云端集成检查

日期：2026-09-07。承接 `R3-TIME-ISOLATED-DESIGN-20260906-01`。

## 本轮完成

本轮只完成云端可完成的工程接线，不运行真实市场数据。新增运行器将已有模块串成一条明确链路：

1. 从 OT1 `factor_basis_history/future` 与真实交易日历出发，只允许 H20 结果在 2016 年末前成熟的 decision 进入 OT2 年度评价；复用原 `build_candidate_states`、`evaluate_annual_tools` 与 `select_one_tool_per_family`，不复用 2009–2020 事后选出的工具身份。
2. 用前缀选择的工具在完整历史基底上物化固定规则状态，再复用原 `materialize_store` 生成新的 K1 store；原 OT1 residual/exposure 字节不重算。
3. 每个 clock/seed 只生成一份共同 pre-DMD 初始状态，F/H 从完全相同的 state_dict 克隆；两臂随后分别做 DMD 和训练，避免旧 CUDA F 与新 CPU H 拼接。
4. 每臂在最多 3 个 cycle 中保存最小 canonical-loss 的状态；checkpoint、normalizer、candidate、prediction rows 均落新目录。
5. 评分必须通过 `scripts/reaka_r3_time_isolated_compare.py --reload-worker` 启动新的 Python 进程，重新构造对应 arm 并从 checkpoint 树加载；worker 只调用 `assemble_inputs`，不读 `epsilon_future`。
6. 父进程在分数保存后才将已成熟标签挂到共同坐标上；先按 seed、按日期 rank-z，再等权集成，输出 F/H 配对 daily RankIC 和预先固定 block 4/8/12 的 moving-block 区间。

## 云端实际检查

云端运行了与 `tests/unit/test_reaka_r3_time_isolated_runner.py` 对应的合成测试：10 项通过、0 失败。覆盖成熟标签交易位置、前缀选型不读取 2017、共同初始状态、只用 <=2016 fit rows、无标签评分、标签后挂载、共同坐标、输出防覆盖和子进程启动。

另在独立临时 Python package 中启动真实 `--reload-worker` 子进程，加载合成 store 与 checkpoint，输出 180 个有限、非恒定分数；worker 回执 `target_values_read=0`。该检查验证进程与持久化路径，不是原 Stage6 真数据/真权重的市场复验。

检查环境：Python 3.13.5，NumPy 2.3.5，pandas 2.2.3，PyTorch 2.10.0+cpu，pytest 9.0.2。

## 仍未执行

- 没有读取本地 P6.1/P6.2 大数组；
- 没有在真实数据上重做 2009–2016 OT2 前缀工具选择；
- 没有新建真实 2018–2020 K1 store；
- 没有执行 12 次 F/H 拟合、真实 checkpoint 重载或市场评价；
- 没有恢复 fresh OOS、PIT 认证、成交性、经济因果或生产权限；
- 没有调用 GitHub Actions。

因此，云端工程任务“隔离运行链的接线与可得的集成检查”在源码和合成范围内完成；下一步真实运行因数据只在本地，按协作协议交给本地模型。实验结果无论正、负或混合都不得改变冻结年份、seed、clock、arm、cycle 或评价区间。
