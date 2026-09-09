# 云端—本地沟通：LCL-R3-XCOARSE-20260907-01

**状态**：本地已反馈；待云端复核。云端已实现 E-only runner 与月度时间接口并完成 27 项合成/接口检查；真实大数组留本地，不上传整湖，不使用 GitHub Actions。

## 1. 任务目标

在已经最终验收的 `LCL-R3-TIMEISO-20260907-01` 上做最小粗分解：仅新增 `E=history_exposure` 的 6 次拟合，复用原 F/H scores，得到：

- `E−H`: exposure + reliability + exposure-mask 包的有序条件增量；
- `F−E`: state value + state availability 包的有序条件增量。

不是唯一因果归因，不改变 incumbent，不运行 Stage B 细拆，不运行月度 F+M。

## 2. 代码入口

主题仓开发分支：`codex/reaka-foundation-audit-20260905`

使用本任务发布后的最新 HEAD，入口：

- `src/factor_lab/factor_rotation/reaka_r3_x_decomposition.py`
- `src/factor_lab/factor_rotation/reaka_r3_x_coarse_runner.py`
- `scripts/reaka_r3_x_coarse_compare.py`
- `docs/ops/r3_x_decomposition_and_monthly_condition_design_20260907.md`

原 accepted TIMEISO run 不得移动/覆盖。原 run root 类似：

`FactorLab/tmp/LCL-R3-TIMEISO-20260907-01/run01`

## 3. 运行前硬检查

runner 将拒绝：

- TIMEISO numerical runner SHA 与 accepted 身份不一致；
- condition-view SHA 不一致；
- FactorLab HEAD 不是 `b39bb12f43a46b165d18db93191a669234077444`；
- Python/platform/numpy/pandas/torch/device/cuda stable fields 与 accepted TIMEISO 环境不一致；
- accepted F/H receipt 在 frozen identity 字段上不一致；
- 新建 E 的 pre-DMD digest 不等于 accepted F/H 同 seed/clock；
- E/F/H score coordinates 不一致；
- 复算 F−H 不能逐日重现 accepted TIMEISO paired_daily。

任何上述失败只报告 blocker，不改设计绕过。

## 4. run spec

新建例如：

```json
{
  "schema_id": "factorlab.r3_x_coarse_run_spec@1.0",
  "accepted_timeiso_run_root": "/path/to/FactorLab/tmp/LCL-R3-TIMEISO-20260907-01/run01",
  "output_root": "/path/to/FactorLab/tmp/LCL-R3-XCOARSE-20260907-01/run01",
  "expected_factorlab_commit": "b39bb12f43a46b165d18db93191a669234077444"
}
```

执行：

```bash
python scripts/reaka_r3_x_coarse_compare.py --spec /path/to/x_coarse_run_spec.json
```

如果本地仍需要 FactorLab 包路径注入，沿 TIMEISO 已验收方式设置：

```bash
export FACTORLAB_ROOT="/path/to/factor_lab"
```

runner 会自己 bootstrap；不要修改 FactorLab 数值源码。

## 5. 冻结预算

- 新 arm: E only
- clocks: 1430 / 1445
- seeds: 11 / 29 / 47
- new fits: **exactly 6**
- max cycles: **3 each / 18 total**
- F new fits: 0
- H new fits: 0
- E own DMD + own optimizer
- CPU only
- 不增加 E 以外 arm；不跑 `STATE_VALUE_PLUS_E/BETA_ONLY/BETA_RELIABILITY`
- 不改变 2018–2020 支持、normalizer、candidate、seed、LR、K、cycle
- 不因结果负/弱而重跑到转正

每个 E checkpoint 必须保存，再通过 `--reload-e-worker` 新进程打分。评分前不读取 future target；评价阶段才挂原成熟标签。

## 6. 回传小产物

大 checkpoint/scores/store 继续留本地。提交主题仓：

`cloud_results/local_handoff_R3_xcoarse_20260907/`

至少回传：

1. `local_feedback.md`
2. 顶层 `result.json`
3. `runtime_identity.json`
4. 两时钟 `result.json`
5. 两时钟 `paired_daily.csv`
6. 两时钟 `per_seed.csv`
7. 6 个 E `fit_receipt.json`
8. 6 个 E checkpoint `manifest.json`
9. 6 个 E `reload_spec.json`
10. 首次失败日志（如有）

反馈必须写：实际主题仓 HEAD、FactorLab HEAD、命令、退出码、环境、新 fits/cycles、是否重跑、所有异常与未验证项。

## 7. 月度 CloudRidge 定义发现（只查身份，不训练）

云端没有在当前仓库或可恢复上下文找到“前一完整自然月 CloudRidge 1σ / S_obs 条件”的精确公式。

本地允许**只读搜索**本地 FactorLab、旧研究文档或用户已有材料，目标只找：

- S_obs 精确公式；
- 1σ 的估计对象/窗口；
- 正负趋势方向；
- 连续/离散编码；
- available_at / 何时可用；
- 缺月规则；
- 对应源码/文档路径及 commit/hash。

若找到，回传 `monthly_condition_definition.md/json` 小文件；**不要执行 F+M fit**。若找不到，明确 `formula_identity_not_found`。不得根据名称猜公式。

## 8. 云端验收边界

云端将验证：

- E-only 6 fits，无 F/H rerun；
- runtime/source identity 守卫通过；
- E pre-DMD 与 accepted F/H 同 seed/clock 完全相同；
- E 自己 DMD/训练，cycle 选择不看评价结果；
- fresh-process E reload；
- accepted F−H 逐日重现；
- E−H 与 F−E 按同支持报告，负结果照收；
- 不把有序差值改写成唯一可加因果贡献。

`fresh_oos=false`、`full_pit_certified=false`、`production_authority=false` 保持。

## 本地反馈（2026-09-07）

E-only 6 次拟合完成，F/H 未重跑，退出码 0。accepted F−H 逐日重现。combined E−H mean 0.009278，F−E mean 0.011259。报告 [local_feedback.md](../../cloud_results/local_handoff_R3_xcoarse_20260907/local_feedback.md)。月度公式未找回，未跑 F+M。未调用 Actions。

