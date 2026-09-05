# REAKA Koopman 算子来源与多状态可识别性白皮书

## 一句话结论

Koopman算子与用户提供的金融数据强依赖，但用户不直接填写算子矩阵，也不负责拍板K数量。
项目必须事前允许一个有界算子数量候选，模型从收益与特征中学习具体矩阵和样本归属，最后由
可识别证据决定有效算子数。真实市场存在多状态，不保证当前数据能够观察或区分这些状态。

## 四层责任

| 层次 | 提供什么 | 不提供什么 |
|---|---|---|
| 用户金融输入 | target、horizon、cadence、universe、收益、因子、状态、执行语义 | 不填写矩阵元素，不决定optimizer或强制N |
| 论文框架 | 多算子codebook、selector、soft训练/argmax推理、Koopman损失 | 不给A股状态字典，不披露最优operator count N |
| AI/数学主控 | 将金融假设编译成有界`N={1,2,...}`候选、样本/DOF/稳定门和停止规则 | 不手写K矩阵，不用收益事后扩N，不保证K2/K3成功 |
| 模型与数据 | 学习每个`K_i`矩阵、selector和样本归属 | 不能从收益与特征都没有的状态信息中凭空生成真实K |

“K不是用户输入”只表示`K_i`矩阵和operator ID不是普通特征或人工标签；它不表示K与用户数据
无关。若用户改变因子、状态、目标期限或收益定义，latent状态、算子矩阵和可识别operator count
都可能改变。

## 必要但不充分的条件

K2/K3成立至少需要：

1. 真实市场在当前预测问题下存在多套动力；
2. 历史收益`Hy`或特征`Hx`至少一条路径含有可区分线索；
3. 当前horizon/cadence下这些线索对应不同的状态转移，而不只是不同水平；
4. 每套动力有足够独立episode和`n_k_eff/DOF`；
5. encoder/gate/latent gauge保留差异；
6. optimizer和损失尺度使selector/operators不能无代价忽略差异；
7. 多seed、时间折和扰动下仍可复演。

这些条件中任何一项失败，都可能做不出K2。失败的解释必须精确定位：

- `information_not_observed`：市场可能多状态，但当前收益/特征无可区分信息；
- `episode_or_support_insufficient`：有线索但独立episode或算子自由度不足；
- `representation_gap`：输入有线索，encoder/gate没有保留；
- `objective_or_optimizer_gap`：潜空间有线索，训练目标或求解器把它洗掉；
- `no_incremental_operator_identified`：基础设施健康但第二算子仍无独立增量。

任何失败都不得改写成“市场只有一个状态”，也不得改写成“用户数据错误”。

## K1、K2、K3怎样尝试

1. K1是最小参照；
2. 只有结果前episode、有效秩和样本/自由度支持时开放K2；
3. K2必须通过operator差异、软支撑、持续性、三seed和金融排序门；
4. K2未通过时不得直接尝试K3，因为K3只会增加未识别自由度；
5. K2通过后，K3才可以作为下一次单步容量扩展，重新生成当前参数和资源收据；
6. 不得设置“必须平均使用每个operator”的正则来伪造多状态；
7. 算子数由证据逐级解锁，不是永久项目常数。

论文投资模拟中的TopK持股数与Koopman operator count无关；项目文档必须分别使用
`portfolio_top_k`和`operator_count_N`，不得都简写成K。

## 显式条件因子与潜动力算子

显式可观察状态和因子效力状态属于输入内容；它们经feature encoder和gate进入latent `Z`，再由
`selector(Z, Hy)`影响operator选择。两者强相关但不一一对应：多个条件因子可以共同形成一个
潜动力状态，一个显式状态也可能跨多个潜动力状态。禁止把14个状态输入机械翻译成14个operator。

## 权限与终态

每次容量研究只能结束为：

- `operator_count_N_selected_retrospective`；
- `no_incremental_operator_identified`；
- `information_not_observed`；
- `episode_or_support_insufficient`；
- `representation_gap`；
- `objective_or_optimizer_gap`。

这些均不自动产生fresh-OOS、残差、账户或生产权。
