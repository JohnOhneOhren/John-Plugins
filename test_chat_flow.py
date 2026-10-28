"""无终端交互、授权保护与对话选书回归测试。"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'plugins/weread-notes/scripts'))
import bridge
import credentials


BOOKS = [{'bookId': '1', 'title': '不开玩笑', 'author': '作者'},
         {'bookId': '2', 'title': '思考', 'author': '作者'}]


def run_bridge(arguments):
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()), \
            patch('builtins.input', side_effect=AssertionError('不应读取终端输入')), \
            patch.object(bridge.core, 'secret', side_effect=AssertionError('不应调用隐藏终端输入')), \
            patch.object(bridge.core, 'select_book', side_effect=AssertionError('不应调用终端选书')):
        code = bridge.main(arguments)
    return code, json.loads(output.getvalue())


class ChatFlowTests(unittest.TestCase):
    def test_chat_key_requires_confirmation_before_read_or_request(self):
        class Unreadable:
            def readline(self, *args):
                raise AssertionError('确认前不能读取 Key')
        with patch.object(sys, 'stdin', Unreadable()), patch.object(bridge.core, 'Weread') as client, \
                patch.object(credentials, 'save_key') as save:
            code, result = run_bridge(['auth', 'import', '--stdin'])
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'confirmation_required')
        client.assert_not_called()
        save.assert_not_called()

    def test_confirmed_chat_key_uses_pipe_without_clipboard_or_book_prompt(self):
        with patch.object(sys, 'stdin', io.StringIO('wrk-chat-test\n')), \
                patch.object(bridge.core, 'read_clipboard', side_effect=AssertionError('默认不能读剪贴板')), \
                patch.object(bridge.core, 'Weread') as client, patch.object(credentials, 'save_key') as save:
            client.return_value.shelf.return_value = BOOKS
            code, result = run_bridge(['auth', 'import', '--stdin', '--confirmed'])
        self.assertEqual(code, 0)
        self.assertTrue(result['authorized'])
        self.assertNotIn('books', result)
        self.assertNotIn('wrk-chat-test', json.dumps(result))
        save.assert_called_once_with('wrk-chat-test', remember=False)

    def test_launcher_forwards_pipe_and_does_not_echo_invalid_input(self):
        fake = 'invalid-private-fixture'
        with tempfile.TemporaryDirectory() as folder:
            run = subprocess.run([sys.executable, str(ROOT / 'plugins/weread-notes/scripts/launch.py'),
                                  'auth', 'import', '--stdin', '--confirmed'], input=fake + '\n',
                                 env={**os.environ, 'WEREAD_NOTES_STATE_DIR': folder},
                                 capture_output=True, encoding='utf-8')
        self.assertEqual(run.returncode, 1)
        self.assertIn('error', json.loads(run.stdout))
        self.assertNotIn(fake, run.stdout + run.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node runtime required for host pipe adapter test')
    def test_node_adapter_sends_key_in_pipe_not_child_arguments(self):
        module = (ROOT / 'plugins/weread-notes/scripts/auth_transport.mjs').as_uri()
        with tempfile.TemporaryDirectory() as folder:
            fake_launcher = Path(folder) / 'fake_launcher.py'
            fake_launcher.write_text(
                'import json,sys\nkey=sys.stdin.readline().strip()\n'
                'print(json.dumps({"authorized":key=="wrk-fake-transport" and not any("wrk-" in a for a in sys.argv),'
                '"remembered":"--remember" in sys.argv}))\n', encoding='utf-8')
            program = ('import {authorizeFromChat} from ' + json.dumps(module) + ';'
                       'const pending=await authorizeFromChat({python:"missing",launcher:"missing",key:"wrk-fake-transport"});'
                       'const result=await authorizeFromChat({python:process.argv[1],launcher:process.argv[2],'
                       'key:"wrk-fake-transport",confirmed:true,remember:true});'
                       'console.log(JSON.stringify({pending,result}));')
            run = subprocess.run([shutil.which('node'), '--input-type=module', '-e', program,
                                  sys.executable, str(fake_launcher)], capture_output=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['pending']['status'], 'confirmation_required')
        self.assertTrue(result['result']['authorized'])
        self.assertTrue(result['result']['remembered'])
        self.assertNotIn('wrk-fake-transport', run.stdout + run.stderr)

    def test_missing_auth_is_a_chat_event_not_a_terminal_prompt(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
                'WEREAD_API_KEY': '', 'WEREAD_NOTES_STATE_DIR': folder}):
            code, result = run_bridge(['shelf'])
        self.assertEqual(code, 3)
        self.assertEqual(result['code'], 'auth_required')

    def test_shelf_and_prepare_do_not_ask_for_book_again(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'WEREAD_API_KEY': 'wrk-fake-test'}), \
                patch.object(bridge.core, 'Weread') as client:
            client.return_value.shelf.return_value = BOOKS
            client.return_value.collect.return_value = bridge.core.demo_book(bridge.ZoneInfo('Asia/Shanghai'))
            code, shelf = run_bridge(['shelf'])
            self.assertEqual(shelf['books'][0]['bookId'], '1')
            code, exported = run_bridge(['prepare', '--book-id', shelf['books'][0]['bookId'],
                                        '--format', 'notion', '--dates', 'hide', '--output', folder])
            self.assertEqual(code, 0)
            self.assertTrue(Path(exported['path']).exists())
            selected = client.return_value.collect.call_args.args[0]
            self.assertEqual(selected['bookId'], '1')

    def test_unique_keyword_selects_without_prompt(self):
        self.assertEqual(bridge.select_for_chat(BOOKS, book_name='玩笑')['bookId'], '1')

    def test_exact_title_preferred_over_partial_matches(self):
        books = BOOKS + [{'bookId': '3', 'title': '不开玩笑续篇'}]
        self.assertEqual(bridge.select_for_chat(books, book_name='不开玩笑')['bookId'], '1')

    def test_ambiguous_and_missing_selection_return_candidates(self):
        variants = [[], ['--book-name', '想不到的名字'], ['--book-name', '开']]
        with patch.dict(os.environ, {'WEREAD_API_KEY': 'wrk-fake-test'}), patch.object(bridge.core, 'Weread') as client:
            client.return_value.shelf.return_value = BOOKS + [{'bookId': '3', 'title': '开场'}]
            for selection in variants:
                code, result = run_bridge(['prepare', '--format', 'notion', '--dates', 'hide', *selection])
                self.assertEqual(code, 2)
                self.assertEqual(result['status'], 'selection_required')
                self.assertTrue(result['books'])
            client.return_value.collect.assert_not_called()

    def test_clipboard_import_validates_before_encrypting_and_never_echoes(self):
        with patch.object(bridge.core, 'read_clipboard', return_value='wrk-fake-secret'), \
                patch.object(bridge.core, 'Weread') as client, patch.object(credentials, 'save_key') as save:
            client.return_value.shelf.return_value = BOOKS
            code, result = run_bridge(['auth', 'import', '--clipboard', '--remember'])
            self.assertEqual(code, 0)
            self.assertTrue(result['remembered'])
            self.assertEqual(result['books'][0]['bookId'], '1')
            self.assertNotIn('wrk-fake-secret', json.dumps(result))
            save.assert_called_once_with('wrk-fake-secret', remember=True)

    def test_rejected_key_does_not_replace_valid_local_auth(self):
        with patch.object(bridge.core, 'read_clipboard', return_value='wrk-fake-secret'), \
                patch.object(bridge.core, 'Weread') as client, patch.object(credentials, 'save_key') as save:
            client.return_value.shelf.side_effect = bridge.core.ExportError('授权失败')
            code, result = run_bridge(['auth', 'import', '--clipboard'])
            self.assertEqual(code, 1)
            save.assert_not_called()

    def test_saved_auth_can_be_reused_by_later_commands(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
                'WEREAD_API_KEY': '', 'WEREAD_NOTES_STATE_DIR': folder}), \
                patch.object(credentials, 'protect', side_effect=lambda data, decrypt=False: b'wrk-fake-secret' if decrypt else b'cipher-bytes'):
            credentials.save_key('wrk-fake-secret', remember=True)
            self.assertNotIn('wrk-fake-secret', credentials.vault_path().read_text())
            self.assertEqual(credentials.get_key(), 'wrk-fake-secret')
            self.assertTrue(credentials.status()['available'])
            credentials.forget()
            self.assertFalse(credentials.status()['available'])

    def test_temporary_auth_expires_without_falling_back_to_input(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
                'WEREAD_API_KEY': '', 'WEREAD_NOTES_STATE_DIR': folder}), \
                patch.object(credentials, 'protect', return_value=b'cipher'), \
                patch.object(credentials.time, 'time', return_value=1000):
            credentials.save_key('wrk-fake-secret')
            with patch.object(credentials.time, 'time', return_value=2801):
                code, result = run_bridge(['shelf'])
            self.assertEqual(code, 3)
            self.assertEqual(result['code'], 'auth_expired')

    def test_unreadable_auth_is_not_silently_treated_as_logged_in(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
                'WEREAD_API_KEY': '', 'WEREAD_NOTES_STATE_DIR': folder}):
            credentials.vault_path().write_text('{bad json', encoding='utf-8')
            self.assertEqual(credentials.status()['code'], 'auth_invalid')

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI only')
    def test_actual_windows_dpapi_round_trip(self):
        message = b'not-a-real-key\x00DPAPI-test'
        try:
            ciphertext = credentials.protect(message)
        except credentials.AuthError as exc:
            self.skipTest(str(exc))
        self.assertNotEqual(ciphertext, message)
        self.assertEqual(credentials.protect(ciphertext, decrypt=True), message)


if __name__ == '__main__':
    unittest.main()
