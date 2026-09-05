# REAKA 多因子选股六位一体基础设施白皮书

## 目的

基础设施的价值不是文件数量，而是把一次金融意图稳定编译为可执行、可验证、可交接的研究状态。用户或 AI 不应靠遍历历史文件重建上下文；current manifest 必须给出最小必读闭包、每份文件的职责和唯一下一动作。

## 六个表面的职责

### 文档

`docs/user` 使用命令式口径，回答“现在在哪、先读什么、运行什么、何时停”。不得定义新数学对象或宣布科学结果。

### 白皮书

`docs/ops/*whitepaper.md` 使用解释性口径，回答“为什么、对象是什么、数学如何对应金融意图、什么不能推出”。每个结论必须标明输入、学习、诊断或权限身份。

### 机器合同

`docs/ops/*.json` 使用封闭枚举和布尔权限，冻结对象、stage、输入、输出、source closure 与 digest。机器合同不得用自然语言模糊 `S_obs` 与 `S_latent`。

### 代码

`src` 实现领域对象和 fail-closed 不变量。代码不得读取未进入 current manifest 的历史文件作为默认权威，也不得把类默认值当论文参数。

### 测试

`tests` 同时覆盖正例、真实事故负例、跨文档冲突和权限升级。仅证明 JSON 能解析不算基础设施测试。

### 脚本

`scripts` 只负责 build/freeze/run/validate/close/publish。脚本调用代码、读取合同并产出收据；不得内嵌另一套领域语义。

## 文档类型不可互相冒名

| 类型 | 语气 | 首屏必须有 | 禁止 |
|---|---|---|---|
| current workflow | 命令式 | 当前状态、必读顺序、唯一下一动作、停止点 | 历史长日志 |
| whitepaper | 解释式 | 对象、公式、责任、能/不能证明 | current 状态指针 |
| contract | 机器式 | schema、stage、scope、authority、digest | 未限定的“状态有效” |
| result | 事实式 | 输入、执行、结果、限制 | 改写上游定义 |
| handoff | 恢复式 | current manifest、语义 checksum、开放/关闭权限 | 自创下一动作 |
| history index | 索引式 | 版本与撤权原因 | current 规范权 |

## current manifest 规则

1. 首次阅读只读 manifest 标为 `required_first_read` 的文件；
2. 未列入 manifest 的 REAKA 文件默认 `historical_or_specialized_no_current_normative_authority`；
3. 专题文件只有被 current 根显式引用时才有局部权限；
4. manifest 中每个职责只能有一个 owner；
5. current authority 只能给出一个 `next_legal_action`；
6. manifest 不删除历史，而是解决“谁现在说了算”。

## 防误解门

本轮真实事故被固化为回归门：Stage3 出现 `K2_allowed`、`discrete_operator_expert_allowed`、`N_effective`，或出现外部状态到 operator 的监督映射时，validator 必须失败。handoff 若没有完整语义 checksum，或引用 manifest 外文件作为当前规范，也必须失败。
