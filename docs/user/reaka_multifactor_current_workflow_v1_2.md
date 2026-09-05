# REAKA 多因子选股当前唯一工作流 V1.2

## 当前状态

Stage3 `S_obs` 支持已关闭。Stage4 机器证据已完成，当前等待用户审核指数/行业在上一自然月趋势条件下的金融机制；机器没有代签金融回执。

当前 manifest：`docs/ops/reaka_multifactor_current_manifest@1.2.json`。当前 authority：`docs/ops/reaka_strategy_authority_registry@113.0.json`。当前 succession：`docs/ops/reaka_controller_succession_audit@274.0.json`。

## 当前唯一动作

阅读 `docs/ops/evidence/reaka_v2_stage4_observable_factor_pairing_v1_20260905/advisor_interpretation_request.md`，对五个冻结机制分别作金融判断。Stage5、训练、K容量、账户和生产继续关闭。

## 不变量

`S_obs` 是用户/项目输入；`K_i` 与有效 operator 数量由后续模型和证据产生。Stage4 只能判断条件×因子机制，不能选择K或权重。
