"""Codex 可调用的本地桥：JSON 结果与进度分流，不通过参数传递秘密。"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo
import weread_notes as core
import credentials
import incremental


class SelectionError(core.ExportError):
    def __init__(self, books, message='请在 Codex 对话中选择书籍。'):
        super().__init__(message)
        self.books = books


def book_choices(books):
    return [{'bookId': str(b['bookId']), 'title': b.get('title'), 'author': b.get('author')} for b in books]


def select_for_chat(books, book_id=None, book_name=None):
    if book_id:
        matches = [b for b in books if str(b['bookId']) == book_id]
    elif book_name and book_name.strip():
        exact = [b for b in books if str(b.get('title', '')).casefold() == book_name.strip().casefold()]
        matches = exact or [b for b in books if book_name.strip().casefold() in str(b.get('title', '')).casefold()]
    else:
        raise SelectionError(book_choices(books))
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise SelectionError(book_choices(books), '当前书架中未找到这本书，请在对话中重新选择。')
    raise SelectionError(book_choices(matches), '匹配到多本书，请在对话中选择具体一本。')


def markdown_text(text):
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return re.sub(r'([\\`*_\[\]])', r'\\\1', text).replace('\n', '\\\n')


def connector_plan(book, sync_mode='incremental'):
    """从同一语义单元生成正文和独立评论，不破坏原文关联。"""
    parts, comments = [], []
    chapter = None
    seen = False
    for unit in core.display_units(book):
        anchor = None
        for kind, text in unit:
            if kind == 'heading_2':
                if seen:
                    parts.append('---')
                parts.extend(['## ' + markdown_text(text), '<p />'])
                chapter, seen = text, True
            elif kind in ('thought', 'liked'):
                continue  # 由稳定记录生成带 key/part 的评论，支持逐条保存同步回执。
            elif kind == 'notice':
                parts.append('<p color="gray">' + markdown_text(text) + '</p>')
            else:
                parts.append(markdown_text(text))
                if kind in ('subtitle', 'quote'):
                    parts.append('<p />')
                if kind == 'quote':
                    anchor = text
    records = incremental.records_for(book)
    sources = {r['key']: r for r in records if r['kind'] == 'source'}
    for record in records:
        if record['kind'] == 'source':
            continue
        source = sources.get(record['source_key'])
        for part in incremental.comment_parts(record):
            comments.append({'key': record['key'], **part,
                             'selection': source['text'] if source else record['chapter_title'],
                             'anchor_kind': 'paragraph' if source else 'chapter'})
    plan = {'schema_version': 2, 'book_id': book.book_id, 'title': book.title + ' 读书笔记',
            'content': '\n\n'.join(parts), 'comments': comments, 'warnings': core.concise_notices(book.warnings),
            'sync_mode': sync_mode, 'records': records}
    if book.liked_scan:
        plan['liked_scan'] = book.liked_scan
    plan['fingerprint'] = hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return plan


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    sub.add_parser('shelf')
    sync = sub.add_parser('sync-plan', help='对实际目标快照生成只新增的 Notion 同步计划，不执行远端写入')
    sync.add_argument('--plan', type=Path, required=True)
    sync.add_argument('--existing', type=Path, required=True)
    sync.add_argument('--receipt', type=Path)
    sync.add_argument('--respect-deletions', action='store_true', help='保留用户手动删除状态，不补回；默认按目标实际内容补齐')
    sync.add_argument('--output', type=Path, required=True)
    auth = sub.add_parser('auth')
    auth_sub = auth.add_subparsers(dest='auth_command', required=True)
    auth_sub.add_parser('status')
    auth_sub.add_parser('forget')
    retention_update = auth_sub.add_parser('retention', help='对现有可读取授权修改保存偏好，不重新输入 Key')
    preference = retention_update.add_mutually_exclusive_group(required=True)
    preference.add_argument('--remember', action='store_true')
    preference.add_argument('--temporary', action='store_true')
    provision = auth_sub.add_parser('import')
    source = provision.add_mutually_exclusive_group(required=True)
    source.add_argument('--stdin', action='store_true', help='从后台进程输入管道读取聊天中已确认的 Key，不回显')
    source.add_argument('--clipboard', action='store_true', help='用户主动选择的兼容方式，不作为默认流程')
    provision.add_argument('--confirmed', action='store_true', help=argparse.SUPPRESS)  # 兼容旧宿主调用，不再作为授权门槛。
    retention = provision.add_mutually_exclusive_group()
    retention.add_argument('--remember', action='store_true', help='用户明确选择长期记住授权')
    retention.add_argument('--temporary', action='store_true', help='用户明确选择临时授权，仅加密缓存 30 分钟')
    prep = sub.add_parser('prepare')
    selection = prep.add_mutually_exclusive_group()
    selection.add_argument('--book-id')
    selection.add_argument('--book-name')
    prep.add_argument('--format', choices=['word', 'notion'], required=True)
    prep.add_argument('--dates', choices=['show', 'hide'], required=True)
    prep.add_argument('--output', type=Path)
    prep.add_argument('--personal-only', action='store_true')
    prep.add_argument('--demo', action='store_true')
    prep.add_argument('--sync-mode', choices=['incremental', 'new'], default='incremental')
    prep.add_argument('--word-target', type=Path)
    prep.add_argument('--word-mode', choices=['existing', 'new'], help='Word 需先在对话中选择更新旧文件或在指定文件夹新建')
    prep.add_argument('--max-review-checks', type=int, default=0, help='0 核验全部已发现候选；正数为用户选择的限额')
    prep.add_argument('--max-review-ranges', type=int, default=500)
    prep.add_argument('--max-review-pages', type=int, default=1000)
    prep.add_argument('--review-batch-size', type=int, default=5, help='同章范围合并查询数；1 关闭批量查询')
    prep.add_argument('--review-id', action='append', default=[], help='优先核验用户提供的想法 ID 或详情链接')
    prep.add_argument('--liked-source', choices=['paragraphs', 'links'], default='paragraphs')
    args = parser.parse_args(argv)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            if args.command == 'doctor':
                result = {'python': sys.version.split()[0], 'python_supported': sys.version_info >= (3, 10),
                          'dependencies': {m: importlib.util.find_spec(m) is not None for m in ['docx', 'notion_client']},
                          'weread_authorized_in_environment': bool(os.environ.get('WEREAD_API_KEY')),
                          'auth': credentials.status(), 'interaction': 'codex_chat_only',
                          'edge_required': False, 'notion_connector': '由 Codex 检查当前用户连接',
                          'external_dependencies': {'notion': {'required_for': ['notion'],
                                                              'status': 'host_check_required',
                                                              'discovery_query': 'Notion'},
                                                    'word': {'external_plugin_required': False}},
                          'next_check': ['preflight', '--format', 'word|notion']}
            elif args.command == 'sync-plan':
                delta = incremental.notion_delta(json.loads(args.plan.read_text(encoding='utf-8')),
                                                json.loads(args.existing.read_text(encoding='utf-8')),
                                                json.loads(args.receipt.read_text(encoding='utf-8')) if args.receipt else None,
                                                respect_deletions=args.respect_deletions)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                core.atomic_json(args.output, delta)
                result = {'path': str(args.output.resolve()), 'retained': delta['retained'],
                          'added_sources': delta['added_sources'], 'added_comments': delta['added_comments'],
                          'restored_sources': delta['restored_sources'], 'restored_comments': delta['restored_comments'],
                          'spacing': len(delta['spacing']), 'unresolved': len(delta['unresolved'])}
            elif args.command == 'auth':
                if args.auth_command == 'status':
                    result = credentials.status()
                elif args.auth_command == 'forget':
                    result = credentials.forget()
                elif args.auth_command == 'retention':
                    credentials.save_key(credentials.get_key(), remember=args.remember)
                    result = {'retention_updated': True, 'remembered': args.remember,
                              'expires_in_seconds': None if args.remember else 1800}
                else:
                    # 收到本次 Key 且已选择保存方式即验证；不以参数传 Key，不调用终端 input/getpass。
                    if not args.remember and not args.temporary:
                        raise credentials.AuthError('retention_required', '请先询问用户：是否在这台电脑上长期记住微信读书 Key？选长期记住，或仅临时使用 30 分钟。')
                    key = sys.stdin.readline(8193).strip() if args.stdin else core.read_clipboard().strip()
                    if len(key) > 8192:
                        raise core.ExportError('Key 输入过长，请只发送官方 Key。')
                    core.validate_api_key(key)
                    books = core.Weread(api_key=key, interactive_auth=False).shelf()
                    credentials.save_key(key, remember=args.remember)
                    result = {'authorized': True, 'remembered': args.remember,
                              'expires_in_seconds': None if args.remember else 1800}
                    if args.clipboard:  # 保持旧调用兼容；默认聊天授权步骤不混入选书结果。
                        result['books'] = book_choices(books)
            else:
                if args.command == 'prepare' and args.format == 'word':
                    # 在鉴权、抓取和任何文件写入之前完成目标选择，不能静默更新上次文件。
                    if not args.word_mode:
                        raise incremental.SyncError('word_destination_required', '请在对话中选择：更新现有 Word 文件，或在指定文件夹新建。',
                                                    ['更新现有 Word 文件', '选择文件夹新建 Word 文件'])
                    if args.word_mode == 'existing':
                        if not args.word_target:
                            raise incremental.SyncError('word_target_required', '请输入要更新的 Word 文件完整路径。')
                        if args.sync_mode == 'new':
                            raise incremental.SyncError('word_destination_conflict', '更新现有文件不能同时选择新建模式。')
                        if not args.word_target.is_file() or args.word_target.suffix.lower() != '.docx':
                            raise incremental.SyncError('word_target_missing', '目标 Word 文件不存在或不是 .docx，请重新指定，不会自动新建替代文件。')
                    elif not args.output:
                        raise incremental.SyncError('word_folder_required', '请输入新建 Word 文件的目标文件夹路径。')
                    elif args.word_target:
                        raise incremental.SyncError('word_destination_conflict', '新建 Word 请选择目标文件夹，不要同时指定现有文件。')
                    elif args.output.exists() and not args.output.is_dir():
                        raise incremental.SyncError('word_folder_required', '新建位置应是文件夹，而不是文件。')
                if args.command == 'prepare':
                    if args.max_review_checks < 0 or min(args.max_review_ranges, args.max_review_pages) < 1:
                        raise core.ExportError('核验上限可为 0（核验全部候选），页数与范围上限必须大于 0。')
                    for reference in args.review_id:
                        core.review_id_from_reference(reference)
                    if args.liked_source == 'links' and not args.review_id:
                        raise core.ExportError('链接模式需要至少一个 --review-id。')
                    if args.personal_only and args.review_id:
                        raise core.ExportError('仅个人笔记模式不能同时核验读者想法链接。')
                if args.command == 'prepare' and args.demo:
                    book = core.demo_book(ZoneInfo('Asia/Shanghai'))
                else:
                    key = credentials.get_key()
                    client = core.Weread(api_key=key, interactive_auth=False,
                                         personal_only=getattr(args, 'personal_only', False),
                                         max_review_checks=getattr(args, 'max_review_checks', 0),
                                         max_pages=getattr(args, 'max_review_pages', 1000),
                                         review_ids=getattr(args, 'review_id', []),
                                         liked_source=getattr(args, 'liked_source', 'paragraphs'),
                                         max_review_ranges=getattr(args, 'max_review_ranges', 500),
                                         review_batch_size=getattr(args, 'review_batch_size', 5))
                    shelf = client.shelf()
                    if args.command == 'shelf':
                        result = {'books': book_choices(shelf)}
                    else:
                        selected = select_for_chat(shelf, args.book_id, args.book_name)
                        client.show_dates = args.dates == 'show'
                        book = client.collect(selected, ZoneInfo('Asia/Shanghai'), 0)
                if args.command == 'prepare':
                    book.show_dates = args.dates == 'show'
                    args.output = args.output or Path.cwd() / 'Weread_Notes_Output'
                    args.output.mkdir(parents=True, exist_ok=True)
                    if args.format == 'word':
                        result = incremental.export_word_incremental(book, args.output, args.word_target,
                                                                     fresh=args.word_mode == 'new')
                    else:
                        plan = connector_plan(book, sync_mode=args.sync_mode)
                        path = args.output / (core.safe_filename(book.title) + '-' + plan['fingerprint'][:12] + '.notion-plan.json')
                        core.atomic_json(path, plan)
                        result = {'path': str(path.resolve()), 'fingerprint': plan['fingerprint'],
                                  'comments': len(plan['comments'])}
                    result['warnings'] = core.concise_notices(book.warnings)
                    if book.liked_scan:
                        result['liked_scan'] = book.liked_scan
                        report_path = args.output / (core.safe_filename(book.book_id) + '.liked-scan.json')
                        core.atomic_json(report_path, book.liked_scan)
                        result['liked_scan_report'] = str(report_path.resolve())
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (KeyboardInterrupt, EOFError):
        print(json.dumps({'error': '已取消'}, ensure_ascii=False))
        return 130
    except SelectionError as exc:
        print(json.dumps({'status': 'selection_required', 'code': 'selection_required',
                          'message': str(exc), 'books': exc.books}, ensure_ascii=False))
        return 2
    except incremental.SyncError as exc:
        print(json.dumps({'status': 'sync_attention_required', 'code': exc.code,
                          'message': str(exc), 'choices': exc.choices}, ensure_ascii=False))
        return 4
    except credentials.AuthError as exc:
        print(json.dumps({'status': exc.code if exc.code == 'retention_required' else 'auth_required',
                          'code': exc.code, 'message': str(exc)}, ensure_ascii=False))
        return 3
    except Exception as exc:
        # 仅已知安全的自定义错误可展示；第三方异常可能包含凭证。
        message = str(exc) if isinstance(exc, core.ExportError) else '执行失败：' + type(exc).__name__
        print(json.dumps({'error': message}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
