# 公库计算，私库存储

ChatGPT网页版使用Chat模式进行研究设计、改代码和调度。实际策略计算运行在本公库的**标准免费GitHub-hosted runner**；私库存数据、模型、代码版本和结果，私库Actions关闭。

当前执行指南：[docs/public_execution.md](docs/public_execution.md)。Actions工作流为Public standard-runner research executor，仅手动触发：

- runtime-smoke：无私库数据/凭据，验证运行环境及容器隔离。
- baseline-replay-v1：通过环境secret取固定私库数据，在断网容器重放基线，完整结果仅回存私库。

需要的受限授权为private-research环境中的FACTORLAB_PRIVATE_TOKEN；仅授新私库Contents读写，不向聊天提交token。环境限制为cloud-workspace-v1分支。

私库研究入口：staryocean0/factorlab-multifactor-research-private中的AGENTS.md、CLOUD_CURRENT.json和CHAT_START.md。公库只保存通用执行器，不放私有数据、策略补丁或结果。

旧main和PR保持可查；bootstrap.py作为历史终端参考保留。标准免费不等于无限资源；不得改用付费runner或把本公库用于无关工作。
