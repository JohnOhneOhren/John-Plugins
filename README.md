# John Plugins

个人 Codex 插件合集。当前提供微信读书笔记插件 weread-notes。

## 安装

在支持仓库插件市场的 Codex 客户端中，添加本仓库地址：

https://github.com/JohnOhneOhren/John-Plugins

选择“微信读书笔记”安装，然后新开对话。客户端需具备本地 Python 执行能力。

初次设置和使用说明见 [插件指南](plugins/weread-notes/GUIDE.md)。

## 功能

- 从自己的微信读书书架选书，整理划线与个人想法。
- 对可发现的读者观点逐条核验本人点赞状态；不保证全书点赞记录完整。
- 导出 Word，或通过用户自己的 Notion 连接导入。
- 普通正文、章节横线、标题留白，原文与想法以原生评论关联。
- 支持运行代码更新包校验与回滚；尚未配置远端更新源。

所有选书与导出选项在 Codex 对话中完成，不需要 PowerShell，也不重复输入书名。首次复制微信读书官方 Key 后回到对话说“已复制”，后台读取一次；Windows 可选择加密记住授权。Notion 使用用户自己的连接。不要把 Key 发到聊天或提交到仓库。

## 开发与发布

Python 3.10+，依赖见 requirements.txt。

```shell
python -m pip install -r requirements.txt
python -m unittest -b
python tools/build_plugin.py
```

发布维护见 [维护说明](plugins/weread-notes/MAINTAINING.md)。微信读书和 Notion 的接口变化需要维护者验证修复并发布新版；自动升级不能代替兼容修复。当前为社区项目，与微信读书、Notion 无官方隶属关系。
