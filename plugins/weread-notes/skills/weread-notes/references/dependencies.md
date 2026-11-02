# 首次使用的依赖检查与补齐

对每位使用者检查其当前环境，不能沿用作者的账号、电脑路径或安装状态。不把用户导入笔记的请求扩大为安装无关插件。先处理本地运行能力；用户已指定输出方式时可同步检查该方式的依赖，尚未指定时只检查公共能力。微信读书 Key 的独立确认步骤仍按主 Skill 执行。

## 本地环境

- 需要本地执行器和 Python 3.10+。已有可用解释器优先复用；找不到时检查宿主提供的工作区运行时或系统 Python 启动器。仍不可用时指出缺少的具体能力，并通过宿主可用的安装入口引导；不宣称插件自带 Python 或可以仅凭浏览器登录抓取。
- 运行 `doctor` 后执行 `preflight --format word|notion`。本地缺库时后台执行 `setup --format word|notion`，仅在用户状态目录建立隔离环境并安装对应固定运行库。入口自动选择该解释器。网络/权限失败时走宿主允许的权限流程，失败仍保持未就绪；不能循环重装、要求打开终端或修改系统 Python。
- Word 只需要本地 python-docx 和时区数据，不要求 Microsoft Word、Notion 或 documents 插件。Notion 通过宿主工具写入，不要求 python-docx、notion-client 或浏览器自动化插件。时区数据在系统已提供时无需安装。setup 只补 Python 库，不安装外部账号插件。

## Notion 插件发现和连接

1. 先发现当前可用 Notion 工具。已有工具时用其访问检查/只读搜索确认当前连接，再 fetch 用户指定目标以核对访问权限；工具名字存在不等于账号连接成功。按目标检查 search、fetch、get_comments、create_comment，以及写现有页所需 update_page 或建新页所需 create_pages。不要用不存在的测试页验证权限，也不要创建空白页测试连接。
2. 缺少 Notion 工具时，发现宿主的插件管理能力。若提供 get_plugin_dependencies，可查询 `weread-notes@weread-notes-community` 的已声明依赖；社区插件可能无法解析，失败后继续实际搜索，不以此判定 Notion 不存在。调用 search_plugins，query 为 `Notion`。只选官方 Notion 的实际返回结果，不猜 ID，也不捆绑作者个人账号。
3. 未安装且允许安装时，用返回的确切 ID 调用 suggest_plugins 展示宿主安装入口；遵循工具自身的频率及去重限制，不重复推荐已安装或待处理插件。该操作是安装建议，不是后台静默安装。告诉用户完成安装并连接其自己的 Notion 后继续。
4. 已安装但未连接时，引导宿主的连接/重新授权入口；不要再次建议安装。连接可用但目标页无权限时，引导授权具体页面，不重新安装插件。安装被组织策略禁止、插件不适用于当前账号、没有管理工具或没有搜索结果时，说明实际阻碍，并给宿主插件目录/连接设置入口。未经用户选择不切换到 Word 或手工 Token 路径。
5. 等待用户完成必要的安装或账号授权期间，继续不依赖连接的环境检查、需求确认；避免先长时间抓取私人笔记再发现无法写入。连接完成后重新发现工具并复查，不凭“我装好了”或旧检查自动认定所有能力已就绪。确认就绪才抓取/导入。没有原生评论能力时说明具体缺项，不能把仅写正文称为完整成功。

## 可验证的就绪快照

可在用户输出/临时目录保存以下最小宿主检查结果（不含 Key、Token、账号正文或工具原始回包）：

```json
{"notion":{"installed":true,"connected":true,"capabilities":["search","fetch","get_comments","create_comment","update_page"]}}
```

仅在实际检查证实时置 true；未知不猜测。执行 `preflight --format notion --destination page --host-state <快照路径>`，新建页面改为 `--destination new`。Word 无需宿主快照。返回 ready 才表示所选路径的依赖检查通过，目标页权限仍需 fetch 核对。

preflight 缺少宿主快照会返回 plugin_discovery_required；未连接返回 plugin_connection_required；缺工具返回 notion_capabilities_required。根据 actions 继续上述流程，不把缺失当成功。Python 进程无法直接访问 Codex 的连接器状态，快照由宿主工具提供，不能用本地包安装结果代替。实际工具名称/参数以当前宿主暴露的描述为准，不依赖本文列出的内部名字永久不变。
