"""首次使用的缺插件、未连接、隔离安装与分享包回归，不访问真实账号。"""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / 'plugins/weread-notes/scripts'
sys.path.insert(0, str(SCRIPTS))
import dependencies


READY_LOCAL = {'python_supported': True, 'missing_packages': []}
CAPABILITIES = ['search', 'fetch', 'get_comments', 'create_comment', 'update_page']


class DependencyTests(unittest.TestCase):
    def check(self, format, host=None, destination='page'):
        with patch.object(dependencies, 'local_status', return_value=READY_LOCAL):
            return dependencies.preflight(format, host, destination)

    def test_new_user_without_host_evidence_is_not_ready_for_notion(self):
        result = self.check('notion')
        self.assertEqual(result['status'], 'dependencies_required')
        self.assertEqual(result['actions'], [{'code': 'plugin_discovery_required', 'query': 'Notion'}])

    def test_installed_plugin_needs_account_connection(self):
        result = self.check('notion', {'notion': {'installed': True, 'capabilities': CAPABILITIES}})
        self.assertEqual(result['connector']['status'], 'connection_required')
        self.assertEqual(result['actions'][0]['code'], 'plugin_connection_required')

    def test_connected_without_comments_cannot_claim_full_import(self):
        host = {'notion': {'installed': True, 'connected': True,
                           'capabilities': ['search', 'fetch', 'update_page']}}
        result = self.check('notion', host)
        self.assertEqual(result['connector']['missing_capabilities'], ['create_comment', 'get_comments'])
        self.assertNotEqual(result['status'], 'ready')

    def test_existing_page_does_not_require_page_creation(self):
        host = {'notion': {'installed': True, 'connected': True, 'capabilities': CAPABILITIES}}
        self.assertEqual(self.check('notion', host)['status'], 'ready')
        new = self.check('notion', host, 'new')
        self.assertEqual(new['connector']['missing_capabilities'], ['create_pages'])
        host['notion']['capabilities'] = CAPABILITIES + ['create_pages']
        self.assertEqual(self.check('notion', host, 'new')['status'], 'ready')

    def test_word_is_independent_of_notion_installation(self):
        result = self.check('word', {'notion': {'installed': False, 'connected': False}})
        self.assertEqual(result['status'], 'ready')
        self.assertFalse(result['connector']['required'])

    def test_local_packages_and_host_blockers_are_reported_together(self):
        with patch.object(dependencies, 'local_status', return_value={
                'python_supported': True, 'missing_packages': ['tzdata>=2025.2']}):
            result = dependencies.preflight('notion')
        self.assertEqual([a['code'] for a in result['actions']],
                         ['python_setup_required', 'plugin_discovery_required'])

    def test_string_booleans_cannot_fake_connection(self):
        result = self.check('notion', {'notion': {'installed': 'true', 'connected': 'true'}})
        self.assertEqual(result['connector']['status'], 'discovery_required')

    def test_setup_reuses_current_runtime_when_ready(self):
        with patch.object(dependencies, 'local_status', return_value=READY_LOCAL), \
                patch.object(dependencies.subprocess, 'run') as run, \
                patch.object(dependencies.venv, 'EnvBuilder') as create:
            result = dependencies.setup('word')
        self.assertEqual(result['status'], 'ready')
        self.assertFalse(result['installed'])
        run.assert_not_called()
        create.assert_not_called()

    def test_install_uses_private_runtime_and_rechecks_before_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            python = Path(folder) / 'Scripts/python.exe'
            python.parent.mkdir()
            python.touch()
            with patch.object(dependencies, 'managed_python', return_value=python), \
                    patch.object(dependencies, 'local_status', return_value={
                        'python_supported': True, 'missing_packages': ['python-docx>=1.2,<2']}), \
                    patch.object(dependencies.subprocess, 'run', side_effect=[
                        subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 5)]) as run:
                result = dependencies.setup('word')
        self.assertEqual(result['code'], 'python_verification_failed')
        install_args = run.call_args_list[0].args[0]
        self.assertEqual(install_args[0], str(python))
        self.assertIn('python-docx>=1.2,<2', install_args)
        self.assertNotIn('notion-client', ' '.join(install_args))
        self.assertIn('check', run.call_args_list[1].args[0])

    def test_failed_install_does_not_echo_installer_output(self):
        with tempfile.TemporaryDirectory() as folder:
            python = Path(folder) / 'python.exe'
            python.touch()
            with patch.object(dependencies, 'managed_python', return_value=python), \
                    patch.object(dependencies, 'local_status', return_value={
                        'python_supported': True, 'missing_packages': ['tzdata>=2025.2']}), \
                    patch.object(dependencies.subprocess, 'run', return_value=
                                 subprocess.CompletedProcess([], 1, stdout='private-proxy', stderr='secret')):
                result = dependencies.setup('notion')
        self.assertEqual(result, {'status': 'dependencies_required', 'code': 'python_install_failed'})

    def test_cli_invalid_snapshot_fails_without_echoing_contents(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / 'host.json'
            state.write_text('private-invalid-state', encoding='utf-8')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = dependencies.main(['preflight', '--format', 'notion', '--host-state', str(state)])
        self.assertEqual(code, 5)
        self.assertEqual(json.loads(output.getvalue())['code'], 'dependency_check_failed')
        self.assertNotIn('private-invalid-state', output.getvalue())

    def test_extracted_package_can_detect_missing_connector(self):
        from tools.build_plugin import build
        import zipfile
        result = build()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with zipfile.ZipFile(result['archive']) as package:
                package.extractall(root)
            run = subprocess.run([sys.executable, str(root / 'plugins/weread-notes/scripts/launch.py'),
                                  'preflight', '--format', 'notion'], cwd=root,
                                 env={**os.environ, 'WEREAD_NOTES_STATE_DIR': str(root / 'state')},
                                 capture_output=True, encoding='utf-8')
        self.assertEqual(run.returncode, 5, run.stderr)
        report = json.loads(run.stdout)
        self.assertEqual(report['connector']['status'], 'discovery_required')

    def test_clean_python_without_third_party_packages_reports_word_setup(self):
        import venv
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            venv.EnvBuilder(with_pip=False).create(root / 'empty-runtime')
            python = root / 'empty-runtime' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            run = subprocess.run([str(python), str(SCRIPTS / 'launch.py'), 'preflight', '--format', 'word'],
                                 env={**os.environ, 'WEREAD_NOTES_STATE_DIR': str(root / 'state')},
                                 capture_output=True, encoding='utf-8')
        self.assertEqual(run.returncode, 5, run.stderr)
        report = json.loads(run.stdout)
        self.assertIn('python-docx>=1.2,<2', report['local']['missing_packages'])
        self.assertFalse(report['connector']['required'])
        self.assertEqual(report['actions'][0]['code'], 'python_setup_required')


if __name__ == '__main__':
    unittest.main()
