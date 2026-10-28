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


def connector_plan(book):
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
                label, _, body = text.partition('\n')
                chunks = core.text_chunks(body)
                for offset in range(0, len(chunks), 20):
                    rich_text = [{'type': 'text', 'text': {'content': label + ('（续）' if offset else '')},
                                  'annotations': {'bold': True}}]
                    rich_text.extend({'type': 'text', 'text': {'content': ('\n' if i == 0 else '') + part},
                                      'annotations': {'italic': False}}
                                     for i, part in enumerate(chunks[offset:offset + 20]))
                    comments.append({'selection': anchor or chapter,
                                     'anchor_kind': 'paragraph' if anchor else 'chapter', 'rich_text': rich_text})
            elif kind == 'notice':
                parts.append('<p color="gray">' + markdown_text(text) + '</p>')
            else:
                parts.append(markdown_text(text))
                if kind == 'subtitle':
                    parts.append('<p />')
                if kind == 'quote':
                    anchor = text
    plan = {'schema_version': 1, 'book_id': book.book_id, 'title': book.title + ' 读书笔记',
            'content': '\n\n'.join(parts), 'comments': comments, 'warnings': core.concise_notices(book.warnings)}
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
    auth = sub.add_parser('auth')
    auth_sub = auth.add_subparsers(dest='auth_command', required=True)
    auth_sub.add_parser('status')
    auth_sub.add_parser('forget')
    provision = auth_sub.add_parser('import')
    provision.add_argument('--clipboard', action='store_true', required=True,
                           help='仅在用户明确已复制 Key 后主动读取一次，不回显')
    provision.add_argument('--remember', action='store_true', help='同一 Windows 用户加密记住授权；默认仅保留 30 分钟')
    prep = sub.add_parser('prepare')
    selection = prep.add_mutually_exclusive_group()
    selection.add_argument('--book-id')
    selection.add_argument('--book-name')
    prep.add_argument('--format', choices=['word', 'notion'], required=True)
    prep.add_argument('--dates', choices=['show', 'hide'], required=True)
    prep.add_argument('--output', type=Path, default=Path.cwd() / 'Weread_Notes_Output')
    prep.add_argument('--personal-only', action='store_true')
    prep.add_argument('--demo', action='store_true')
    prep.add_argument('--max-review-checks', type=int, default=200)
    prep.add_argument('--max-review-ranges', type=int, default=500)
    args = parser.parse_args(argv)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            if args.command == 'doctor':
                result = {'python': sys.version.split()[0], 'python_supported': sys.version_info >= (3, 10),
                          'dependencies': {m: importlib.util.find_spec(m) is not None for m in ['docx', 'notion_client']},
                          'weread_authorized_in_environment': bool(os.environ.get('WEREAD_API_KEY')),
                          'auth': credentials.status(), 'interaction': 'codex_chat_only',
                          'edge_required': False, 'notion_connector': '由 Codex 检查当前用户连接'}
            elif args.command == 'auth':
                if args.auth_command == 'status':
                    result = credentials.status()
                elif args.auth_command == 'forget':
                    result = credentials.forget()
                else:
                    # 不调用 input/getpass/PowerShell，不在 stdout、stderr 或文件中输出 Key。
                    key = core.read_clipboard().strip()
                    core.validate_api_key(key)
                    books = core.Weread(api_key=key, interactive_auth=False).shelf()
                    credentials.save_key(key, remember=args.remember)
                    result = {'authorized': True, 'remembered': args.remember,
                              'expires_in_seconds': None if args.remember else 1800, 'books': book_choices(books)}
            else:
                if args.command == 'prepare' and min(args.max_review_checks, args.max_review_ranges) < 1:
                    raise core.ExportError('扫描上限必须大于 0。')
                if args.command == 'prepare' and args.demo:
                    book = core.demo_book(ZoneInfo('Asia/Shanghai'))
                else:
                    key = credentials.get_key()
                    client = core.Weread(api_key=key, interactive_auth=False,
                                         personal_only=getattr(args, 'personal_only', False),
                                         max_review_checks=getattr(args, 'max_review_checks', 200),
                                         max_review_ranges=getattr(args, 'max_review_ranges', 500))
                    shelf = client.shelf()
                    if args.command == 'shelf':
                        result = {'books': book_choices(shelf)}
                    else:
                        selected = select_for_chat(shelf, args.book_id, args.book_name)
                        client.show_dates = args.dates == 'show'
                        book = client.collect(selected, ZoneInfo('Asia/Shanghai'), 0)
                if args.command == 'prepare':
                    book.show_dates = args.dates == 'show'
                    args.output.mkdir(parents=True, exist_ok=True)
                    if args.format == 'word':
                        result = {'path': str(core.export_word(book, args.output).resolve())}
                    else:
                        plan = connector_plan(book)
                        path = args.output / (core.safe_filename(book.title) + '-' + plan['fingerprint'][:12] + '.notion-plan.json')
                        core.atomic_json(path, plan)
                        result = {'path': str(path.resolve()), 'fingerprint': plan['fingerprint'],
                                  'comments': len(plan['comments'])}
                    result['warnings'] = core.concise_notices(book.warnings)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (KeyboardInterrupt, EOFError):
        print(json.dumps({'error': '已取消'}, ensure_ascii=False))
        return 130
    except SelectionError as exc:
        print(json.dumps({'status': 'selection_required', 'code': 'selection_required',
                          'message': str(exc), 'books': exc.books}, ensure_ascii=False))
        return 2
    except credentials.AuthError as exc:
        print(json.dumps({'status': 'auth_required', 'code': exc.code, 'message': str(exc)}, ensure_ascii=False))
        return 3
    except Exception as exc:
        # 仅已知安全的自定义错误可展示；第三方异常可能包含凭证。
        message = str(exc) if isinstance(exc, core.ExportError) else '执行失败：' + type(exc).__name__
        print(json.dumps({'error': message}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
