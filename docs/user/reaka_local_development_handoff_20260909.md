# REAKA 本地开发接管提示词与项目进度（2026-09-09）

> 用途：把 `staryocean0/factorlab-multifactor-stock-lab` 的 REAKA / 多因子策略研究从云端继续迁回本地 FactorLab 开发。  
> 云端交接基准分支：`codex/reaka-foundation-audit-20260905`  
> 云端交接基准 HEAD：`267bdcdb01599a2c7edd859f1b9baadcd40a414e`  
> PR：`https://github.com/staryocean0/factorlab-multifactor-stock-lab/pull/1`

## 1. 给本地 AI 的提示词块

将下面整段原样交给本地 AI / Codex。它是执行提示词，不是重新讨论方案的邀请。

```text
你现在接管本地 FactorLab 仓库中的 REAKA / 多因子选股项目。

云端权威仓库：
staryocean0/factorlab-multifactor-stock-lab

云端开发分支：
codex/reaka-foundation-audit-20260905

云端迁移基准 HEAD：
267bdcdb01599a2c7edd859f1b9baadcd40a414e

PR：
https://github.com/staryocean0/factorlab-multifactor-stock-lab/pull/1

用户要求：直接继续执行，不要从头重新设计，不要重复询问已经明确的信息。先读取实际本地仓库、Git 状态和本地旧策略材料，再继续 Phase II。

=== 一、接管前先做实际环境核对 ===

1. 在本地 FactorLab 仓库根目录记录：
   - pwd
   - git rev-parse HEAD
   - git branch --show-current
   - git status --short
   - git remote -v
2. fetch 云端分支，确认本地是否已包含云端迁移提交。
3. 不得把 dirty/untracked 本地旧策略文件冒充 Git HEAD 内容；凡用于身份恢复的本地文件都按实际字节计算 SHA256。
4. 若本地已有比云端更多的旧策略源码、配置、pointer、账户合同、历史 manifest、checkpoint metadata 或用户实际使用记录，优先把它们作为 Phase II 身份恢复证据；不要为了“与云端一致”而删除本地证据。

=== 二、项目总路线 ===

总路线只有两阶段：

Phase I：验证新 REAKA 实验室数学成立性及金融实现能力。
Phase II：用已经通过 Phase I 的新实验室重新开发旧实验室策略。

Phase I 已正式 PASS，但带明确证据边界：
- 数学成立性 PASS；
- 金融实现能力 PASS；
- 不代表所有 optional market/size/industry 因子已 PIT 认证；
- 不代表 fresh OOS；
- 不代表 production authority；
- 不代表已证明净账户 alpha 或交易可实现性。

因此不要重做 Phase I，也不要重新把 R3/TIMEISO/XFINE/INFOCLOCK 变成主线。

=== 三、当前 Phase II 进度 ===

Phase II 已经启动，当前任务是恢复旧策略精确身份并建立等价基线。

云端已经完成：

1. `docs/ops/phase1_lab_validation_20260908.md`
   - Phase I PASS；
   - 当前主金融目标按 H20 股票横截面 ranking candidate 理解；
   - residual-only 不能自动等于完整产品目标。

2. `docs/ops/phase2_baseline_spec_20260908.md`
   - Phase II semantic baseline 已冻结。

3. `docs/ops/old_strategy_identity_manifest@0.1.json`
   - 已从云端 artifact / registry / history 提取第一版旧策略身份；
   - canonical executable policy 仍未唯一恢复；
   - 已确认 V4 是 common root；
   - V5、V6、old V7 是从 V4 并行分叉，不是 V4->V5->V6->V7 继承链；
   - old V7 因重新选择 V5 behavior 对 clean isolated branch 无效；
   - V6 repeat audit 与 V2 account-equivalent、且低于 V5，但这不能证明 V5 就是 canonical policy；
   - 历史项目执行合同要求 causal fill、raw/PIT fill view、T+1 与 costs；
   - exact score / universe / TopN / rebalance / cost / benchmark / canonical factor membership / CloudRidge S_obs formula 仍需本地权威材料恢复。

4. `docs/ops/core_spatial_h20_lineage_manifest@0.1.json`
   - `CORE_SPATIAL_H20` authority count = 48；
   - `baseline_score` 是 transparent teacher，不是 factor #49；
   - current authority 不支持“48+2 正式核心输入”这种说法；
   - optional market/size/industry/context 不自动属于 48 core；
   - 当前仅证明 48 个身份整体存在，尚没有云端逐项权威清单把每一个 factor 映射到 position/source/Stage6 tensor position；
   - 不得用 general factor registry 猜成 48 个 paper-core member。

=== 四、你现在首先要执行的本地任务 ===

A. 恢复 canonical old strategy executable identity。

尽最大可能从本地真实材料确定：
- canonical policy id/version/name；
- authority pointer / current pointer / 用户实际使用证据；
- V4 common root 精确实现路径、版本、SHA256；
- 预测/排序经济对象；
- label horizon；
- score 方向、公式、normalization/zscore/rank/clip；
- stock universe 与 eligibility/filter；
- benchmark；
- TopN / selection rule；
- weighting；
- rebalance cadence；
- blocked-buy backfill/cash；
- sell/hold；
- decision clock；
- fill clock / fill price；
- T+1；
- costs；
- account initial value（若属于历史身份）；
- canonical policy 是否实际使用 market/index、size、industry、paper/core factor、financial epsilon、CloudRidge S_obs 或其他 context。

若有多个候选 canonical policy，全部列出，不得根据历史收益自动择优。

B. 恢复 CloudRidge `S_obs` 精确公式（仅当 canonical policy 或 common root 实际依赖它）。

必须从实际源码/配置恢复：
- exact input sequence；
- previous completed calendar month 边界；
- 1 sigma 窗口及统计对象；
- trend/sign 编码；
- continuous/discrete；
- missing rule；
- source path + SHA256。

如果找不到，继续写 `formula_identity: not_found`，禁止猜公式。

C. 尝试闭合 `CORE_SPATIAL_H20` 48-member lineage。

优先寻找：
- frozen member manifest；
- task tensor manifest；
- Stage5 freeze artifact；
- Stage6 tensor manifest；
- 或任何明确序列化全部 48 identity + order 的等价权威文件。

只有拿到真实证据后，才能把：
`resolved_exact_member_count=0`
升级，并逐项记录：
`position -> factor_id -> paper_identity -> source_artifact/digest -> implementation_mapping -> stage6_position -> validation_status`。

绝对不要为了凑满 48 行而使用 placeholder 名称，也不要把 factor_specs.py/Alpha158 中的普通 registry 因子强行对应到 48 core。

=== 五、身份未闭合前禁止的事情 ===

在 canonical old policy executable identity 未审阅闭合前，不要：
- 新策略训练；
- retrain / retune；
- 从 consumed history 重选赢家；
- 新 R3 24-job scoring；
- 用 V5/V6 历史表现反推 baseline；
- account promotion；
- production pointer 修改。

允许做：
- Git history / local source / config / manifest / receipt 读取；
- SHA256；
- 小型只读 metadata parser；
- 身份 manifest 补全；
- source closure；
- 不依赖新模型训练的文档/测试/接口修复。

=== 六、建议首先阅读 ===

1. `CURRENT.json`
2. current manifest 指向的 takeover route
3. `docs/ops/reaka_research_mission.md`
4. `docs/ops/phase1_lab_validation_20260908.md`
5. `docs/ops/phase2_old_strategy_redevelopment_20260908.md`
6. `docs/ops/phase2_baseline_spec_20260908.md`
7. `docs/ops/old_strategy_identity_manifest@0.1.json`
8. `docs/ops/core_spatial_h20_lineage_manifest@0.1.json`
9. `docs/ops/cloud_local_communication_P2_old_strategy_identity_20260908.md`
10. `docs/user/reaka_multifactor_current_workflow_v1_4.md`

按任务需要再读 whitepaper / code / tests；不要从 README 开始重新理解整个项目。

=== 七、本地完成身份恢复后的输出 ===

更新或新增一个本地身份回执，至少包含：
- local HEAD / branch / worktree；
- exact source files；
- tracked/dirty/untracked；
- SHA256；
- canonical policy 是否唯一确定；
- old strategy identity 完整字段；
- unresolved dependencies；
- CORE_SPATIAL_H20 lineage 恢复进度；
- 明确声明本轮 training/inference/backtest selection 数量。

如果身份闭合，则下一步才是：
“把同一金融任务映射到通过 Phase I 的新 REAKA 实验室，先重建等价 baseline，再研究新实验室增量”。

=== 八、必须一直保留的证据边界 ===

fresh_oos = false
production_authority = false

2021-2025/2021-2026 已消费证据不能重新包装成 fresh OOS。

不要重新设计一套新的总纲；直接从当前 Phase II 身份恢复继续执行。
```

## 2. 云端交接时项目真实进度

- Phase I：`PASS`，但不授予 fresh-OOS / production authority。
- Phase II：已开启。
- Phase II semantic baseline：已冻结。
- 云端旧策略身份恢复：已形成 `old_strategy_identity_manifest@0.1`，但 canonical executable identity 仍 unresolved。
- `CORE_SPATIAL_H20`：48-core authority/count 已确认；逐项 48-member lineage 尚未从云端权威 artifact 闭合。
- 旧策略谱系：V4 common root 已确认；V5/V6/old-V7 为并行分支；不得按历史收益自动选 V5 为 canonical。
- CloudRidge `S_obs`：历史 V2 的“上一自然月 1σ，作用于 index/industry、不作用于 size”设计存在，但 exact formula identity 尚未恢复，不能猜。
- 当前正确下一步：在本地读取真实旧策略材料，恢复 canonical executable identity 与 source hashes；然后再开始新实验室等价 baseline rebuild。

## 3. 这次迁移对仓库各类材料的更新判定

| 类别 | 是否需要因“迁回本地”而更新 | 本次处理 |
| --- | --- | --- |
| 顶层导航 / current manifest | 是 | 新增下一版 current manifest，并把本 handoff 设为本地接手入口 |
| Phase II 状态 / 研究资料 | 是 | 新增 2026-09-09 Phase II state，记录云端部分身份恢复已完成、执行主场迁回本地 |
| Phase II task / baseline spec | 否 | 研究任务与基线语义未改变，继续作为权威材料 |
| 研究总纲 | 否 | Phase I -> Phase II 的目标和顺序未改变 |
| 白皮书 | 否 | 没有新的数学、金融或模型语义变更 |
| 算法/模型/账户代码 | 否 | 本次只是执行地点迁移，无算法行为变化 |
| 测试 | 否 | 没有代码行为变化，不制造无意义测试改动 |
| 通用 workflow | 否 | workflow 已允许“数据在本地执行 + 小回执回传”；无需把一次项目迁移写成新的通用规则 |
| 历史 receipts / evidence | 否 | 保持不可变，不重写历史证据 |

## 4. 云端停止点

本 handoff 完成后，云端不应自行启动新训练、调参、candidate selection 或账户晋级。云端仓库继续作为版本化研究资料和证据索引；本地 FactorLab 成为下一阶段主要执行环境。

`fresh_oos=false`  
`production_authority=false`
