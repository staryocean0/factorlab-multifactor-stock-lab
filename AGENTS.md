# Chat入口，不是终端工作区

当前目标是ChatGPT网页版Chat；不使用Work或Codex云端。项目所有者已确认Chat通过GitHub插件可读取公私库并修改文件，不重复设置GitHub读写测试门。

先通过GitHub插件读取私库staryocean0/factorlab-multifactor-research-private的AGENTS.md、CHAT_START.md、CLOUD_CURRENT.json。未实际读到就说明失败，不假设仓库AGENTS自动载入。

公库只留无敏感内容的研究入口。所有数据、研究代码变更、回测输出、私有patch和工具回执都留私库。不要在公库commit/PR/issue/Actions日志或公开分享中披露，不索取或打印token。

不默认运行bootstrap.py、克隆、安装环境或git push；这些是旧终端执行器参考。通过当前Chat实际可用工具按需取数、计算并回存私库，运行与写回分别留实际回执。
不切Work，不自动退回本地，不部署收费服务，不触发Actions，不删除/清理旧分支或PR。Github文件修改能力不等于大数据运行能力，也不构成真正盲测隔离。
