# REAKA P6.1 盘中 target/fill 工作流

## 权限

本工作流已由用户开放P6后执行一个pioneer step。只允许target/fill物化；模型训练、
评分、账户和生产均为false。

## 1. 冻结合同

```bash
PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/freeze_reaka_intraday_target_fill_v1.py
```

## 2. 单月性能预检

性能预检只读取一个月、丢弃结果，不写科学产物。正式物化使用CPU并行I/O；GPU对
Parquet字符串筛选和小矩阵装配没有优势。首次8进程尝试在formal产生前因内存过度
并行终止，当前固定Arrow下午过滤加4进程；该事件不改变算法或候选身份。

## 3. 正式与隔离物化

```bash
root=output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020

PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/materialize_reaka_intraday_target_fill_v1.py \
  --output-root "$root/formal" --workers 4

PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/materialize_reaka_intraday_target_fill_v1.py \
  --output-root "$root/isolated" --workers 4
```

## 4. 验证与主控收官

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/unit/test_reaka_intraday_target_fill_v1.py

PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/validate_reaka_intraday_target_fill_v1.py

PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/close_reaka_intraday_target_fill_v1.py
```

验证器检查：

- 14:30/14:45决策价不晚于时钟；
- entry fill严格晚于时钟且不晚于15:00；
- H20历史和未来target公式逐元素零误差；
- inference rows不重复，四相位完整；
- future target只通过独立evaluation index加入；
- post-2020读取为0；
- formal/isolated全部核心文件字节一致；
- source closure无漂移。

收官后必须停止，等待是否开放盘中OT1 successor。
