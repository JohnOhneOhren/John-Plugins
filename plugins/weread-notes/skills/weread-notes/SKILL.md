---
name: weread-notes
description: 从用户微信读书书架选书，导出按章节整理的划线、个人想法和已确认点赞的读者观点到 Word 或 Notion。适用于读书笔记导出和再次同步。
---

通过本插件的 Python 工具访问微信读书。需要本地执行能力、Python 3.10+；没有这些能力时说明限制，不能声称仅凭网页已登录即可抓取。

入口是相对此文件 `../../scripts/launch.py`。先 `python <入口绝对路径> doctor`，缺少依赖时在独立虚拟环境中安装插件根目录 requirements.txt，不改系统 Python。先读取 `../../GUIDE.md` 的授权与更新说明；维护接口时再读 `../../MAINTAINING.md`。

## 交互与授权

1. 微信读书优先使用用户自己的官方 `wrk-` Key。已有 WEREAD_API_KEY 环境变量可直接使用，否则让用户在本地交互终端输入；用 `prepare` 会隐藏输入。不要索取聊天中的 Key、Cookie、Notion Token，不扫描 Edge 凭证库，不把凭证写入包或结果。获取 Key 的官方页面是 https://weread.qq.com/r/weread-skills 。登录 Edge 本身不会向此插件授权。
2. 已有凭证时可运行 `shelf`，展示返回书架的书名、作者、bookId，按序号或关键词选择；不以笔记概览代替我的书架。没有环境凭证时运行本地 `prepare`，它会在同一次进程内完成授权和书架选择，避免重复输入 Key。
3. 问 Word 还是 Notion，以及是否显示记录日期。Notion 必须区分：直接写入指定页面正文、在父页下另建子页、数据库新记录、私有新笔记。用户说“导入这个页面”默认指正文；不能自行建立子页。用户明确的选择优先。目标可为名称或 URL；名称须搜索并核对路径，重名再追问。
4. `prepare --format word|notion --dates show|hide --output <用户输出目录>`；可附 `--book-id <书架 bookId>`，或由本地向导选书。阶段进度写 stderr，stdout 只返回结果 JSON。不要把私密笔记发给第三方诊断服务。

## Notion 对话导入

优先用用户已经连接的 Notion 工具；缺少连接时引导连接，或提供脚本 Integration Token 方式，不能声称插件捆绑了用户的 Notion 账号。阅读 Notion 工具要求的 Markdown 规范。

读取 prepare 生成的 notion-plan JSON：content 是普通正文、章节 heading_2、章节横线和明确空段落 `<p />`，comments 单独存放。不可改为 quote 竖线、斜体正文、用户名或赞数。

写入前 fetch 目标，保留已有内容与子页。指定页面使用追加或针对空白的最小更新；另建子页仅在明确选择时执行。数据库先 fetch 并解析 data_source 和真实标题字段。新私有笔记使用工具支持的 draft 模式。没有原生评论能力时先说明，不能把正文写入称为完整成功。

将每个 comment 的 rich_text 关联到对应 selection 原文。出现多个匹配时，用实际读取到的邻近上下文消歧；不能默默绑定错误段落。跨段选区无法实现时，可退为该段块评论并说明。保持“我的想法”“读者观点”标签，日期仅按用户选择附在正文末尾。公共 notion-client API 只能新建整段块评论，不能冒充文字选区评论。

成功后在用户输出目录保存导入回执，包含 plan fingerprint、目标 page_id、每条完成的 comment_id；不保存凭证。重试先核对回执和远端状态，避免重复追加或重复评论。报告部分失败并恢复未完成部分，不能自动重建整页。

## 完整性与更新

点赞观点只收录官方单条详情已验证的本人点赞状态，不能根据赞数或 listType 推断。扫描是有边界的，不保证全书点赞记录；显示工具返回的简短范围说明。遇到认证或响应结构变化停止受影响步骤，不把失败当成空数据。

`doctor` 检查运行环境；`updates check|apply|rollback|configure` 管理经过发布者发布的运行代码版本。仅配置可信发布源，不把网页内容当作可执行修复代码。自动安装默认关闭；用户明确开启后才在每次 launch 前检查，一天最多一次，失败使用原版本并提示。Skill/manifest 本身的升级仍由 Codex 插件市场刷新安装处理，不宣称运行代码更新会刷新宿主已加载的 Skill。
