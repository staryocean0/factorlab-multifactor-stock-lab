# REAKA 多因子选股模型装配 V2 白皮书

## 装配边界

本文件负责把已经冻结的金融产品、因子和可观测条件编译成论文模型输入与后续容量研究顺序。它不负责发现新因子，不负责手工命名潜状态，不负责决定 operator 数量。

## 从金融输入到模型输入

```text
历史收益 y
  -> return encoder -> H_y

PIT 因子 + availability + reliability + S_obs/条件交互
  -> feature encoder -> H_x

H_y 与 H_x
  -> feature-controlled gate -> Z
  -> selector(Z, H_y) -> alpha_i / argmax
  -> 模型学习的 K_i
```

`S_obs` 可作为全市场广播条件、因子交互或 gate 可见上下文；具体方式必须在 Stage5 结果前冻结并做消融。禁止把 `S_obs` 状态标签直接写成 operator ID，禁止为每个外部状态手工创建一个 `K_i`。

## 当前 Stage 顺序

1. Stage0 冻结产品、时钟、成本和证据边界；
2. Stage1–2 冻结因子身份及长期/条件/跟随三出口；
3. Stage3 冻结 `S_obs` 定义和支持；
4. Stage4 验证 `S_obs×factor` 机制；
5. Stage5 冻结输入张量、交互、mask、gate 可见性和中性回退；
6. Stage6 从零训练 matched K1 基线与后续有界 N 候选；
7. operator admission 选择 `N_effective`；
8. residual 从零到简单再到 diffusion；
9. score 冻结后依次执行 SSA 与 A0-A7。

## 状态如何进入但不接管 K

用户提出“上涨时增强指数、下跌时减弱指数、横盘时增强行业”是金融机制。Stage4 负责检验这个条件机制，Stage5 负责把它表示为输入交互或有界上下文。它可以改变模型学习出的 `Z`、selector 和 `K_i`，但不预先规定这些对象的数量或身份。

## 验收

模型必须证明完整条件与中性条件的反事实差异、gate 确实使用条件、排序没有被输入装配洗掉。operator 数量仍须独立通过 K1→K2→K3 容量链；外部状态的 episode、类别数或金融名称不得替代这条训练后证据。
