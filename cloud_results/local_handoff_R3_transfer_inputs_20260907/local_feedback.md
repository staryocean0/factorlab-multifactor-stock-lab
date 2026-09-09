# LCL-R3-TRANSFER-INPUT-20260907-01 本地反馈

任务：`LCL-R3-TRANSFER-INPUT-20260907-01`  
执行方：本地 Codex controller  
时间：2026-09-07  
状态：本地已反馈；待云端复核。

这是同定义特征输入重建，不是审计复跑，也不是 24 项跨期评分。

## 身份

- 主题仓执行时 HEAD：`5cc8925ff48f142ae1e44705c64013ca3bb0b486`
- FactorLab HEAD：`b39bb12f43a46b165d18db93191a669234077444`（未改数值源码）
- 实际加载的生产器是工作区文件，不是该 HEAD 的入库身份。`producer_sources.json` 记录了 `__file__` 与 SHA256。
- 原 TIMEISO store / 选型 / normalizer 只读。原 24 个 checkpoint 未重验未重载。

## 本地新增桥接（云端未实现）

`scripts/reaka_r3_transfer_source_bridge.py` + `tests/unit/test_reaka_r3_transfer_source_bridge.py`

- 先固定 TIMEISO 3982 股票原顺序，再从价格缓存取前 3982 列（缓存是 incumbent prefix，不是先 5894 再切列）。
- 日历截到 **2025-12-31**，丢弃 2026。
- 历史前缀六组数组从已验收 TIMEISO store **复制**（`reused_accepted_arrays`），不是独立全历史重建。
- 尾部：原配方 H20 历史收益、成员等权载体、因果基底、滚动 OLS 暴露/reliability、冻结 2016 工具滤波。滤波在「原 OT 基底至 2020 + 新基底 2021–2025」上连续运行，不从 2021 硬重启。
- 未使用 `reaka_residual_only_post2020_extension_v1_2009_2026` 残差成品切列。
- 未读取未来标签做特征；OLS 的 future_returns 填 NaN。
- 未重选工具、未重估 normalizer、无网络训练/推理/checkpoint reload。

有界价格源：`reaka_current_generation_blackbox_gpu_cache_v2_2007_2026` 的 decision_close，按 3982 原队列截到 2025。  
P6 `decision_close` / `history_h20_raw` 前缀比对 maxdiff=0。  
成员：CloudRidge append-only CSV 与 condensation parquet，按名称映射到 3982，并丢弃 2026 as_of。

## 命令

```bash
python3 -m pytest -q tests/unit/test_reaka_r3_transfer_inputs.py tests/unit/test_reaka_r3_transfer_source_bridge.py
# exit 0；58 passed

python3 scripts/reaka_r3_transfer_source_bridge.py \
  --output-root .../tmp/LCL-R3-TRANSFER-INPUT-20260907-01/source_bundles
# exit 0；source_bundles_prepared

python3 scripts/reaka_r3_build_transfer_inputs.py --spec .../transfer_run_spec.json
# exit 0；prepared_features_only_not_scored
```

- 新网络 fits = **0**
- 新 inference = **0**
- checkpoint reload = **0**
- 滚动 OLS 决策点 = **486**（每时钟 242 个新 D5 + 1 个 2020 边界点用于把残差窗续进 2021）
- 未调用 Actions；未启动 24 项评分

## 产物规模

两时钟相同：calendar 4618 日（2007-01-04–2025-12-31），3982 股票，14 因子，71 通道。  
新 D5=242。预测行 931677 / 242 日；成熟候选 916077（`decision+20 < len(calendar)`，不是有限标签）。  
原 2011–2020 行 853732 保留。  
六组历史前缀 exact value+NaN 比较通过。`prefix_check_is_independent_producer_replay=false`。

首个新 D5 2021-01-08：universe 3982，included 3386，history_missing 596。  
末个 2025-12-29：included 3901，history_missing 81。缺数据按原支持规则排除，不按表现删样本。

## 未知

- PIT / 首次可读时间仍 unknown。
- 源码快照不是历史 HEAD 认证。
- 前缀复制成功不能写成独立重建成功。
- 滤波继承的是原 OT 基底至 2020，不是把前缀 OLS 再跑一遍。

## 回传

`cloud_results/local_handoff_R3_transfer_inputs_20260907/`：local_feedback、run_spec、result、bridge_result、两时钟 bundle/producer_sources/manifest/daily_support、桥接脚本与测试、测试日志。  
大数组留本地 `FactorLab/tmp/LCL-R3-TRANSFER-INPUT-20260907-01/`。

完成后停止：不评分、不重选 seed/工具、不加臂、不猜 CloudRidge 公式。
