# REAKA P6.3 执行工作流

1. 运行 `freeze_reaka_intraday_K1_preflight_v1.py`，冻结上游digest、71维输入、
   K1/r0、容量根、LR网格、CPU/ROCm和权限。
2. 依次对 `formal/isolated x 1430/1445`运行
   `materialize_reaka_intraday_K1_input_v1.py`。任何已存在输出都fail closed，不覆盖。
3. 先验证双树逐字节一致，再对每个时钟运行
   `run_reaka_intraday_K1_preflight_v1.py`。该命令只读历史输入，不读target值。
4. 运行 `validate_reaka_intraday_K1_preflight_v1.py`。它复算digest、相位、样本、
   参数数量、LR右截断、后端入选和权限，并执行ruff/pytest。
5. 只有validation report为passed时才运行
   `close_reaka_intraday_K1_preflight_v1.py`。关闭后不得自动训练，必须等用户审阅。

失败时保留当前回执，新建incident后从冻结合同重跑受影响的整步；不得修改
已读结果的容量或LR参数来追求通过。
