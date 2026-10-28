# 增量同步协议

默认再次同步保留旧内容，只补新增的原文与想法/评论，不重建或覆盖整页。相同内容在不同章节分别处理。自己的想法、读者观点即使正文相同也不混为一条。时间显示选择不影响记录身份；删除、取消点赞或重新编辑过的旧记录不自动清除，不恢复用户已删除的导入内容。

## Notion

1. 用户明确选择“新建一份”时使用 prepare --sync-mode new 并新建目标。否则先从本地导入回执找到同一 book_id 的旧页面，读取当前远端内容并确认用户的本次目标。多个旧页面时在对话中选一个。新选目标没有旧笔记则按首次导入处理，不能对别的页面去重后漏写新目标。
2. 读取 schema_version=2 的 notion-plan，含 records。旧版历史笔记可直接参与精确文本对比，不要求先全量重写。必须 fetch 目标完整正文及 get_comments 全部原生评论（含各块、全部分页），按真实章节和原文位置建立快照。拒绝截断数据，不能把未能读取的评论当成空列表。不要将 `<span discussion-urls>` 或 Notion 格式标签当正文；转换 rich_text/选区为真实纯文本，不概括或改写。保留源 Markdown 供后续最小编辑。

快照 JSON（保存在用户输出目录，不能放插件仓库）：

```json
{
  "book_id": "实际 bookId",
  "page_id": "实际目标页 ID",
  "comments_complete": true,
  "chapters": [{"title": "章节名", "paragraphs": [{"text": "原文", "id": "可取得时填写实际 block ID"}]}],
  "comments": [{"id": "实际评论 ID", "chapter_title": "章节名", "selection": "关联的整段原文纯文本", "text": "我的想法\n评论正文"}]
}
```

章节尚无导出标题的旧手工笔记，不要猜测归属，应先确认与原文对应的章节。有未关联原文的独立章节想法，selection 为空字符串。评论选区需要由 discussion 标记/实际 block 对应关系恢复完整原文；只有截短片段无法可靠对应时应说明，不能凭相似度绑定。只有完整读取成功才设置 comments_complete=true。接口不给 block ID 时省略 id，不编造 ID。

3. 后台 `sync-plan --plan <当前计划> --existing <快照> --receipt <已有回执，可省略> --output <增量计划>`。回执只能对应同一书、同一实际 page_id：

回执文件位置以 book_id 和 page_id 的组合稳定命名（例如对二者计算 SHA256 后截取文件名），不能只按本次 plan fingerprint 命名，否则新增笔记改变 fingerprint 会找不到旧回执。首次完整导入也使用每条 comments 的 key/part 保存 completed/comment_parts，后续沿用同一份回执。

```json
{
  "book_id": "实际 bookId",
  "page_id": "实际目标页 ID",
  "completed": [{"key": "已完成记录 key", "remote_id": "可取得的真实远端 ID"}],
  "comment_parts": [{"key": "评论记录 key", "part": 0, "remote_id": "实际已创建的评论 ID"}]
}
```

4. 增量计划 chapters 仅含需添加的原文，comments 仅含需添加的批注。retained/matched 是旧内容，不再写入。unresolved 是原文被手动改写或位置不明确的新增评论：先在对话中定位，不另抄一份原文绕过关联问题。已有回执的记录保持已导入状态，即使用户改写/删除也不自动重建。
5. 将新原文追加到对应章节正文末尾，保留那一章的现有文本、人工批注、格式、讨论引用、图片、子页及表格。新章节按目录插到 next_existing_chapter 之前，或最后追加，保留横线和标题后空行。使用 update_content 最小的唯一原文上下文插入；不存在唯一位置就先澄清。不要 replace_content 整页，不再次附加完整书名、作者或重复章节目录。
6. comments 的 selection 是当前实际对应原文；有 anchor_block_id 可帮助定位，没有 ID 就在正确章节内用真实邻近上下文消歧。每个 jobs 元素分别创建原生评论，成功后立即保存 comment_parts，全部完成才记 completed。源段落新增完成也立即保存 completed；remote_id 仅在真实取得时保存。matched 可加入回执以供下一次识别，不提前记录尚未写入的新增项。长评论的部分已成功时不能重发已完成 parts。
7. 写入超时先读取远端核对是否已成功，再继续，不盲目重试。无新增就不写页面，回复“本次无新增，原笔记已保留”。有新增报告新增原文/想法数量及旧内容保留数；部分未定位/未完成则不能称完整同步成功。

## Word

prepare --format word 默认更新该 book_id 上次同步的文件。首次遇到多个旧同名文件返回 word_target_required，由对话选定后用 --word-target 传路径，不打开终端。明确新建则传 --sync-mode new。

Word 通过隐藏书签识别已导入的原文/评论，以避免手动编辑后的条目再次添加；旧版文件没有书签时按同章精确文本识别并建立标记。不重建已有正文 XML；新评论加在对应原文下，新原文在所属章节末尾补充。修改现有文件前保留 .before-sync.bak 备份，原子替换保存。旧文件移动或存在同名章节等歧义时先确认，不自动另建重复笔记。

此增量协议用于 Codex 插件；独立 weread_notes.py 的开发者向导仍是原先单次导出行为，不能混用其全量追加逻辑来完成增量同步。
