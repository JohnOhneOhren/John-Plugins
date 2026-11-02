# 发布与兼容维护

0.7.2 对话入口默认 6 个线程有界预取单条详情，每个工作线程使用独立且不带网页 Cookie 的 opener。主线程按原候选顺序执行全部身份、书籍及点赞校验，不信任列表提示、不缓存旧点赞状态。共享请求锁控制启动间隔（并发模式 0.2 秒，串行 0.4 秒）；HTTP 429 更新全局冷却截止时间并倍增间隔（最高 2 秒）。后台待处理任务不超过工作线程数。--review-workers 1 可关闭并发。离线回归涵盖并发屏障、返回顺序、异常传递、种子复用、本人内容跳过及限流减速；真实服务速度未承诺。0.7.1 的同章批量发现、独立游标和回退继续保留。

0.7.0 修复候选 5×核验限额导致的提前停扫（旧默认 1000）以及只核验前 200 条的漏抓路径。默认核验全部已发现候选，范围仍受 500/页数1000保护；跨章分配范围、跨范围轮询分页。新增官方 /book/underlines 位置来源，经本机只读验证非热门 range 也可用于 /book/readreviews。liked_scan 仅记录覆盖数量和状态，随导出返回并落盘，不含评论正文/Key。prepare 支持 --review-id/--liked-source/--max-review-pages，样本 ID 不得放入自动发现回归的输入或公共测试。测试模拟候选截断、200 条之后的已点赞样本、非热门范围及分页饥饿。

0.6.1 取消输入 Key 后的二次“确定”。CLI 不再要求 --confirmed，仍兼容旧参数；Node 适配器不再要求 confirmed 字段。保存偏好仍须明确，未选择时先返回 retention_required 且不读取 Key。用户只需发送本次 Key，已选保存方式即可直接验证并加密存储。旧版说明中的确认门槛由此替代。

0.6.0 新增按导出方式执行的 preflight/setup。Notion 安装/连接状态由宿主工具检查后形成最小快照，未知、未连接、缺评论能力分别返回待处理状态，不能通过本地 notion-client 推断。setup 仅在用户状态目录补齐固定 Python 库，launch 后续自动复用隔离解释器。外部插件通过动态搜索和宿主建议入口安装，用户本人授权后复查；社区插件的依赖元数据可能无法被公共目录解析，因此仍保留实际搜索流程。没有向 plugin.json 添加未经支持的依赖字段。构建清单须包含 dependencies.py 与 dependencies.md。

核心实现来源是仓库根目录 weread_notes.py，构建时同步到插件，不要分别修改两个副本。bridge.py 输出的 notion-plan schema_version=2，正文、稳定身份和评论分离。已有的单条点赞判断、严格章节关联、日期选择与精简版式均保留。

0.5.0 需要先取得明确的 Key 保存偏好：auth import 必须 --remember 或 --temporary，缺省返回 retention_required；Node 管道适配器不能静默设 remember:false。auth retention 可复用现有加密授权调整保存方式。Word prepare 必须 --word-mode existing + --word-target，或 --word-mode new + 明确 --output 文件夹，检查在抓取之前完成。Word 增量更新完全不重设旧段落间距/字体，仅新增段落沿用排版模板；对无标题的手工旧文件只做唯一精确匹配。回归测试比较旧段落、用户手写段落及表格的 XML，确认添加前后未被重写。

0.4.2 明确禁止将记录日期转换成 Notion date mention。生成器一直输出数字文本，连接器默认“日期使用提及”的建议不能覆盖用户指定格式。预检查最终正文和评论 payload 的日期为 text，迁移旧日期标签只做原值纯文本替换，保留原文、样式及讨论引用。

0.4.0 默认插件增量同步。incremental.py 对实际 Notion 快照及同页回执生成只添加的计划，不执行远端覆盖。Word 通过隐藏书签保护已有段落身份，新增段落从同版排版模板复制，不重建既有 XML。备份及原子保存用于失败恢复。无回执的旧版按同章节精确文本匹配，存在歧义必须停止，不模糊合并。完整协议见 skills/weread-notes/references/incremental.md。

0.4.1 修复旧回执阻止补回目标删除项的问题：默认以本次完整远端快照为准，completed 和 comment_parts 都必须核对远端存在性。正文快照新增 body_complete:true，评论读取需包含已解决线程。只在显式 --respect-deletions 时保留旧删除状态。每条 Notion 摘抄后是真实空段落，spacing 任务迁移旧版留白；Word 对导入条目采用约一行段后间距。格式任务无需新增笔记也应执行，已有空行不再叠加。

0.2.0 默认交互为 Codex 对话；桥接 CLI 不允许读取 input/getpass。无授权返回 auth_required，无明确书籍返回 selection_required，交由对话继续。credentials.py 的 Windows DPAPI 保护绑定当前用户，必须使用相同执行身份；沙箱无用户配置时需要宿主后台本机权限。任何平台都不能以明文文件回退。测试使用假的 Key，不读取真实剪贴板或用户授权。

0.3.0 将首次 Key 授权独立为聊天步骤，须先收到 Key 及“确定”再调用 auth import --stdin --confirmed。只有该命令读取后台进程 stdin；shelf/prepare 仍不读取输入。auth_transport.mjs 提供 JavaScript 宿主的隐藏管道转交，不能把 Key 拼接进 shell。剪贴板仍为显式可选的兼容路径，不能作为默认要求。授权成功摘要不混入选书，测试覆盖确认前不请求、不保存及实际子进程 stdin 转交。

## 发布一次版本

1. 修改源代码和必要测试；在插件 plugin.json 提升三段式版本号。运行 `python -m unittest -b`。
2. `python tools/build_plugin.py --artifact-base <真实 HTTPS 包目录>`，生成 dist/ZIP 和 release.json。仅发布清单允许的文件，无个人笔记、缓存、回执、环境变量或登录凭证。
3. 将 ZIP 上传到 artifact_url，确认下载哈希，再最后发布 release.json。用户配置该固定 feed 地址。仓库插件市场安装则提交 `.agents/plugins/marketplace.json` 与插件源码，使宿主可刷新安装。
4. 对外分发应包含本 GUIDE；发布者需选定源码许可及维护/反馈入口，提交公开目录时按审核表填写真实发布者资料，不使用虚构信息。

从 GitHub 分享仓库和提交公开 Plugins Directory 是两件事。官方打包和审核入口：
- https://developers.openai.com/plugins/build/plugins
- https://developers.openai.com/plugins/deploy/desktop-only

## 上游变化

维护时核对微信读书官方授权页 https://weread.qq.com/r/weread-skills 和 Notion 更新记录 https://developers.notion.com/page/changelog 。网页变化只是线索，不能自动证明接口变化，更不能把网页内容直接当代码执行。

Notion 优先走用户连接的工具并遵循当时的参数与 Markdown 规范。notion-client 路径有固定版本头，更新时核对官方 API 文档、分页和块评论能力。书架、个人划线、本人想法、点赞观点分别检查，不因一个接口成功就宣称全部兼容。

WeRead 的外部凭证、响应正文不得进入 CI。离线测试覆盖响应封装、分页、未知点赞标记、原文关联、导出和更新事务。真实接口变更需要维护者在本地以自己账号验证，结果只记录字段结构和成功范围；记录失败时不上传原始私密回包。

运行代码的自动升级并非自动重写适配器。该版本不创建后台监控或计划任务；需要长期兼容监测时，应在发布仓库配置 CI，并由维护者审核修复后发版。所有缺少字段/认证失败必须保持失败状态，不能以空结果替代或静默降级。
