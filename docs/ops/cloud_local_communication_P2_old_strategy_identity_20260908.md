# 云端→本地：Phase II 旧策略精确身份回收

日期：2026-09-08  
任务 ID：`LCL-P2-OLDSTRAT-ID-20260908-01`  
状态：`awaiting_local_execution`  
对应云端基线：`docs/ops/phase2_baseline_spec_20260908.md`

## 1. 任务目的

Phase I 已通过，Phase II 已进入“用新实验室重新开发旧实验室策略”。当前唯一不能由云端仓库安全唯一恢复的关键依赖，是**用户实际认可/使用的旧实验室 canonical strategy 的精确可执行身份**。

本任务只回收身份，不训练、不推理、不重新选策略、不跑新的历史赢家竞赛。

## 2. 不允许推断的事项

本地执行者不得因为：

- V5 历史上优于 V6；
- V6 与 V2 账户等价；
- 文件名或版本号相似；
- 某个旧结果看起来最优；

就自动宣布某版本是 canonical policy。

必须用实际旧源码、配置、manifest、指针、用户使用记录或等价的权威身份材料证明。

若找不到，明确写 `not_found` 或 `ambiguous`，并列出缺失依赖。禁止从收益结果逆向重构策略公式。

## 3. 执行前环境记录

在任何结论前，记录：

1. 当前本地 FactorLab 仓库绝对路径；
2. `git rev-parse HEAD`；
3. 当前分支；
4. `git status --short`；
5. 与旧策略有关的 dirty/untracked 文件。

若实际加载/使用文件是 dirty 或 untracked，必须按**当前工作区实际字节**记录 SHA256，不能把它冒充为 HEAD 中的 Git blob。

## 4. 必须回收的旧策略身份

尽最大可能从实际旧实验室材料恢复以下字段。

### A. Canonical policy authority

- canonical policy id/version/name；
- 证明其为用户实际认可/使用策略的 authority evidence；
- 若存在 strategy pointer/current pointer，记录其路径、内容身份和 SHA256；
- 与 V4/V5/V6/旧 V7 的关系；
- V4 common root 的确切实现路径/版本/SHA256（若适用）。

若存在多个可能 canonical 候选，全部列出，但不得自行择优。

### B. 金融任务

精确恢复：

- 预测或排序的经济对象；
- label horizon；
- score 正负方向；
- score 公式；
- normalization/zscore/rank/clip 等处理；
- 股票 universe；
- eligibility/filtering；
- benchmark。

### C. 组合与账户

精确恢复：

- TopN 或 selection rule；
- 权重规则；
- rebalance cadence；
- 买入受阻后的替补/现金处理；
- sell/hold 规则；
- 成本模型；
- decision clock；
- fill clock / fill price；
- T+1 或其他执行约束；
- 账户初值（如其对历史身份有意义）。

### D. 因子与条件变量角色

明确 canonical policy 中是否真的使用：

- market/index；
- size；
- industry；
- 股票横截面 paper/core factors；
- financial epsilon；
- CloudRidge 上一自然月 1σ `S_obs`；
- 其他 observable/context。

对每一个实际使用项给出来源文件、配置字段和 SHA256。不要把“某个实验分支用过”写成“canonical policy 使用”。

### E. CloudRidge `S_obs`

若 canonical policy 或其必需共同根确实依赖 `S_obs`，恢复：

- 精确输入序列；
- 1σ 的窗口定义；
- 统计对象；
- trend/sign 编码；
- continuous/discrete；
- missing rule；
- previous-completed-calendar-month 的时间边界；
- 计算源码路径与 SHA256。

如果无法从精确源码/权威配置恢复，写：

`formula_identity: not_found`

禁止猜公式。

## 5. 推荐的本地检查方式

当前仓库**没有**专用的 `reaka_p2_old_strategy_identity.py` 脚本；不要虚构该命令。

可以使用普通只读/哈希命令，例如：

```bash
git rev-parse HEAD
git branch --show-current
git status --short
rg -n "V4|V5|V6|V7|policy_id|strategy_pointer|TopN|top_n|rebalance|CloudRidge|S_obs|cost|fill" .
sha256sum <actual-file>
```

也可以用 Python 只读解析 JSON/YAML/源码。若为了整理结果需要编写一个**本任务专用的小型身份采集脚本**，可以在本地提交，但它只能做路径、字段和哈希采集，不能跑策略或选赢家。

## 6. 允许读取、不要求重跑

允许：

- 仓库 Git 历史；
- 旧源码/配置；
- 已有账户回执/报告；
- 已有小型 manifest；
- 本地工作区已有的历史策略材料。

不要求：

- 重新上传 R1/R2 大数组；
- 模型训练；
- 模型 inference；
- checkpoint reload；
- 新账户 backtest；
- R3 transfer scoring；
- GitHub Actions。

如果某个身份只有通过读取已有 checkpoint metadata 才能确定，可以只读 metadata；不要执行模型 forward。

## 7. 必须返回的目录

把小型回执提交到：

`cloud_results/local_handoff_P2_old_strategy_identity_20260908/`

至少包含：

### `local_feedback.md`

报告：

- FactorLab HEAD/branch/worktree；
- 实际执行命令与 exit code；
- canonical policy 是否唯一确定；
- authority evidence；
- V4/V5/V6/V7 谱系结论；
- score/universe/portfolio/account/clock/fill/cost 身份摘要；
- market/index/size/industry/S_obs 是否属于 canonical；
- 未找到的依赖；
- 明确声明 `0 training / 0 new inference / 0 new backtest selection`。

### `old_policy_identity.json`

建议 schema：

```json
{
  "schema_id": "factorlab.p2_old_policy_identity@1.0",
  "task_id": "LCL-P2-OLDSTRAT-ID-20260908-01",
  "status": "resolved_or_ambiguous_or_not_found",
  "canonical_policy": {},
  "authority_evidence": [],
  "common_root": {},
  "financial_target": {},
  "universe": {},
  "score": {},
  "portfolio": {},
  "execution": {},
  "factor_roles": {},
  "s_obs": {},
  "source_files": [],
  "missing_dependencies": [],
  "training_runs": 0,
  "new_inference_runs": 0,
  "new_strategy_backtests": 0
}
```

字段内容必须来自实际材料；模板不是允许填猜测值。

### `source_hashes.json`

对所有用于身份判定的实际源码/配置记录：

- absolute/local path 或仓库相对路径；
- tracked/dirty/untracked；
- SHA256；
- 若 tracked，可附 Git blob/commit。

若文件很多，只需 canonical policy 及其直接依赖的小集合，不要打包整个数据湖。

## 8. 回传后的停止点

完成身份采集后**停止**。

不要：

- 开始 Phase II 模型训练；
- 根据旧结果重选参数；
- 启动 R3 的 24 项评分；
- 自行决定 V5/V6 谁成为新基线；
- 修改 production pointer。

云端先审阅 `old_policy_identity.json`，确认等价基线的旧端身份闭合后，才会提交下一条真正的 rebuild 任务。

## 9. 证据边界

本任务是历史身份恢复，不提供 fresh OOS，也不授予 production authority。

`fresh_oos=false`  
`production_authority=false`
