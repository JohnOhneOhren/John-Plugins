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
    prep = sub.add_parser('prepare')
    prep.add_argument('--book-id')
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
                          'edge_required': False, 'notion_connector': '由 Codex 检查当前用户连接'}
            else:
                if args.command == 'prepare' and min(args.max_review_checks, args.max_review_ranges) < 1:
                    raise core.ExportError('扫描上限必须大于 0。')
                if args.command == 'prepare' and args.demo:
                    book = core.demo_book(ZoneInfo('Asia/Shanghai'))
                else:
                    key = os.environ.get('WEREAD_API_KEY', '')
                    if not key:
                        if not sys.stdin.isatty():
                            raise core.ExportError('请在本地交互终端运行 prepare 输入 Key，或预先设置 WEREAD_API_KEY。')
                        key = core.secret('请输入微信读书官方 Key：', 'WEREAD_API_KEY', core.validate_api_key)
                    core.validate_api_key(key)
                    client = core.Weread(api_key=key, interactive_auth=False,
                                         personal_only=getattr(args, 'personal_only', False),
                                         max_review_checks=getattr(args, 'max_review_checks', 200),
                                         max_review_ranges=getattr(args, 'max_review_ranges', 500))
                    shelf = client.shelf()
                    if args.command == 'shelf':
                        result = {'books': [{'bookId': str(b['bookId']), 'title': b.get('title'),
                                             'author': b.get('author')} for b in shelf]}
                    else:
                        matches = [b for b in shelf if str(b['bookId']) == args.book_id] if args.book_id else []
                        if args.book_id and len(matches) != 1:
                            raise core.ExportError('bookId 不在当前书架中，不能导出。')
                        selected = matches[0] if matches else core.select_book(shelf)
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
    except Exception as exc:
        # 仅已知安全的自定义错误可展示；第三方异常可能包含凭证。
        message = str(exc) if isinstance(exc, core.ExportError) else '执行失败：' + type(exc).__name__
        print(json.dumps({'error': message}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
