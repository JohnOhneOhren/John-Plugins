"""分享包、对话计划及更新器的离线测试；不使用任何真实账号。"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / 'plugins/weread-notes/scripts'
sys.path.insert(0, str(SCRIPTS))
import bridge
import updates
from tools.build_plugin import build, FILES


def archive_for(version='0.3.0', extra=None):
    data = io.BytesIO()
    files = {
        'plugin.json': json.dumps({'name': 'weread-notes', 'version': version}).encode(),
        'scripts/bridge.py': b'# bridge', 'scripts/weread_notes.py': b'# core',
        'requirements.txt': (ROOT / 'requirements.txt').read_bytes(),
    }
    with zipfile.ZipFile(data, 'w') as package:
        for name, body in files.items():
            package.writestr('plugins/weread-notes/' + name, body)
        if extra:
            package.writestr(*extra)
    data = data.getvalue()
    return {'name': 'weread-notes', 'version': version, 'sha256': hashlib.sha256(data).hexdigest()}, data


class PluginTests(unittest.TestCase):
    def test_connector_plan_preserves_association_and_spacing(self):
        book = bridge.core.demo_book(ZoneInfo('Asia/Shanghai'))
        plan = bridge.connector_plan(book)
        self.assertNotIn('\n> ', plan['content'])
        self.assertNotIn('我的想法', plan['content'])
        self.assertTrue(plan['comments'])
        for comment in plan['comments']:
            self.assertIn(bridge.markdown_text(comment['selection']), plan['content'])
            self.assertEqual(comment['anchor_kind'], 'paragraph')
        self.assertEqual(plan['content'].count('<p />'), 1 + len(book.chapters))
        self.assertEqual(plan, bridge.connector_plan(book))

    def test_checksum_failure_keeps_active_version(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            updates.save_json(root / 'active.json', {'key': 'a' * 64})
            info, data = archive_for()
            with self.assertRaises(ValueError):
                updates.install_release(info, data + b'corrupt', root)
            self.assertEqual(updates.read_json(root / 'active.json'), {'key': 'a' * 64})

    def test_long_comments_are_split_without_losing_text(self):
        body = '长评论😀' * 10000
        note = bridge.core.Note('thought', '1', body, '', quote='原文')
        book = bridge.core.Notebook('book', '书', '作者', [
            bridge.core.Chapter('1', '章节', 0, [bridge.core.Group(thoughts=[note], quote='原文')])])
        jobs = bridge.connector_plan(book)['comments']
        self.assertGreater(len(jobs), 1)
        reconstructed = ''
        for job in jobs:
            pieces = job['rich_text'][1:]
            reconstructed += ''.join(p['text']['content'] for p in pieces).removeprefix('\n')
            self.assertTrue(all(len(p['text']['content'].encode('utf-16-le')) // 2 <= 2000 for p in pieces))
        self.assertEqual(body, reconstructed)

    def test_extracted_share_package_runs_independently(self):
        result = build()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with zipfile.ZipFile(result['archive']) as package:
                package.extractall(root)
            env = {**os.environ, 'WEREAD_NOTES_STATE_DIR': str(root / 'state'), 'PYTHONIOENCODING': 'utf-8'}
            run = subprocess.run([sys.executable, str(root / 'plugins/weread-notes/scripts/launch.py'),
                                  'prepare', '--demo', '--format', 'notion', '--dates', 'hide',
                                  '--output', str(root / 'output')], cwd=root, env=env,
                                 capture_output=True, encoding='utf-8')
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            response = json.loads(run.stdout)
            plan = json.loads(Path(response['path']).read_text(encoding='utf-8'))
            self.assertTrue(plan['comments'])
            self.assertIn('<p />', plan['content'])

    def test_unsafe_archives_leave_no_active_marker(self):
        for name in ['plugins/weread-notes/../../escaped.py', 'C:/escaped.py',
                     'plugins/weread-notes/scripts/CON.py', 'plugins/weread-notes/scripts/x:y',
                     'plugins/weread-notes/scripts//duplicate.py']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                info, data = archive_for(extra=(name, b'bad'))
                with self.assertRaises(ValueError):
                    updates.install_release(info, data, root)
                self.assertFalse((root / 'active.json').exists())

    def test_install_and_rollback_disable_auto(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'WEREAD_NOTES_STATE_DIR': folder}):
            root = Path(folder)
            info, data = archive_for()
            updates.save_json(root / 'settings.json', {'feed': 'https://example.org/release.json', 'auto_update': True})
            updates.install_release(info, data, root)
            self.assertEqual(updates.active_plugin(root), root / 'versions' / info['sha256'])
            with patch('sys.stdout', new=io.StringIO()):
                self.assertEqual(updates.main(['rollback']), 0)
            self.assertEqual(updates.active_plugin(root), updates.PLUGIN)
            self.assertFalse(updates.read_json(root / 'settings.json')['auto_update'])

    def test_package_version_mismatch_is_not_activated(self):
        with tempfile.TemporaryDirectory() as folder:
            info, data = archive_for()
            info['version'] = '0.4.0'
            with self.assertRaises(ValueError):
                updates.install_release(info, data, Path(folder))
            self.assertFalse((Path(folder) / 'active.json').exists())

    def test_symlink_refused(self):
        info, raw = archive_for()
        data = io.BytesIO(raw)
        with zipfile.ZipFile(data, 'a') as package:
            member = zipfile.ZipInfo('plugins/weread-notes/scripts/link')
            member.create_system = 3
            member.external_attr = 0o120777 << 16
            package.writestr(member, '../../outside')
        raw = data.getvalue()
        info['sha256'] = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            updates.install_release(info, raw, Path(folder))

    def test_feed_requires_https_and_no_embedded_credentials(self):
        for value in ['http://example.org/feed', 'file:///tmp/release', 'https://user:secret@example.org/feed']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                updates.https_url(value)

    def test_doctor_outputs_json_without_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {**os.environ, 'WEREAD_NOTES_STATE_DIR': folder, 'WEREAD_API_KEY': 'wrk-test-secret',
                   'PYTHONIOENCODING': 'utf-8'}
            run = subprocess.run([sys.executable, str(SCRIPTS / 'launch.py'), 'doctor'], env=env,
                                 capture_output=True, encoding='utf-8')
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue(json.loads(run.stdout)['weread_authorized_in_environment'])
            self.assertNotIn('wrk-test-secret', run.stdout + run.stderr)

    def test_share_archive_uses_explicit_allowlist(self):
        result = build()
        with zipfile.ZipFile(result['archive']) as package:
            expected = {'plugins/weread-notes/' + p for p in FILES} | {'.agents/plugins/marketplace.json'}
            self.assertEqual(set(package.namelist()), expected)
            self.assertNotIn('Weread_Notes_Output', ' '.join(package.namelist()))
            self.assertEqual(package.read('plugins/weread-notes/scripts/weread_notes.py'),
                             (ROOT / 'weread_notes.py').read_bytes())


if __name__ == '__main__':
    unittest.main()
