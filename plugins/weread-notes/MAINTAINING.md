# 发布与兼容维护

核心实现来源是仓库根目录 weread_notes.py，构建时同步到插件，不要分别修改两个副本。bridge.py 输出的 notion-plan schema_version=1，正文与评论分离。已有的单条点赞判断、严格章节关联、日期选择与精简版式均保留。

0.2.0 默认交互为 Codex 对话；桥接 CLI 不允许读取 input/getpass。无授权返回 auth_required，无明确书籍返回 selection_required，交由对话继续。credentials.py 的 Windows DPAPI 保护绑定当前用户，必须使用相同执行身份；沙箱无用户配置时需要宿主后台本机权限。任何平台都不能以明文文件回退。测试使用假的 Key，不读取真实剪贴板或用户授权。

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
