"""固定入口；更新运行代码存于用户数据目录，安装目录保持不变。"""
from pathlib import Path
import os
import subprocess
import sys
import updates


def main():
    if sys.argv[1:2] == ['updates']:
        return updates.main(sys.argv[2:])
    try:
        updates.auto_update()
        plugin = updates.active_plugin()
    except Exception:
        print('更新状态异常，使用捆绑版本；可运行 updates rollback。', file=sys.stderr)
        plugin = Path(__file__).resolve().parents[1]
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    if sys.argv[1:3] == ['auth', 'import'] and '--stdin' in sys.argv and '--confirmed' in sys.argv:
        # 从宿主后台管道转交一次，绝不打开终端或把 Key 放入 argv。
        payload = sys.stdin.readline(8193).encode('utf-8')
        return subprocess.run([sys.executable, str(plugin / 'scripts' / 'bridge.py'), *sys.argv[1:]],
                              input=payload, stdout=sys.stdout, stderr=sys.stderr, **options).returncode
    # CREATE_NO_WINDOW 不提供控制台默认句柄，必须显式传递管道，否则 JSON 会丢失。
    return subprocess.call([sys.executable, str(plugin / 'scripts' / 'bridge.py'), *sys.argv[1:]],
                           stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr, **options)


if __name__ == '__main__':
    raise SystemExit(main())
