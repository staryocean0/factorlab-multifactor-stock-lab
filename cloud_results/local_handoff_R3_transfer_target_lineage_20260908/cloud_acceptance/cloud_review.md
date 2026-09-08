# R3 transfer target-lineage 云端验收与最小修复

日期：2026-09-08。已审提交：`2329b24161649afc4f176bbac990a0de920565b3`。

## 裁决

`LCL-R3-TRANSFER-TARGET-LINEAGE-20260908-01` **completed_with_limits**。本地按门执行：8项诊断测试通过、自检通过、正式只读诊断exit 0；模型fit=0、checkpoint reload=0、score=0、sidecar=0、2026 target=false、Actions=false。

两时钟 `historical_artifact_replay_with_current_OT_code` 均通过：在旧P6 raw + 旧factor basis上，当前OT代码对5个结构成熟锚点重放 beta/reliability/available、epsilon_history、epsilon_future 的max abs error均为0，support mismatch=0。因此不需要恢复另一份历史OT源码才能表达旧target语义。

第一处分歧均为 `raw_future_H20_path_diverges`：1430 max约0.017076，1445 max约0.020367，支持一致。旧/重建history basis一致到约1e-16；future basis后续偏约1e-3，属于已偏离raw future输入之后的下游差异。延伸重建epsilon_future偏约0.017–0.020，与前轮label gate失败一致。

## 已恢复的精确P6 future target定义

R2独立审计 `scripts/reaka_r2_local_audit_v1.py` 明确重建并验证：

- `history_h20_raw[t] = decision_close[t] / decision_close[t-20] - 1`；
- **`future_h20_raw[t] = entry_open[t+20] / entry_open[t] - 1`**。

DataHub抽样重建规则：在会话时间13:00–15:00内，decision close取timestamp墙钟时间<=决策时钟的最后一个正且有限close；entry open取timestamp墙钟时间>决策时钟且<=15:00的第一条正且有限open。14:30/14:45对应entry minute最早为14:31/14:46。该历史实现读取timestamp字符串`[11:16]`作为会话墙钟；它不是时区转换/PIT证明。

因此失败的v1 transfer label bridge把future H20从decision close直接计算，是已识别的target-definition错误。旧失败脚本和回执保留，不倒填修改。

## 最小修复

云端新增：

- `scripts/reaka_r3_transfer_target_source_bridge.py`：复用accepted P6旧前缀，仅从DataHub按旧entry-open事件规则生成2021–2025尾部；用5个结构成熟旧锚点及其t+20日全3982队列做价格/分钟/future H20门；不读取2026 target月份。
- `scripts/reaka_r3_transfer_label_bridge_v1_1.py`：只接受已通过上述门的target-source bundle，以P6 entry-open future raw构建future basis/residual，并再次重放TIMEISO epsilon_future锚点。
- `tests/unit/test_reaka_r3_transfer_target_source_bridge.py`：事件选择、future公式、尾部成熟、容差、旧R2公式绑定、successor无模型评分入口等反例。
- `docs/ops/cloud_local_communication_R3_transfer_target_entryopen_20260908.md`：下一本地任务。

新本地任务：`LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01`。任务只生成target source和successor label bundles；即使全部通过也停止，不建立sidecar、不运行archived-score preflight或24项评分。云端验收后再恢复原transfer-eval评分阶段。

## 证据边界

恢复P6数学定义不等于PIT认证。成员历史首次可读时间及此前输入来源限制继续存在。后继2021–2025评价仍为consumed historical transfer，`fresh_oos=false`、`PIT_certified=false`、`production_authority=false`。
