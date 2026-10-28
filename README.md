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
- 同一本书再次同步到同一位置时，只补新增划线和评论，保留旧笔记与人工修改；Word 写入前备份。
- 支持运行代码更新包校验与回滚；尚未配置远端更新源。

所有选书与导出选项在 Codex 对话中完成，不需要 PowerShell，也不重复输入书名。首次独立输入微信读书 Key，回复“确定”后才后台验证授权；成功后再选书和导出。Key 会进入聊天历史，插件不回显，也不放进命令行或明文文件；Windows 可选择加密记住授权。剪贴板仅作为主动选择的兼容方式。Notion 使用用户自己的连接，凭证不能提交到仓库。

## 开发与发布

Python 3.10+，依赖见 requirements.txt。

```shell
python -m pip install -r requirements.txt
python -m unittest -b
python tools/build_plugin.py
```

发布维护见 [维护说明](plugins/weread-notes/MAINTAINING.md)。微信读书和 Notion 的接口变化需要维护者验证修复并发布新版；自动升级不能代替兼容修复。当前为社区项目，与微信读书、Notion 无官方隶属关系。
