# 微信读书笔记 · Codex 插件 0.1.0

在 Codex 本地对话中选择微信读书书架上的书，将划线、我的想法、已核验点赞的读者观点整理成 Word 或 Notion。不是 Edge 浏览器扩展。需要本地 Python 3.10+；云端无本地运行能力的聊天不支持这套本地脚本。

## 安装与开始

分享包解压后，将解压目录作为仓库插件市场使用；其中 `.agents/plugins/marketplace.json` 指向 `plugins/weread-notes`。在支持本地插件市场的 Codex 客户端中选择该市场并安装“微信读书笔记”，新开对话。若客户端仅提供 Git 仓库来源，使用发布者提供的仓库地址。此 ZIP 是仓库包，不是直接拖入 Edge 的安装包。

初次安装需要在独立 Python 环境中安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r plugins/weread-notes/requirements.txt
.\.venv\Scripts\python.exe plugins/weread-notes/scripts/launch.py doctor
```

对 Codex 说：“使用微信读书笔记插件，选一本书导入 Notion 的指定页面。”插件会问目标、是否显示日期，并引导本地授权。也可直接本地测试：

```powershell
.\.venv\Scripts\python.exe plugins/weread-notes/scripts/launch.py prepare --format word --dates hide
```

首次用户需在 https://weread.qq.com/r/weread-skills 登录并获取自己的 `wrk-` Key，在本地终端隐藏输入。已有 WEREAD_API_KEY 环境变量也可使用。此版不安全持久化 Key，因此新进程未设置环境变量时需再次输入。无需发送 Key 到聊天，也无需每次复制 Cookie。Key 用于调用接口，浏览器无需保持打开；仅打开已登录的 Edge 不会自动完成授权。未来若做浏览器授权桥，需要独立实现，当前不包含。

Notion 使用当前用户自己连接的 Notion 插件；首次须在 Codex 中连接账号并授权目标页面。没有连接时可以运行捆绑的 `scripts/weread_notes.py`，通过 Notion Integration Token 导入，但公共 API 关联的是整段块评论。对话连接器支持文字选区评论。该插件不内置任何人的 Notion Token，也不能共享发布者的账号权限。

## 导出与范围

Word 创建 Weread_Notes_Output 文件夹。Notion 计划先保存到该文件夹，再通过用户连接导入；计划文件含私人笔记，请自行选择分享范围。Notion 使用普通正文、章节横线、标题后留白，想法/读者观点挂在对应原文评论中。直接写入页面、子页和数据库记录分别选择，默认“导入某页”为写入其正文。

点赞观点采用可发现的段落候选 + 官方单条点赞状态核验。不是全书“我的全部点赞”接口，扫描上限或不可见段落会造成遗漏；失败不会假装没有笔记。自己的书架和笔记需要有效授权。

## 更新

有两种升级：Codex 插件市场刷新用于整个插件、Skill 和说明；本插件的运行代码更新器可安装同一发布者的新版本，不改宿主缓存。自动升级默认关闭，也不后台常驻。发布者配置真实 release.json 后，用户可明确启用“每次启动时检查，一天最多一次”：

```powershell
python plugins/weread-notes/scripts/launch.py updates configure --feed https://你的发布域名/release.json --auto on
python plugins/weread-notes/scripts/launch.py updates check
python plugins/weread-notes/scripts/launch.py updates apply
python plugins/weread-notes/scripts/launch.py updates rollback
```

上面 URL 是说明用地址，不能原样执行。未配置真实更新源时，不会访问该示例地址。更新包通过 HTTPS 下载并校验 SHA256，采用版本目录与原子指针切换；回滚同时关闭自动更新。哈希用于验证完整性，发布源本身仍须可信。依赖变化要求完整升级，不自动 pip 安装。更新器不覆盖笔记、凭证或导入回执。

Notion/微信读书接口变化不等于插件已有修复。开发者验证并发布新版本后才会升级；错误或不认识的结构会停止受影响步骤并显示提示。当前包尚未接入真实远端更新源，也未上架公开目录。
