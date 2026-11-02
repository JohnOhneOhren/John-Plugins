"""本地依赖自检与隔离安装；外部插件状态只能来自宿主的实际检查。"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import venv
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import updates


def managed_python():
    folder = updates.state_root() / 'runtime' / f'py{sys.version_info.major}{sys.version_info.minor}'
    return folder / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def local_status(format):
    missing = []
    if format == 'word' and importlib.util.find_spec('docx') is None:
        missing.append('python-docx>=1.2,<2')
    try:
        ZoneInfo('Asia/Shanghai')
    except ZoneInfoNotFoundError:
        missing.append('tzdata>=2025.2')
    return {'python_supported': sys.version_info >= (3, 10), 'missing_packages': missing}


def preflight(format, host=None, destination='page'):
    local = local_status(format)
    actions = []
    if not local['python_supported']:
        actions.append({'code': 'python_required', 'minimum_version': '3.10'})
    elif local['missing_packages']:
        actions.append({'code': 'python_setup_required', 'command': ['setup', '--format', format]})
    connector = {'required': format == 'notion'}
    if format == 'notion':
        # 缺少/不可读取状态不是“已安装”，尤其不能由 notion-client 推断账号连接。
        notion = (host or {}).get('notion', {})
        if not isinstance(notion, dict):
            raise ValueError('invalid_host_state')
        connector['provider'] = 'Notion'
        if notion.get('installed') is not True:
            connector['status'] = 'discovery_required'
            actions.append({'code': 'plugin_discovery_required', 'query': 'Notion'})
        elif notion.get('connected') is not True:
            connector['status'] = 'connection_required'
            actions.append({'code': 'plugin_connection_required', 'provider': 'Notion'})
        else:
            required = {'search', 'fetch', 'get_comments', 'create_comment',
                        'create_pages' if destination == 'new' else 'update_page'}
            capabilities = notion.get('capabilities', [])
            if not isinstance(capabilities, list) or not all(isinstance(c, str) for c in capabilities):
                raise ValueError('invalid_host_state')
            missing = sorted(required - set(capabilities))
            connector.update(status='capabilities_required' if missing else 'ready', missing_capabilities=missing)
            if missing:
                actions.append({'code': 'notion_capabilities_required', 'capabilities': missing})
    ready = not actions
    return {'status': 'ready' if ready else 'dependencies_required', 'format': format,
            'local': local, 'connector': connector, 'actions': actions}


def setup(format):
    if sys.version_info < (3, 10):
        return {'status': 'dependencies_required', 'code': 'python_required'}
    if not local_status(format)['missing_packages']:
        return {'status': 'ready', 'python': sys.executable, 'installed': False}
    python = managed_python()
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(python.parent.parent)
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    # 仅固定的公开运行库；不读取宿主快照中的安装命令或修改系统 Python。
    packages = ['tzdata>=2025.2'] + (['python-docx>=1.2,<2'] if format == 'word' else [])
    result = subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                             '--no-input', *packages], capture_output=True, timeout=300, **options)
    if result.returncode:
        return {'status': 'dependencies_required', 'code': 'python_install_failed'}
    # 在目标解释器内复查，安装器退出 0 不代表环境已经可用。
    check = subprocess.run([str(python), str(Path(__file__).resolve()), 'check', '--format', format],
                           capture_output=True, text=True, encoding='utf-8', timeout=30, **options)
    if check.returncode:
        return {'status': 'dependencies_required', 'code': 'python_verification_failed'}
    return {'status': 'ready', 'python': str(python), 'installed': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['preflight', 'setup', 'check'])
    parser.add_argument('--format', choices=['word', 'notion'], required=True)
    parser.add_argument('--destination', choices=['page', 'new'], default='page')
    parser.add_argument('--host-state', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'setup':
            result = setup(args.format)
        elif args.command == 'check':
            result = local_status(args.format)
            result['status'] = 'ready' if result['python_supported'] and not result['missing_packages'] else 'dependencies_required'
        else:
            host = json.loads(args.host_state.read_text(encoding='utf-8')) if args.host_state else None
            if host is not None and not isinstance(host, dict):
                raise ValueError('invalid_host_state')
            result = preflight(args.format, host, args.destination)
    except Exception:
        # 安装器、快照和进程异常可能含本机路径或凭证；不回传原始异常。
        result = {'status': 'dependencies_required', 'code': 'dependency_check_failed'}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('status') == 'ready' else 5


if __name__ == '__main__':
    raise SystemExit(main())
