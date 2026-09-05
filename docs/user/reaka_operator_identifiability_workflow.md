# REAKA Koopman 算子来源与可识别性工作流

1. 用户只声明金融问题：target、horizon、cadence、universe、收益、因子、状态和执行时钟；不得
   向用户询问operator count、矩阵、temperature、LR或epoch。
2. 主控登记收益路径与特征路径分别含有哪些状态线索；若两边均无可区分线索，只能报告
   `information_not_observed`，不能凭空建立K2。
3. 先运行无标签episode/有效秩/局部DMD/`n_k_eff/DOF`预检，再决定是否开放下一档N。
4. 按K1→K2→K3逐级执行；前一档未通过，禁止跳级。
5. 训练只学习矩阵和selector，不使用人工operator标签；显式状态可作结果前初始化或诊断，不能
   变成未声明的运行时硬路由。
6. 验收必须同时报告信息可观测性、episode支持、表示保留、目标/求解器、矩阵差异、软支撑、
   多seed与金融排序。
7. 失败使用白皮书规定的精确终态；禁止将“当前没识别出K2”写成“市场没有第二状态”。

机器入口：

```bash
PYTHONPATH=src python scripts/factor_rotation/build_reaka_operator_identifiability_v1.py
PYTHONPATH=src pytest -q tests/unit/test_reaka_operator_identifiability_v1.py
```

该工作流只建立治理和防漂移门，不训练模型、不评分、不运行账户。
