# LCL-R3-XCOARSE-20260907-01 本地反馈

任务：LCL-R3-XCOARSE-20260907-01
执行方：本地 Codex controller
时间：2026-09-07
状态：本地已反馈；待云端复核。

## 身份与命令

- 主题仓 HEAD：`43920405fc6368620740ae1ee3c9b8c88d668413`
- FactorLab HEAD：`b39bb12f43a46b165d18db93191a669234077444`
- accepted TIMEISO run：`tmp/LCL-R3-TIMEISO-20260907-01/run01`（只读 overlay，未覆盖原 scores/store/checkpoint）
- 命令：

```bash
export FACTORLAB_ROOT="/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab"
python3 scripts/reaka_r3_x_coarse_compare.py --spec .../x_coarse_run_spec.json
```

- 退出码：**0**
- 新 fits：**6**（E only）
- F new fits：**0**
- H new fits：**0**
- 未因结果重跑；未跑细拆臂；未跑 F+M
- 未调用 Actions；未改 FactorLab 数值源码

## 结果（已消费 2018–2020，同 TIMEISO 支持）

accepted F−H 逐日重现通过。combined 主量 F−H = **0.020536824420887195**（与 TIMEISO 验收一致）。

| 对比 | combined mean | median | win days | block8 区间 |
|---|---:|---:|---:|---|
| E−H | 0.009278 | 0.007066 | 86 | [-0.0011, 0.0195] |
| F−E | 0.011259 | 0.010802 | 105 | [0.0059, 0.0173] |
| F−H | 0.020537 | 0.018540 | 112 | [0.0083, 0.0332] |

E−H 的 block 区间跨 0。1445 seed47 的 F−E 为负，已原样保留。这是有序条件增量，不是唯一可加因果归因。

## 月度 CloudRidge

`formula_identity_not_found`。未猜公式，未执行 F+M。

## 产物

回传：`cloud_results/local_handoff_R3_xcoarse_20260907/`
大 checkpoint 张量 / E scores.npz 留本地 `tmp/LCL-R3-XCOARSE-20260907-01/run01/`。

fresh_oos=false；full_pit_certified=false；production_authority=false。
