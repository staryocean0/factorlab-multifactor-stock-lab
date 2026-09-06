# REAKA P6.4.1 双时钟配对归因工作流

1. 运行 `freeze_reaka_intraday_K1_clock_attribution_v1.py`，冻结A/B两配置、四格、已有控制格digest、
   2011--2017边界和诊断指标；2018与账户关闭。
2. 分别对 `formal/isolated × 1430_B/1445_A` 运行
   `run_reaka_intraday_K1_clock_missing_cell_v1.py`。控制格不得重训。
3. 对formal和isolated分别运行 `run_reaka_intraday_K1_clock_attribution_v1.py`，它从四格checkpoint物化
   一步/recursive K、三种子集成扰动、2017排序和2×2连续效应。
4. 运行 `validate_close_reaka_intraday_K1_clock_attribution_v1.py`，检查双树、源闭包、予测源码只用一次K、
   数据边界、质量门和连续归因，然后写数学门语义合同和controller acceptance。

本工作流不选新配置、不打开2018、不运行账户，完成后必须停在P6.5之前。
