# REAKA 多因子选股六位一体基础设施系统优化执行计划

## 0. 计划状态与边界

- 计划身份：`REAKA_MULTIFACTOR_INFRASTRUCTURE_SYSTEM_REBUILD_V1`
- 责任事项：`bd://fl-r3yr2`
- 目标：让第一次进入项目的用户或 AI 在有限、明确、可验证的阅读路径内形成正确认知，并能从唯一 current 权威继续工作。
- 本轮允许：文档、白皮书、机器合同、治理代码、测试、工作流和脚本的基础设施建设；修正 current 权威与交接入口。
- 本轮禁止：策略训练、收益重算、账户执行、因子/模型/参数选择、指针修改和生产授权。
- 历史原则：不静默改写已封存科学合同；使用 successor、撤权回执和 current manifest 保留历史可查询性。

## 1. 为什么要建设六位一体基础设施

六个表面不是重复写同一件事，而是同一研究意图在不同责任层的投影：

| 表面 | 唯一职责 | 不得承担 |
|---|---|---|
| 文档 `docs/user` | 告诉用户/执行者从哪里进入、按什么顺序做、何时停 | 发明数学定义、保存科学结果、暗改权限 |
| 白皮书 `docs/ops/*whitepaper.md` | 解释金融问题、数学对象、设计理由、反例和边界 | 冒充当前机器状态或执行收据 |
| 机器合同 `docs/ops/*.json` | 用确定字段冻结身份、输入、输出、权限、版本和 digest | 用长篇叙述替代可验证条件 |
| 代码 `src` | 实现领域对象、纯函数、不变量和 fail-closed 规则 | 读取文档外的隐含默认权威 |
| 测试 `tests` | 用正例、负例和跨层反例证明规则不能被误实现 | 只测试 happy path 或复述实现 |
| 脚本 `scripts` | 冻结、执行、验证、关闭与发布；连接六个表面 | 承担领域语义或绕过代码/合同 |

六位一体的共同结果应是：任一入口都能追溯到同一个语义对象、同一个 current 闭包和同一组权限；任何一个表面漂移，validator 必须阻断，而不是依赖下一位 AI 主动发现。

## 2. 当前审计结论

### 2.1 资产很多，但 current 根没有被压缩

未归档顶层当前可见约有：

- `docs/ops`：917 个 `reaka*` 文件；
- `docs/user`：185 个 `reaka*` 文件；
- `src/factor_lab/factor_rotation`：228 个 `reaka*` 源码；
- `scripts/factor_rotation`：528 个 `reaka*` 脚本；
- `tests/unit`：259 个 `reaka*` 测试。

这些数字不等于 2,117 个 current 规范资产；大部分是历史证据、单步实现和旧版本。但项目没有一张 fail-closed 的 current manifest，导致同层文件都可能被读者误认为当前权威。

### 2.2 正确认知存在，但控制路径自相矛盾

`reaka_operator_identifiability@1.0` 已正确冻结：

- 用户不提供 `K_i` 矩阵，不拍板 operator count；
- 模型学习矩阵、selector 和样本归属；
- 可观测状态不等于潜动力状态；
- K2 失败不等于市场只有一个状态。

但 `state_factor_research_state_machine@1.0`、旧 V2 handoff 及 Stage3 V1 successor 又允许外部状态 episode 直接产生 `discrete_operator_expert` 或禁止独立 K。更近的执行文本覆盖了更深层的正确白皮书，形成了语义冲突。

### 2.3 同一个词承担了不同对象

当前至少混用了：

- `S_obs`：用户/项目输入的可观测条件或状态；
- `S_factor`：因子在条件内外的效力画像；
- `Z` / `S_latent`：encoder 与 gate 学出的潜在表示；
- `K_i`：模型学习的潜空间转移矩阵；
- `N_max`：结果前冻结的 operator 数量搜索上限；
- `N_effective`：训练与可识别性证据选出的有效 operator 数量；
- `portfolio_top_k`：组合持股数，与 operator count 无关。

只写“状态”或“K”不足以维持跨文档语义。

### 2.4 入口、过程、结果和历史没有严格分工

`ai-readme`、`docs/00-index`、`docs/ops/README`、专题白皮书和 succession 都积累了“当前”段落。历史结果继续停留在 current 目录并不可避免，但它们必须由 manifest 明确降权，而不是要求读者靠日期和版本号猜测。

## 3. 目标架构：从产品到生产的唯一语义链

```text
产品与金融目标
  -> 数据/时钟/成本/证据边界
  -> 因子身份与三出口
  -> S_obs 可观测条件定义与 PIT 支持
  -> S_obs × factor 金融机制和条件证据
  -> 输入装配：S_obs 如何进入 Hx/gate/显式交互
  -> encoder/gate 学习 Z
  -> 有界 N 候选下训练 K_i 与 selector
  -> K1 -> K2 -> K3 逐级容量准入，得到 N_effective
  -> residual 从零到简单再到 diffusion
  -> 冻结 score identity
  -> SSA
  -> A0-A7 完整账户
  -> fresh challenge / production authority
```

依赖只允许从左向右。Stage3 可以阻断一个 `S_obs` 输入身份，却不能选择或否决 `N_effective`；K 容量研究可以发现当前输入无法区分第二套动力，却不能否定用户状态的金融存在性。

## 4. current 规范闭包

系统重构后，首次阅读只允许以下角色进入 current 闭包：

1. 顶层入口：一页当前状态、唯一下一动作和必读顺序；
2. 语义本体：对象、所有者、输入/学习身份、允许产生的裁决；
3. 六位一体职责合同：每类文件负责什么、用什么语气、不得说什么；
4. 产品与执行合同：目标、频率、时钟、成本、股票池、证据边界；
5. 因子研究合同：因子身份、长期/条件/跟随三出口；
6. 可观测条件合同：`S_obs` 的 PIT、episode、持续和覆盖；
7. 输入装配合同：`S_obs` 怎样进入模型输入或显式交互；
8. 论文模型合同：`Z`、selector、`K_i`、residual 和 decoder；
9. operator 容量合同：`N_max`、K1→K2→K3、有效 K 裁决；
10. 训练后合同：SSA 与 A0-A7；
11. current authority：版本、阶段、开放权限和唯一下一动作。

其他 REAKA 文件即使仍位于顶层目录，只要不在 current manifest 中，就默认属于 `historical_or_specialized_no_current_normative_authority`。专题 current 文件只能在上述根显式引用时获得局部权限。

## 5. 文档类型的语气和口径

### 5.1 用户文档

- 使用命令式、短句和检查表；
- 首屏写“现在在哪、下一步是什么、何时必须停”；
- 只引用 current manifest 中的规范根；
- 不复制长篇历史结果；历史从单独索引进入；
- 不用“状态”“K”这类未限定缩写，必须写 `S_obs`、`S_latent`、`operator_count_N` 或 `portfolio_top_k`。

### 5.2 白皮书

- 先定义对象和责任，再写原因和公式；
- 每项结论标明 `input / learned / diagnostic / authority`；
- 每节必须写“能证明什么、不能证明什么”；
- 反例与失败模式必须和正例同级；
- 历史结果只作例证，不承担 current pointer。

### 5.3 机器合同

- 字段必须可机械验证，禁止含糊的 `state_allowed=true`；
- 每个裁决带 `object_id`、`owner`、`stage`、`scope_of_claim`；
- 权限默认 false，只有 current authority 显式开放；
- 必须区分 `N_max_candidate_boundary` 与 `N_effective_selected`；
- 必须声明哪些对象明确超出本阶段权限。

### 5.4 结果与交接

- 结果只报告已执行事实，不改写上游本体；
- handoff 必须由 current manifest、authority 和语义 checksum 生成或验证；
- handoff 开头必须列出六条语义断言，回答错误不得执行；
- 外部 AI 不得发布 controller acceptance。

## 6. 分阶段实施

### Phase A：计划与清单

交付：

- 本 Plan；
- 当前资产审计报告；
- current/historical/specialized 三类判定规则；
- 不搬迁历史文件、不读取收益、不运行训练的边界。

验收：Plan 可从 `ai-readme` 和 `docs/00-index` 找到，后续每步绑定本 Plan digest。

### Phase B：语义本体与六位一体合同

新增：

- `docs/ops/reaka_multifactor_semantic_ontology_whitepaper.md`；
- `docs/ops/reaka_multifactor_semantic_ontology@1.0.json`；
- `docs/ops/reaka_multifactor_six_surface_infrastructure_whitepaper.md`；
- `docs/ops/reaka_multifactor_current_manifest@1.0.json`；
- `docs/user/reaka_multifactor_current_workflow.md`。

本体至少冻结 `S_obs/S_factor/Z/S_latent/K_i/N_max/N_effective/residual/score/account`，并给出所有者、形成方式、允许裁决和禁止推论。

### Phase C：状态/条件/K 分层 successor

发布新版本而不改写历史：

- `state_factor_research_state_machine@2.0`：Stage3 只产生 observable-context support，不产生 operator count 裁决；
- 新 rollback 说明：状态输入改变仍回 Stage3，但原因是输入身份和条件证据失效；
- 新 operator capacity 连接：只有训练后的 K 准入链选择 `N_effective`；
- 旧 Stage3 V1 的 PIT、月份、转移和持续数据保留，K 相关结论撤权。

### Phase D：入口与交接重写

- 发布 V2 handoff successor；
- `ai-readme`、`docs/00-index`、`docs/ops/README` 只指向一个多因子 current 入口；
- 发布新的 round/authority/succession successor，当前停在基础设施修复完成后的用户 checkpoint；
- 不自动开放 Stage4、训练或账户。

### Phase E：代码、脚本和测试硬门

新增治理代码，至少检查：

```text
observable_state_equals_latent_operator_state = false
user_supplies_operator_count = false
model_learns_operator_matrices = true
model_learns_operator_assignments = true
stage3_may_select_operator_count = false
effective_operator_count_is_post_training_evidence = true
portfolio_top_k_is_operator_count = false
```

validator 必须拒绝：

- Stage3 输出 `K2_allowed`、`discrete_operator_expert_allowed` 或 `N_effective`；
- `S_obs` 被当作 operator supervision label；
- 外部 episode 数直接映射 operator 数；
- K2 失败被写成“市场只有一个状态”；
- handoff 引用不在 current manifest 中的文件作为当前规范权威；
- 同时存在两个 current 下一动作。

### Phase F：验收与关闭

- source closure、canonical digest、链接、Ruff、类型和单测通过；
- 运行六条语义 checksum 正例与完整负例矩阵；
- 生成 current manifest validation 和 controller acceptance；
- 更新 bead；
- 报告剩余历史迁移债务，但不在本轮批量归档或删除。

## 7. 文件职责矩阵

| 主题 | current 责任文件 | 只负责 | 明确不负责 |
|---|---|---|---|
| 当前入口 | `reaka_multifactor_current_workflow.md` | 阅读顺序、当前阶段、下一动作 | 数学推导、结果存档 |
| 产品 | `reaka_product_driven_multiscale_research_whitepaper.md` | 金融产品、频率与目标矩阵 | K 数量、模型参数 |
| 因子 | `reaka_factor_discovery_three_pathway_whitepaper.md` | 因子身份与三出口 | 潜状态、operator 标签 |
| 语义 | 新 ontology | 全部对象与所有者 | 单次结果 |
| 可观测条件 | state machine v2 | `S_obs` 的因果支持与条件角色 | `K_i`、`N_effective` |
| 输入装配 | state-factor joint successor/桥 | `S_obs` 进入 `Hx/gate/interaction` 的方式 | 手工 operator 映射 |
| 论文模型 | REAKA 论文/实现白皮书 | encoder、gate、selector、K、residual、decoder | A股状态字典、作者未披露参数 |
| K 容量 | operator identifiability + K admission | 有界 N、训练后逐级选择 | 用户拍 K、外部状态一一映射 |
| 参数 | parameter governance | 参数来源与结果前实例化 | 用默认值冒充作者参数 |
| 策略科学 | SSA | 固定 score 的信号诊断 | 账户优化、模型重训 |
| 账户 | A0-A7 | 真实账户、成本、持仓和报告 | 反向训练模型 |
| 权威 | round/authority/succession | current 状态和唯一下一动作 | 解释数学原理 |

## 8. 验收标准

本计划只有在下列条件同时满足时完成：

1. 新 AI 只读 current workflow、ontology、manifest 和对应阶段文档即可回答对象所有权；
2. 任意文档都不能合法推导 `external state episode count -> operator count`；
3. current manifest 之外的文件默认没有当前规范权；
4. 六个表面均有唯一职责和 source closure；
5. 机器负例覆盖本次真实误解，而不是只测试 JSON 格式；
6. 旧科学证据可查询但不能静默恢复 current 权威；
7. 当前下一动作唯一，且本轮结束时仍不开放策略训练、账户或生产。

## 9. 停止与升级规则

- 若发现现有 current 合同无法通过 successor 纠正而必须改变科学结果，停止并请求用户确认；
- 若只是撤销越权解释而保留原始测量，可在本基础设施任务内发布 authority correction；
- 不因文档数量大而批量移动或删除；历史归档另立任务；
- 完成本计划后先向用户交付新入口和语义验收结果，再决定是否恢复 REAKA V2 Stage4。
