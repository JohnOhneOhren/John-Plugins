"""只从明确文件清单构建分享包，避免打包个人笔记、凭证和测试缓存。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins' / 'weread-notes'
FILES = [
    'plugin.json', 'GUIDE.md', 'MAINTAINING.md', 'requirements.txt',
    'skills/weread-notes/SKILL.md', 'skills/weread-notes/agents/openai.yaml',
    'scripts/launch.py', 'scripts/updates.py', 'scripts/bridge.py', 'scripts/weread_notes.py', 'scripts/credentials.py',
]


def build(artifact_base=None):
    # 项目单文件脚本是唯一核心实现来源；复制件由构建自动同步。
    shutil.copyfile(ROOT / 'weread_notes.py', PLUGIN / 'scripts' / 'weread_notes.py')
    shutil.copyfile(ROOT / 'requirements.txt', PLUGIN / 'requirements.txt')
    version = json.loads((PLUGIN / 'plugin.json').read_text(encoding='utf-8'))['version']
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    archive = output / ('weread-notes-' + version + '.zip')
    entries = [(PLUGIN / p, 'plugins/weread-notes/' + p) for p in FILES]
    entries.append((ROOT / '.agents/plugins/marketplace.json', '.agents/plugins/marketplace.json'))
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as package:
        for path, name in entries:
            data = path.read_bytes()
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            package.writestr(entry, data)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    release = {'name': 'weread-notes', 'version': version, 'sha256': digest,
               'artifact_url': artifact_base.rstrip('/') + '/' + archive.name if artifact_base else None,
               'configured': bool(artifact_base)}
    (output / 'release.json').write_text(json.dumps(release, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'archive': str(archive), 'sha256': digest, 'files': len(entries), 'update_feed_ready': bool(artifact_base)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-base', help='真实发布包所在 HTTPS 目录；不填则生成未启用更新源的本地分享包')
    args = parser.parse_args()
    if args.artifact_base:
        from urllib.parse import urlsplit
        url = urlsplit(args.artifact_base)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            parser.error('--artifact-base 必须为公开 HTTPS 目录，不含账号、查询或 fragment')
    print(json.dumps(build(args.artifact_base), ensure_ascii=False))
