# REAKA P6.2 盘中 OT1--OT3 工作流

## 顺序

1. 冻结合同；
2. formal/isolated分别重建两个时钟的OT1；
3. formal/isolated生成结果前OT2候选state；
4. 主控按2009--2020自然年逐年执行、审查并封存收据；
5. formal/isolated分别完成OT2选择和OT3运输；
6. 全树验证与主控收官；
7. 停止等待K1 checkpoint。

## 命令

```bash
PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/freeze_reaka_intraday_OT1_OT3_v1.py

# 四条OT1 lane可按tree/clock独立执行
PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/run_reaka_intraday_OT1_v1.py \
  --tree formal --clock 14:30

PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/build_reaka_intraday_OT2_candidates_v1.py \
  --tree formal --clock 14:30
```

年度session不得用shell循环或批量驱动。主控必须依次单独运行：

```bash
PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/run_reaka_intraday_OT2_annual_session_v1.py \
  --year 2009
```

逐年审查至2020后，分别运行：

```bash
PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/finalize_reaka_intraday_OT2_OT3_v1.py \
  --tree formal --clock 14:30

PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/validate_reaka_intraday_OT1_OT3_v1.py

PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/close_reaka_intraday_OT1_OT3_v1.py
```

任何fit触及t、年度session读到未来年份、两个时钟互相选择、OT3预求和或formal/
isolated漂移时立即停止。通过后训练权仍为false。

