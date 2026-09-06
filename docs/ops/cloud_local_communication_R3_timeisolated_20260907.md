# 云端—本地沟通：LCL-R3-TIMEISO-20260907-01

**状态**：待本地执行；云端运行链已接通并完成合成检查。大数据留在本地，不上传整湖，不用 GitHub Actions。

## 目标

按冻结设计 `R3-TIME-ISOLATED-DESIGN-20260906-01`，在本地真实 P6.1/P6.2/K1 数据上执行一次 2016 年末冻结、2018–2020 评价的同环境 F/H 对照。它是已消费历史材料上的时间隔离重复比较，不是 fresh OOS。

## 代码入口

使用开发分支 `codex/reaka-foundation-audit-20260905` 的本次 runner 集成版本：

- `src/factor_lab/factor_rotation/reaka_r3_time_isolated_runner.py`
- `scripts/reaka_r3_time_isolated_compare.py`
- `docs/ops/r3_time_isolated_evaluation_plan_20260906.json`

不得用旧 `reaka_r3_condition_compare.py` 代替本任务。

## 本地只读准备检查

两时钟各自确认存在：

- `ot_root/ot1/factor_basis_history.parquet`
- `ot_root/ot1/factor_basis_future.parquet`
- `ot_root/ot1/stock_residual_surfaces.npz`
- `ot_root/ot1/d5_stock_exposures.parquet`
- `ot_root/ot1/d5_stock_industry_exposures.parquet`
- P6.1 `decision_positions.npy`

路径或依赖缺失只阻断对应 clock；不要回到 R0/R1，不要重算已验收的 OT1 epsilon。

## 运行规范

创建新的 run spec：

```json
{
  "schema_id": "factorlab.r3_time_isolated_run_spec@1.0",
  "output_root": "/path/to/FactorLab/tmp/LCL-R3-TIMEISO-20260907-01/run01",
  "device_name": "cpu",
  "expected_source_commit": "<本次云端runner最终提交>",
  "clocks": {
    "1430": {"ot_root": "/.../formal/1430", "p6_root": "/.../P6.1/formal"},
    "1445": {"ot_root": "/.../formal/1445", "p6_root": "/.../P6.1/formal"}
  }
}
```

执行：

```bash
python scripts/reaka_r3_time_isolated_compare.py --spec /path/to/run_spec.json
```

固定预算：两臂 × 两时钟 × seed 11/29/47 = 12 次新拟合，每次最多 3 cycle。不得增加 E、K、seed、cycle、年份、阈值或调参搜索；不得因结果不理想重跑到转正。两臂统一 CPU 后端。

## 必须回传的小产物

大 store/checkpoint/score 数组保留本地。回传：

1. `local_feedback.md`：实际主题仓 commit、本地 FactorLab commit、数据根身份、命令、退出码、环境、异常和未验证事项；
2. 顶层 `result.json`；
3. 两时钟 `result.json`、`paired_daily.csv`；
4. `source_snapshot.json`、`environment.json`；
5. 两时钟 `selection/selected_tools.json` 与 annual metrics 的行数/摘要；
6. 12 个 checkpoint `manifest.json`、reload spec 与每个 seed/arm fit receipt；
7. 若失败，保留首次失败日志和已经完成的独立 clock，不删结果后改变设计重试。

## 云端验收边界

云端将核对：工具选择只使用 2016 年末前成熟结果；F/H pair identity 除 arm 外一致；同一 seed 的 pre-DMD digest 一致；真实 checkpoint 经新进程重载；2017 不进入主评价；2018–2020 预测先生成、成熟标签后挂载；两时钟和 seeds 不当作独立市场样本。

即使结果显著为正，也只能称为“已消费历史材料上的时间隔离、同环境算法比较”。`fresh_oos=false`、`PIT_certified=false`、`production_authority=false` 保持不变。
