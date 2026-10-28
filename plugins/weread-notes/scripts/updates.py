"""可信 HTTPS 发布源 -> SHA256 校验 -> 版本目录 -> 原子切换，可回滚。

哈希防止包损坏，不能替代发布者身份验证；feed 必须由用户信任的发布者控制。
更新运行代码，不修改宿主缓存、已加载 Skill、依赖、用户笔记或凭证。
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import zipfile

PLUGIN = Path(__file__).resolve().parents[1]
MAX_PACKAGE = 16 * 1024 * 1024


def state_root():
    override = os.environ.get('WEREAD_NOTES_STATE_DIR')
    if override:
        return Path(override).expanduser().resolve()
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_DATA_HOME')
    return (Path(base) if base else Path.home() / '.local' / 'share') / 'weread-notes'


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def https_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('发布源和包地址必须为不含账号密码的 HTTPS URL。')
    return value


def download(url, limit):
    with urlopen(Request(https_url(url), headers={'User-Agent': 'weread-notes-updater/0.1'}), timeout=20) as response:
        https_url(response.geturl())
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('发布文件超过大小上限。')
    return data


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('只支持 major.minor.patch 正式版。')
    return tuple(map(int, value.split('.')))


def active_plugin(root=None):
    root = root or state_root()
    marker = read_json(root / 'active.json', {})
    key = marker.get('key', '')
    if not key:
        return PLUGIN
    if not re.fullmatch(r'[a-f0-9]{64}', key):
        raise ValueError('更新指针格式无效。')
    path = root / 'versions' / key
    if not (path / 'scripts' / 'bridge.py').is_file():
        raise ValueError('当前更新版本不完整，请 rollback。')
    # 宿主插件自身升级后，不能被旧的侧载运行代码覆盖。
    bundled = read_json(PLUGIN / 'plugin.json')['version']
    installed = read_json(path / 'plugin.json')['version']
    return PLUGIN if version(bundled) >= version(installed) else path


def release_info(feed):
    data = json.loads(download(feed, 64 * 1024))
    if data.get('name') != 'weread-notes':
        raise ValueError('发布清单插件名称不匹配。')
    version(data.get('version'))
    https_url(data.get('artifact_url', ''))
    if not re.fullmatch(r'[a-f0-9]{64}', data.get('sha256', '')):
        raise ValueError('发布清单缺少有效 SHA256。')
    return data


def install_release(info, archive, root):
    """完成全部校验后才切换；下载/校验失败不会触碰当前版本。"""
    if len(archive) > MAX_PACKAGE or hashlib.sha256(archive).hexdigest() != info['sha256']:
        raise ValueError('更新包大小或 SHA256 校验失败。')
    key = info['sha256']
    destination = root / 'versions' / key
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='stage-', dir=root) as work:
        stage = Path(work)
        seen, total = set(), 0
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            if len(package.infolist()) > 250:
                raise ValueError('更新包文件过多。')
            for member in package.infolist():
                name = member.filename
                parts = PurePosixPath(name).parts
                if ('\\' in name or ':' in name or name.startswith('/') or '..' in parts
                        or any(p.endswith((' ', '.')) or re.match(r'(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)', p) for p in parts)
                        or any(ord(c) < 32 for c in name)
                        or PurePosixPath(name).as_posix() != name.rstrip('/')
                        or name.casefold() in seen or (member.external_attr >> 16) & 0o170000 == 0o120000):
                    raise ValueError('更新包包含不安全路径、重复文件或符号链接。')
                seen.add(name.casefold())
                total += member.file_size
                if total > 32 * 1024 * 1024:
                    raise ValueError('更新包解压大小超过上限。')
                if parts[:2] != ('plugins', 'weread-notes') or member.is_dir():
                    continue
                relative = Path(*parts[2:])
                if not relative.parts:
                    continue
                target = stage / relative
                if not target.resolve().is_relative_to(stage.resolve()):
                    raise ValueError('更新包路径越界。')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(package.read(member))
        meta = read_json(stage / 'plugin.json', {})
        if meta.get('name') != 'weread-notes' or meta.get('version') != info['version']:
            raise ValueError('包内插件版本与发布清单不符。')
        for filename in ['scripts/bridge.py', 'scripts/weread_notes.py', 'requirements.txt']:
            if not (stage / filename).is_file():
                raise ValueError('更新包缺少必需文件。')
        # 升级依赖必须通过宿主正常更新安装，不能静默修改 Python 环境。
        if (stage / 'requirements.txt').read_bytes() != (PLUGIN / 'requirements.txt').read_bytes():
            raise ValueError('此版本变更依赖，请从插件市场完整升级并安装对应依赖。')
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copytree(stage, destination)
    old = read_json(root / 'active.json', {})
    save_json(root / 'previous.json', old)
    save_json(root / 'active.json', {'key': key, 'version': info['version']})
    return {'updated': True, 'version': info['version'], 'restart_chat_for_skill_update': True}


def check_updates(apply=False):
    root = state_root()
    config = read_json(root / 'settings.json', {})
    if not config.get('feed'):
        return {'configured': False, 'message': '发布者尚未配置更新源。'}
    info = release_info(config['feed'])
    current = read_json(active_plugin(root) / 'plugin.json')['version']
    newer = version(info['version']) > version(current)
    if apply and newer:
        return install_release(info, download(info['artifact_url'], MAX_PACKAGE), root)
    return {'configured': True, 'current': current, 'latest': info['version'], 'update_available': newer}


def auto_update():
    root = state_root()
    settings = read_json(root / 'settings.json', {})
    if not settings.get('auto_update'):
        return
    last = read_json(root / 'last-check.json', {}).get('time', 0)
    if time.time() - last < 86400:
        return
    save_json(root / 'last-check.json', {'time': time.time()})
    try:
        result = check_updates(apply=True)
        if result.get('updated'):
            print('已升级运行代码至 ' + result['version'], file=__import__('sys').stderr)
    except Exception:
        print('更新暂未完成，继续使用当前版本；可运行 updates check 查看。', file=__import__('sys').stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    cfg = sub.add_parser('configure')
    cfg.add_argument('--feed', required=True)
    cfg.add_argument('--auto', choices=['on', 'off'], default='off')
    for cmd in ['check', 'apply', 'rollback']:
        sub.add_parser(cmd)
    args = parser.parse_args(argv)
    try:
        root = state_root()
        if args.command == 'configure':
            save_json(root / 'settings.json', {'feed': https_url(args.feed), 'auto_update': args.auto == 'on'})
            result = {'configured': True, 'auto_update': args.auto == 'on'}
        elif args.command == 'rollback':
            previous = read_json(root / 'previous.json')
            if previous is None:
                raise ValueError('没有可回滚版本。')
            old = read_json(root / 'active.json', {})
            save_json(root / 'active.json', previous)
            save_json(root / 'previous.json', old)
            # 回滚同时关闭自动更新，避免下次启动立即重新升级。
            settings = read_json(root / 'settings.json', {})
            settings['auto_update'] = False
            save_json(root / 'settings.json', settings)
            result = {'rolled_back': True, 'auto_update': False}
        else:
            result = check_updates(apply=args.command == 'apply')
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        message = str(exc) if type(exc) is ValueError else type(exc).__name__
        print(json.dumps({'error': message}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
