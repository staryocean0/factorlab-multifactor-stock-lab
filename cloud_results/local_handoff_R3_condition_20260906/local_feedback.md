# LCL-R3-COND-20260906-01 本地反馈

任务：LCL-R3-COND-20260906-01
执行方：本地 Codex controller
时间：2026-09-06
状态：本地已反馈；**不是**云端已复核；**不是** PIT / fresh OOS / 条件因果 / 生产通过。

## 身份与复用（写于查看新2017 H分数之前）

- 主题仓执行基点 `6552b6f72b80d7bd4bc47d68e188ffce8519d6c0`
- 原 FactorLab `master` `b39bb12f43a46b165d18db93191a669234077444`（脏工作区未改）
- 脚本 `scripts/reaka_r3_condition_compare.py` SHA-256 `4c3d38267cd14bdde866d352efa94c6c862af3997cd37816942785a2b43fa687`
- 适配器仍为云端 `reaka_r3_condition_views.py`
- **F 复用**：是。fit-prefix `f2538b64478c1c05a16c347e69864751661af4cb`、training `94f6fb1eafb2d02cdad4a3cc2883884ef9356852`、preflight `6942fb2dc20d24307578bc7dda45368afaf3d1f5` 与设计一致；输入/formal blob 与 NOFIT 一致。已知相关目录没有同口径 H。残差输入消融不作 H。
- 未因 H 结果不利而重训 F；未执行可选 E；新拟合 6 次（2 时钟 × 3 seed），每 seed ≤3 cycle。
- H 在 CPU 上训练；原 F 分数来自 cuda:0 冻结产物，未重训 F。

详见 `identity_pre_result.json`。失败的 `run01` 仅接线检验因向掩码通道加噪声触发接口检查而中止，不作结果。正式运行为 `run02`。

## 命令与测试

```bash
python3 -m pytest -q tests/unit/test_reaka_r3_condition_views.py tests/unit/test_reaka_r3_condition_compare.py
python3 scripts/reaka_r3_condition_compare.py \
  --factorlab-root "/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab" \
  --output-dir "/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab/tmp/LCL-R3-COND-20260906-01/run02"
```

- 视图测试：33 passed（云端既有）
- 新增 runner 测试：4 passed
- 训练/对照命令退出码：**0**
- 接线：F wrap 与原模型 loss/latent gap=0；H 对 X 值扰动 loss/latent/forecast gap=0；train 最大年=2016

## 拟合

实际 H 拟合次数：6（上限 6）

- 1430 seed 11: selected_cycle=3, canonical_loss 1.744998 → 0.812712, 2017_used_for_checkpoint_selection=False
- 1430 seed 29: selected_cycle=3, canonical_loss 1.682981 → 0.815410, 2017_used_for_checkpoint_selection=False
- 1430 seed 47: selected_cycle=3, canonical_loss 1.699262 → 0.816890, 2017_used_for_checkpoint_selection=False
- 1445 seed 11: selected_cycle=2, canonical_loss 1.745739 → 0.813038, 2017_used_for_checkpoint_selection=False
- 1445 seed 29: selected_cycle=3, canonical_loss 1.683730 → 0.812778, 2017_used_for_checkpoint_selection=False
- 1445 seed 47: selected_cycle=2, canonical_loss 1.699998 → 0.818188, 2017_used_for_checkpoint_selection=False

## 2017 已消费对照

F 的 mean rankIC 与 NOFIT 现任 K1 完全一致（1430 0.159926，1445 0.161526）。

### 1430
- status `completed_consumed_diagnostic`; support_rows=82321; support_days=49
| predictor | mean_rankic | mean_F_minus_predictor |
|---|---|---|
| `F` | 0.159926 | 0.000000 |
| `H` | 0.144053 | 0.015873 |
| `last_epsilon` | 0.050194 | 0.109732 |
| `negative_last_epsilon` | -0.050194 | 0.210120 |
| `mean10_epsilon` | -0.133221 | 0.293147 |
| `negative_mean10_epsilon` | 0.133221 | 0.026705 |
- F−H phase deltas: {'0': 0.016646, '1': 0.017555, '2': 0.012026, '3': 0.017583}

### 1445
- status `completed_consumed_diagnostic`; support_rows=82321; support_days=49
| predictor | mean_rankic | mean_F_minus_predictor |
|---|---|---|
| `F` | 0.161526 | 0.000000 |
| `H` | 0.140526 | 0.021000 |
| `last_epsilon` | 0.049098 | 0.112428 |
| `negative_last_epsilon` | -0.049098 | 0.210623 |
| `mean10_epsilon` | -0.134393 | 0.295919 |
| `negative_mean10_epsilon` | 0.134393 | 0.027133 |
- F−H phase deltas: {'0': 0.024388, '1': 0.020127, '2': 0.016336, '3': 0.023536}

描述性读取（不得升级）：

- 主量 F−H 约 +0.016 / +0.021 RankIC，四相位均为正。这是同配方、同支持上直接 X 信息包的描述性增量，不是市场经济因果。
- H 仍高于最强零拟合基准 `negative_mean10_epsilon`（0.144/0.141 vs 0.133/0.134），因此历史 epsilon 的表示学习仍解释了现任相对固定规则的大部分优势。
- 已消费 2017 review，不是 fresh OOS。无 iid p 值。未跑 E。未替换现任。

## 产物

本地：`/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab/tmp/LCL-R3-COND-20260906-01/run02/`
回传小文件在 `cloud_results/local_handoff_R3_condition_20260906/`。H 的 npy 分数与模型权重留本地，不上传。

## 未执行

可选 E、K/seed/LR 搜索、F 重训、账户重放、DataHub、2026、Actions、main 合并、生产指针。
