# Chat 模式研究入口

本分支服务于 **ChatGPT网页版Chat模式**，不要求使用Work或Codex云端。公库只提供入口说明；私有研究代码、数据和结果都留在私库。

在Chat中使用已经连接的GitHub插件，读取：

`staryocean0/factorlab-multifactor-research-private` 中的 `AGENTS.md`、`CHAT_START.md`、`CLOUD_CURRENT.json`。

项目所有者已确认其Chat可以访问公私库及修改文件；不重复要求证明这两项。若某个具体文件读取失败，报告具体失败，不改用公开副本泄露内容。

按私库说明准备有界数据、使用实际计算工具、把成果写回私库。不要将4GiB数据塞入聊天上下文，也不从文件修改能力推导计算规模。

`bootstrap.py`仅保留为旧终端执行器参考，不是Chat的启动方式。旧main与PR历史未清理，本分支不继承旧数据/模型的当前权威。禁止向本公库提交私有数据、patch、日志、模型或结果。
